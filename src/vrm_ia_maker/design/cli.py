"""Internal JSON CLI for bounded character-reference authoring."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Never, TextIO

from pydantic import BaseModel, ValidationError

from vrm_ia_maker.design.adapters.filesystem import (
    FilesystemAuthoringWorkspace,
    WorkspaceError,
)
from vrm_ia_maker.design.adapters.openai_images import OpenAIImageGenerator
from vrm_ia_maker.design.contracts import RightsMetadata
from vrm_ia_maker.design.ports import ReferenceImageGeneratorPort, WorkspaceInitialization
from vrm_ia_maker.design.service import AuthoringService, AuthoringWorkflowError

GeneratorFactory = Callable[[argparse.Namespace], ReferenceImageGeneratorPort]
Clock = Callable[[], datetime]


class CliUsageError(ValueError):
    """Raised instead of terminating inside argparse."""


class JsonArgumentParser(argparse.ArgumentParser):
    """Argument parser that lets the CLI serialize usage errors as JSON."""

    def error(self, message: str) -> Never:
        raise CliUsageError(message)


def _boolean(value: str) -> bool:
    normalized = value.lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise argparse.ArgumentTypeError("Expected true or false.")


def _parser() -> JsonArgumentParser:
    parser = JsonArgumentParser(prog="python -m vrm_ia_maker.design.cli")
    commands = parser.add_subparsers(dest="command", required=True)

    init = commands.add_parser("init")
    init.add_argument("--workspace", type=Path, required=True)
    init.add_argument("--master", type=Path, required=True)
    init.add_argument("--package-id", required=True)
    init.add_argument("--character-id", required=True)
    init.add_argument("--display-name", required=True)
    init.add_argument("--revision", required=True)
    init.add_argument("--height-meters", type=float)
    init.add_argument("--authoritative-source", required=True)
    init.add_argument("--author")
    init.add_argument("--rights-holder")
    init.add_argument("--license")
    init.add_argument("--commercial-use", type=_boolean)
    init.add_argument("--modification-allowed", type=_boolean)
    init.add_argument("--redistribution-allowed", type=_boolean)
    init.add_argument("--attribution")

    set_rights = commands.add_parser("set-rights")
    set_rights.add_argument("--workspace", type=Path, required=True)
    set_rights.add_argument("--authoritative-source", required=True)
    set_rights.add_argument("--author", required=True)
    set_rights.add_argument("--rights-holder", required=True)
    set_rights.add_argument("--license", required=True)
    set_rights.add_argument("--commercial-use", type=_boolean, required=True)
    set_rights.add_argument("--modification-allowed", type=_boolean, required=True)
    set_rights.add_argument("--redistribution-allowed", type=_boolean, required=True)
    set_rights.add_argument("--attribution", required=True)

    run = commands.add_parser("run")
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--provider", choices=("openai",), default="openai")
    run.add_argument("--model", default="gpt-image-2")
    run.add_argument("--timeout-seconds", type=float, default=180.0)

    status = commands.add_parser("status")
    status.add_argument("--workspace", type=Path, required=True)

    for command_name in ("approve", "reject", "supersede"):
        decision = commands.add_parser(command_name)
        decision.add_argument("--workspace", type=Path, required=True)
        decision.add_argument("--task", required=True)
        decision.add_argument("--candidate", required=True)
        decision.add_argument("--approver", required=True)
        decision.add_argument("--notes", required=True)

    validate = commands.add_parser("validate")
    validate.add_argument("--workspace", type=Path, required=True)

    seal = commands.add_parser("seal")
    seal.add_argument("--workspace", type=Path, required=True)
    seal.add_argument("--output", type=Path, required=True)
    return parser


def _rights(args: argparse.Namespace) -> RightsMetadata | None:
    values = (
        args.author,
        args.rights_holder,
        args.license,
        args.commercial_use,
        args.modification_allowed,
        args.redistribution_allowed,
        args.attribution,
    )
    if all(value is None for value in values):
        return None
    return RightsMetadata(
        author=args.author,
        rights_holder=args.rights_holder,
        license=args.license,
        commercial_use=args.commercial_use,
        modification_allowed=args.modification_allowed,
        redistribution_allowed=args.redistribution_allowed,
        attribution=args.attribution,
    )


def _default_generator(args: argparse.Namespace) -> ReferenceImageGeneratorPort:
    return OpenAIImageGenerator(
        model=args.model,
        timeout_seconds=args.timeout_seconds,
    )


def _serialize(value: object) -> object:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return value


def _write_json(stream: TextIO, payload: object) -> None:
    stream.write(json.dumps(payload, sort_keys=True) + "\n")


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    generator_factory: GeneratorFactory | None = None,
    clock: Clock | None = None,
) -> int:
    """Execute one internal authoring command and return a stable exit code."""
    output = stdout or sys.stdout
    errors = stderr or sys.stderr
    try:
        args = _parser().parse_args(argv)
    except CliUsageError as exc:
        _write_json(
            errors,
            {"ok": False, "error": {"code": "usage_error", "message": str(exc)}},
        )
        return 2

    try:
        workspace = FilesystemAuthoringWorkspace(args.workspace)
        selected_clock = clock or (lambda: datetime.now(UTC))
        generator = None
        if args.command == "run":
            factory = generator_factory or _default_generator
            generator = factory(args)
        service = AuthoringService(
            workspace=workspace,
            generator=generator,
            clock=selected_clock,
        )
        result: object
        if args.command == "init":
            result = service.initialize(
                WorkspaceInitialization(
                    master_source=args.master,
                    package_id=args.package_id,
                    character_id=args.character_id,
                    display_name=args.display_name,
                    revision=args.revision,
                    height_meters=args.height_meters,
                    authoritative_source=args.authoritative_source,
                    rights=_rights(args),
                )
            )
        elif args.command == "set-rights":
            rights = _rights(args)
            if rights is None:
                raise AuthoringWorkflowError(
                    "incomplete_rights",
                    "Every master-source rights field is required.",
                )
            result = service.set_rights(
                rights,
                authoritative_source=args.authoritative_source,
            )
        elif args.command == "run":
            result = service.run()
        elif args.command == "status":
            result = service.status()
        elif args.command == "approve":
            result = service.approve(
                task_id=args.task,
                candidate_id=args.candidate,
                approver=args.approver,
                notes=args.notes,
            )
        elif args.command == "reject":
            result = service.reject(
                task_id=args.task,
                candidate_id=args.candidate,
                approver=args.approver,
                notes=args.notes,
            )
        elif args.command == "supersede":
            result = service.supersede(
                task_id=args.task,
                candidate_id=args.candidate,
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
    except (AuthoringWorkflowError, WorkspaceError) as exc:
        _write_json(
            errors,
            {"ok": False, "error": {"code": exc.code, "message": str(exc)}},
        )
        return 3
    except ValidationError:
        _write_json(
            errors,
            {
                "ok": False,
                "error": {
                    "code": "input_validation",
                    "message": "Command input failed contract validation.",
                },
            },
        )
        return 3
    except OSError:
        _write_json(
            errors,
            {
                "ok": False,
                "error": {
                    "code": "filesystem_failure",
                    "message": "A filesystem operation failed.",
                },
            },
        )
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
