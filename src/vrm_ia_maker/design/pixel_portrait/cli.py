"""Internal JSON CLI for panel-first pixel portrait authoring."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Final, Literal, Never, TextIO

from pydantic import BaseModel, ValidationError

from ..contracts import RightsMetadata
from ..ports import AuthoringWorkspaceError, ReferenceImageGeneratorPort
from .adapters.filesystem import FilesystemPixelPortraitWorkspace
from .contracts import NEUTRAL_PANEL_ID, PortraitIdentityLock
from .ports import (
    BASE_SOURCE_FILENAMES,
    PixelPortraitWorkspacePort,
    PixelWorkspaceInitialization,
)
from .release import (
    RuntimeReleaseError,
    build_runtime_release,
    synchronize_runtime,
)
from .service import PixelPortraitService, PixelPortraitWorkflowError

GeneratorFactory = Callable[[argparse.Namespace], ReferenceImageGeneratorPort]
Clock = Callable[[], datetime]
WorkspaceFactory = Callable[[Path], PixelPortraitWorkspacePort]

_PACKAGE_ID: Final[Literal["juana-talking-bust-v2-pixel"]] = "juana-talking-bust-v2-pixel"
_DEFAULT_MODEL = "gpt-image-2"
_DEFAULT_TIMEOUT_SECONDS = 180.0
_BASE_SOURCE_ARGUMENTS = (
    ("character_sheet", BASE_SOURCE_FILENAMES[0]),
    ("neutral", BASE_SOURCE_FILENAMES[1]),
    ("thinking", BASE_SOURCE_FILENAMES[2]),
    ("explaining", BASE_SOURCE_FILENAMES[3]),
    ("approval", BASE_SOURCE_FILENAMES[4]),
    ("doubt", BASE_SOURCE_FILENAMES[5]),
    ("error", BASE_SOURCE_FILENAMES[6]),
)
_RIGHTS_FIELDS = (
    "author",
    "rights_holder",
    "license",
    "commercial_use",
    "modification_allowed",
    "redistribution_allowed",
    "attribution",
)


class CliUsageError(ValueError):
    """Raised instead of terminating inside argparse."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Argument parser that lets the CLI serialize usage errors as JSON."""

    def error(self, message: str) -> Never:
        raise CliUsageError(message)


def _boolean(value: str) -> bool:
    normalized = value.casefold()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("Expected true or false.")


def _positive_float(value: str) -> float:
    try:
        parsed = float(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Expected a positive number.") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("Expected a positive number.")
    return parsed


def _add_workspace(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--workspace", type=Path, required=True)


def _add_rights(parser: argparse.ArgumentParser, *, required: bool) -> None:
    parser.add_argument("--author", required=required)
    parser.add_argument("--rights-holder", required=required)
    parser.add_argument("--license", required=required)
    parser.add_argument("--commercial-use", type=_boolean, required=required)
    parser.add_argument("--modification-allowed", type=_boolean, required=required)
    parser.add_argument("--redistribution-allowed", type=_boolean, required=required)
    parser.add_argument("--attribution", required=required)


def _add_panel_review(parser: argparse.ArgumentParser) -> None:
    _add_workspace(parser)
    parser.add_argument("--panel", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--reviewed-artifact", action="append", required=True)
    parser.add_argument("--approver", required=True)
    parser.add_argument("--notes", required=True)


def _parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="python -m vrm_ia_maker.design.pixel_portrait.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    _add_workspace(init)
    for destination, _filename in _BASE_SOURCE_ARGUMENTS:
        init.add_argument(
            f"--{destination.replace('_', '-')}",
            dest=destination,
            type=Path,
            required=True,
        )
    init.add_argument("--technical-package", type=Path, required=True)
    init.add_argument("--identity", required=True)
    init.add_argument("--revision", required=True)
    init.add_argument("--authoritative-source", required=True)
    _add_rights(init, required=False)

    set_rights = commands.add_parser("set-rights")
    _add_workspace(set_rights)
    set_rights.add_argument("--authoritative-source", required=True)
    _add_rights(set_rights, required=True)

    run = commands.add_parser("run")
    _add_workspace(run)
    run.add_argument("--provider", choices=("openai",), default="openai")
    run.add_argument("--model", default=_DEFAULT_MODEL)
    run.add_argument(
        "--timeout-seconds",
        type=_positive_float,
        default=_DEFAULT_TIMEOUT_SECONDS,
    )

    status = commands.add_parser("status")
    _add_workspace(status)

    approve_panel = commands.add_parser("approve-panel")
    _add_panel_review(approve_panel)
    approve_panel.add_argument("--identity-lock-json")

    for command_name in ("reject-panel", "supersede-panel"):
        _add_panel_review(commands.add_parser(command_name))

    approve_composite = commands.add_parser("approve-composite")
    _add_workspace(approve_composite)
    approve_composite.add_argument("--composite", required=True)
    approve_composite.add_argument(
        "--reviewed-artifact",
        action="append",
        required=True,
    )
    approve_composite.add_argument("--approver", required=True)
    approve_composite.add_argument("--notes", required=True)

    validate = commands.add_parser("validate")
    _add_workspace(validate)

    seal = commands.add_parser("seal")
    _add_workspace(seal)
    seal.add_argument("--output", type=Path, required=True)

    sync_runtime = commands.add_parser("sync-runtime")
    sync_runtime.add_argument("--source", type=Path, required=True)
    sync_runtime.add_argument("--destination", type=Path, required=True)

    package_runtime = commands.add_parser("package-runtime")
    package_runtime.add_argument("--source", type=Path, required=True)
    package_runtime.add_argument("--output", type=Path, required=True)
    package_runtime.add_argument("--lock", type=Path, required=True)
    package_runtime.add_argument("--version", required=True)
    return parser


def _validate_usage(args: argparse.Namespace) -> None:
    if args.command == "approve-panel":
        is_neutral = args.panel == NEUTRAL_PANEL_ID
        has_identity_lock = args.identity_lock_json is not None
        if is_neutral and not has_identity_lock:
            raise CliUsageError("--identity-lock-json is required when approving presence-neutral.")
        if not is_neutral and has_identity_lock:
            raise CliUsageError(
                "--identity-lock-json is allowed only when approving presence-neutral."
            )
    if args.command == "approve-composite" and len(args.reviewed_artifact) != 1:
        raise CliUsageError("approve-composite requires exactly one --reviewed-artifact.")


def _rights(args: argparse.Namespace) -> RightsMetadata | None:
    values = tuple(getattr(args, field) for field in _RIGHTS_FIELDS)
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise PixelPortraitWorkflowError(
            "incomplete_rights",
            "Every base-set rights field is required when rights are provided.",
        )
    return RightsMetadata(
        author=args.author,
        rights_holder=args.rights_holder,
        license=args.license,
        commercial_use=args.commercial_use,
        modification_allowed=args.modification_allowed,
        redistribution_allowed=args.redistribution_allowed,
        attribution=args.attribution,
    )


def _identity_lock(args: argparse.Namespace) -> PortraitIdentityLock | None:
    if args.command != "approve-panel" or args.identity_lock_json is None:
        return None
    return PortraitIdentityLock.model_validate_json(args.identity_lock_json)


def _default_generator(args: argparse.Namespace) -> ReferenceImageGeneratorPort:
    from ..adapters.openai_images import OpenAIImageGenerator

    return OpenAIImageGenerator(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )


def _serialize(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, dict):
        return {str(key): _serialize(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_serialize(item) for item in value]
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _write_json(stream: TextIO, payload: object) -> None:
    stream.write(json.dumps(payload, sort_keys=True) + "\n")


def _write_error(stream: TextIO, code: str, message: str) -> None:
    _write_json(
        stream,
        {"ok": False, "error": {"code": code, "message": message}},
    )


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    generator_factory: GeneratorFactory | None = None,
    clock: Clock | None = None,
    workspace_factory: WorkspaceFactory | None = None,
) -> int:
    """Execute one internal pixel portrait command and return a stable exit code."""
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    try:
        args = _parser().parse_args(argv)
        _validate_usage(args)
    except CliUsageError as exc:
        _write_error(errors, "usage_error", str(exc))
        return 2

    try:
        if args.command == "sync-runtime":
            release_result = synchronize_runtime(
                args.source,
                args.destination,
            ).as_dict()
            _write_json(
                output,
                {
                    "ok": True,
                    "command": args.command,
                    "result": release_result,
                },
            )
            return 0
        if args.command == "package-runtime":
            release_result = build_runtime_release(
                args.source,
                args.output,
                args.lock,
                version=args.version,
            )
            _write_json(
                output,
                {
                    "ok": True,
                    "command": args.command,
                    "result": release_result,
                },
            )
            return 0

        rights = _rights(args) if args.command in {"init", "set-rights"} else None
        identity_lock = _identity_lock(args)

        selected_workspace_factory = workspace_factory or FilesystemPixelPortraitWorkspace
        workspace = selected_workspace_factory(args.workspace)
        generator = None
        if args.command == "run":
            selected_generator_factory = generator_factory or _default_generator
            generator = selected_generator_factory(args)
        service = PixelPortraitService(
            workspace=workspace,
            generator=generator,
            clock=clock or (lambda: datetime.now(UTC)),
        )

        result: object
        if args.command == "init":
            result = service.initialize(
                PixelWorkspaceInitialization(
                    base_sources=tuple(
                        getattr(args, destination)
                        for destination, _filename in _BASE_SOURCE_ARGUMENTS
                    ),
                    technical_package=args.technical_package,
                    package_id=_PACKAGE_ID,
                    identity=args.identity,
                    revision=args.revision,
                    authoritative_source=args.authoritative_source,
                    base_rights=rights,
                )
            )
        elif args.command == "set-rights":
            if rights is None:
                raise PixelPortraitWorkflowError(
                    "incomplete_rights",
                    "Every base-set rights field is required.",
                )
            result = service.set_rights(
                rights,
                authoritative_source=args.authoritative_source,
            )
        elif args.command == "run":
            result = service.run()
        elif args.command == "status":
            result = service.status()
        elif args.command == "approve-panel":
            result = service.approve_panel(
                panel_id=args.panel,
                candidate_id=args.candidate,
                reviewed_artifacts=tuple(args.reviewed_artifact),
                approver=args.approver,
                notes=args.notes,
                identity_lock=identity_lock,
            )
        elif args.command == "reject-panel":
            result = service.reject_panel(
                panel_id=args.panel,
                candidate_id=args.candidate,
                reviewed_artifacts=tuple(args.reviewed_artifact),
                approver=args.approver,
                notes=args.notes,
            )
        elif args.command == "supersede-panel":
            result = service.supersede_panel(
                panel_id=args.panel,
                candidate_id=args.candidate,
                reviewed_artifacts=tuple(args.reviewed_artifact),
                approver=args.approver,
                notes=args.notes,
            )
        elif args.command == "approve-composite":
            result = service.approve_composite(
                composite_id=args.composite,
                reviewed_artifacts=tuple(args.reviewed_artifact),
                approver=args.approver,
                notes=args.notes,
            )
        elif args.command == "validate":
            result = service.validate()
        else:
            result = service.seal(args.output)

        _write_json(
            output,
            {"ok": True, "command": args.command, "result": _serialize(result)},
        )
        return 0
    except (
        PixelPortraitWorkflowError,
        AuthoringWorkspaceError,
        RuntimeReleaseError,
    ) as exc:
        _write_error(errors, exc.code, str(exc))
        return 3
    except ValidationError:
        _write_error(
            errors,
            "input_validation",
            "Command input failed contract validation.",
        )
        return 3
    except OSError:
        _write_error(
            errors,
            "filesystem_failure",
            "A filesystem operation failed.",
        )
        return 3
    except Exception:
        _write_error(
            errors,
            "unexpected_failure",
            "An unexpected local failure interrupted the pixel portrait workflow.",
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
