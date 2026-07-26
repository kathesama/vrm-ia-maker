"""Tests for the internal pixel portrait authoring CLI."""

from __future__ import annotations

import io
import json
from argparse import Namespace
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

import pytest

from vrm_ia_maker.design.contracts import RightsMetadata
from vrm_ia_maker.design.pixel_portrait.cli import (
    GeneratorFactory,
    WorkspaceFactory,
    main,
)
from vrm_ia_maker.design.pixel_portrait.contracts import PortraitIdentityLock
from vrm_ia_maker.design.pixel_portrait.ports import (
    BASE_SOURCE_FILENAMES,
    PixelWorkspaceInitialization,
)
from vrm_ia_maker.design.pixel_portrait.service import PixelPortraitWorkflowError
from vrm_ia_maker.design.ports import (
    AuthoringWorkspaceError,
)

NOW = datetime(2026, 7, 22, 12, 0, tzinfo=UTC)


class RecordingService:
    """Record CLI-to-service calls without exercising filesystem policy."""

    instances: list[RecordingService] = []
    results: dict[str, object] = {}
    failure: Exception | None = None

    def __init__(
        self,
        *,
        workspace: object,
        generator: object,
        clock: Callable[[], datetime],
    ) -> None:
        self.workspace = workspace
        self.generator = generator
        self.clock = clock
        self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []
        type(self).instances.append(self)

    def _record(self, command: str, *args: object, **kwargs: object) -> object:
        self.calls.append((command, args, kwargs))
        failure = type(self).failure
        if failure is not None:
            raise failure
        return type(self).results.get(command, {"recorded": command})

    def initialize(self, command: object) -> object:
        return self._record("init", command)

    def set_rights(self, rights: object, *, authoritative_source: str) -> object:
        return self._record(
            "set-rights",
            rights,
            authoritative_source=authoritative_source,
        )

    def run(self) -> object:
        return self._record("run")

    def status(self) -> object:
        return self._record("status")

    def approve_panel(self, **kwargs: object) -> object:
        return self._record("approve-panel", **kwargs)

    def reject_panel(self, **kwargs: object) -> object:
        return self._record("reject-panel", **kwargs)

    def supersede_panel(self, **kwargs: object) -> object:
        return self._record("supersede-panel", **kwargs)

    def approve_composite(self, **kwargs: object) -> object:
        return self._record("approve-composite", **kwargs)

    def validate(self) -> object:
        return self._record("validate")

    def seal(self, destination: Path) -> object:
        return self._record("seal", destination)


@pytest.fixture(autouse=True)
def reset_recording_service(monkeypatch: pytest.MonkeyPatch) -> None:
    from vrm_ia_maker.design.pixel_portrait import cli

    RecordingService.instances = []
    RecordingService.results = {}
    RecordingService.failure = None
    monkeypatch.setattr(cli, "PixelPortraitService", RecordingService)


def invoke(
    arguments: list[str],
    *,
    generator_factory: Callable[[Namespace], object] | None = None,
    workspace_factory: Callable[[Path], object] | None = None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        arguments,
        stdout=stdout,
        stderr=stderr,
        generator_factory=cast(GeneratorFactory | None, generator_factory),
        workspace_factory=cast(
            WorkspaceFactory,
            workspace_factory or (lambda _root: object()),
        ),
        clock=lambda: NOW,
    )
    return exit_code, stdout.getvalue(), stderr.getvalue()


def init_arguments(workspace: Path) -> list[str]:
    source_root = workspace.parent / "base"
    return [
        "init",
        "--workspace",
        str(workspace),
        "--character-sheet",
        str(source_root / "juana-avatar-character-sheet.png"),
        "--neutral",
        str(source_root / "juana-avatar-neutral.png"),
        "--thinking",
        str(source_root / "juana-avatar-thinking.png"),
        "--explaining",
        str(source_root / "juana-avatar-explaining.png"),
        "--approval",
        str(source_root / "juana-avatar-approval.png"),
        "--doubt",
        str(source_root / "juana-avatar-doubt.png"),
        "--error",
        str(source_root / "juana-avatar-error.png"),
        "--technical-package",
        str(workspace.parent / "technical-package"),
        "--identity",
        "juana",
        "--revision",
        "2.0.0",
        "--authoritative-source",
        "Approved repository base set.",
    ]


def rights_arguments() -> list[str]:
    return [
        "--author",
        "Katherine E. Aguirre",
        "--rights-holder",
        "Katherine E. Aguirre",
        "--license",
        "Author-approved project use",
        "--commercial-use",
        "true",
        "--modification-allowed",
        "true",
        "--redistribution-allowed",
        "false",
        "--attribution",
        "Katherine E. Aguirre / Juana IA",
    ]


def identity_lock_json() -> str:
    return json.dumps(
        {
            "palette_sha256": "a" * 64,
            "palette_max_colors": 64,
            "pivot": {"x": 128, "y": 160},
            "eye_rect": {"x": 92, "y": 72, "width": 72, "height": 24},
            "mouth_rect": {"x": 100, "y": 130, "width": 56, "height": 20},
            "shoulders": [{"x": 72, "y": 230}, {"x": 184, "y": 230}],
            "face_top_y": 30,
            "chin_y": 190,
        }
    )


def panel_arguments(command: str, workspace: Path, *, neutral: bool = False) -> list[str]:
    panel_id = "presence-neutral" if neutral else "presence-thinking"
    arguments = [
        command,
        "--workspace",
        str(workspace),
        "--panel",
        panel_id,
        "--candidate",
        f"{panel_id}-candidate-1",
        "--reviewed-artifact",
        f"authoring/panels/{panel_id}/attempt-1/raw.png",
        "--reviewed-artifact",
        f"authoring/panels/{panel_id}/attempt-1/panel.png",
        "--reviewed-artifact",
        f"authoring/panels/{panel_id}/attempt-1/validation.json",
        "--approver",
        "Kathy",
        "--notes",
        "Reviewed every candidate artifact.",
    ]
    if command == "approve-panel" and neutral:
        arguments.extend(["--identity-lock-json", identity_lock_json()])
    return arguments


def test_init_dispatches_canonical_sources_and_stable_success_json(tmp_path: Path) -> None:
    workspace_root = tmp_path / "workspace"
    workspace = object()
    seen_roots: list[Path] = []

    def workspace_factory(root: Path) -> object:
        seen_roots.append(root)
        return workspace

    exit_code, stdout, stderr = invoke(
        init_arguments(workspace_root),
        workspace_factory=workspace_factory,
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout) == {
        "command": "init",
        "ok": True,
        "result": {"recorded": "init"},
    }
    assert seen_roots == [workspace_root]
    service = RecordingService.instances[-1]
    assert service.workspace is workspace
    assert service.generator is None
    command = cast(PixelWorkspaceInitialization, service.calls[0][1][0])
    assert command.package_id == "juana-talking-bust-v2-pixel"
    assert tuple(path.name for path in command.base_sources) == BASE_SOURCE_FILENAMES


def test_init_accepts_only_an_absent_or_complete_rights_bundle(tmp_path: Path) -> None:
    arguments = [*init_arguments(tmp_path / "workspace"), *rights_arguments()]

    exit_code, stdout, stderr = invoke(arguments)

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["ok"] is True
    command = cast(
        PixelWorkspaceInitialization,
        RecordingService.instances[-1].calls[0][1][0],
    )
    assert command.base_rights == RightsMetadata(
        author="Katherine E. Aguirre",
        rights_holder="Katherine E. Aguirre",
        license="Author-approved project use",
        commercial_use=True,
        modification_allowed=True,
        redistribution_allowed=False,
        attribution="Katherine E. Aguirre / Juana IA",
    )

    exit_code, stdout, stderr = invoke([*init_arguments(tmp_path / "partial"), "--author", "Kathy"])

    assert exit_code == 3
    assert stdout == ""
    assert json.loads(stderr) == {
        "error": {
            "code": "incomplete_rights",
            "message": "Every base-set rights field is required when rights are provided.",
        },
        "ok": False,
    }


def test_set_rights_dispatches_complete_metadata_and_serializes_model_sequences(
    tmp_path: Path,
) -> None:
    rights = RightsMetadata(
        author="Katherine E. Aguirre",
        rights_holder="Katherine E. Aguirre",
        license="Author-approved project use",
        commercial_use=True,
        modification_allowed=True,
        redistribution_allowed=False,
        attribution="Katherine E. Aguirre / Juana IA",
    )
    RecordingService.results["set-rights"] = (rights,)

    exit_code, stdout, stderr = invoke(
        [
            "set-rights",
            "--workspace",
            str(tmp_path / "workspace"),
            "--authoritative-source",
            "Approved repository base set.",
            *rights_arguments(),
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    payload = json.loads(stdout)
    assert payload["command"] == "set-rights"
    assert payload["result"] == [rights.model_dump(mode="json")]
    _, positional, keywords = RecordingService.instances[-1].calls[-1]
    assert positional == (rights,)
    assert keywords == {"authoritative_source": "Approved repository base set."}


def test_run_is_the_only_command_that_constructs_a_generator(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    generator = object()
    received: list[Namespace] = []

    def generator_factory(args: Namespace) -> object:
        received.append(args)
        return generator

    exit_code, stdout, stderr = invoke(
        [
            "run",
            "--workspace",
            str(workspace),
            "--provider",
            "openai",
            "--model",
            "gpt-image-test",
            "--timeout-seconds",
            "42.5",
        ],
        generator_factory=generator_factory,
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"] == {"recorded": "run"}
    assert len(received) == 1
    assert received[0].provider == "openai"
    assert received[0].model == "gpt-image-test"
    assert received[0].timeout_seconds == 42.5

    exit_code, stdout, stderr = invoke(
        ["run", "--workspace", str(workspace)],
        generator_factory=generator_factory,
    )
    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"] == {"recorded": "run"}
    assert len(received) == 2
    assert received[1].provider == "openai"
    assert received[1].model == "gpt-image-2"
    assert received[1].timeout_seconds == 180.0

    service = RecordingService.instances[-1]
    assert service.generator is generator
    assert service.clock() == NOW

    def forbidden_factory(_args: Namespace) -> object:
        raise AssertionError("Provider construction is forbidden for this command.")

    for arguments in (
        init_arguments(workspace),
        [
            "set-rights",
            "--workspace",
            str(workspace),
            "--authoritative-source",
            "Approved repository base set.",
            *rights_arguments(),
        ],
        ["status", "--workspace", str(workspace)],
        ["validate", "--workspace", str(workspace)],
        ["seal", "--workspace", str(workspace), "--output", str(tmp_path / "package")],
        panel_arguments("approve-panel", workspace, neutral=True),
        panel_arguments("reject-panel", workspace),
        panel_arguments("supersede-panel", workspace),
        [
            "approve-composite",
            "--workspace",
            str(workspace),
            "--composite",
            "presence-composite-v1",
            "--reviewed-artifact",
            "authoring/composites/presence-v1.png",
            "--approver",
            "Kathy",
            "--notes",
            "Reviewed the complete family sheet.",
        ],
    ):
        assert invoke(arguments, generator_factory=forbidden_factory)[0] == 0


@pytest.mark.parametrize(
    "command",
    ["approve-panel", "reject-panel", "supersede-panel"],
)
def test_panel_decisions_dispatch_exact_review_arguments(
    command: str,
    tmp_path: Path,
) -> None:
    neutral = command == "approve-panel"
    arguments = panel_arguments(command, tmp_path / "workspace", neutral=neutral)

    exit_code, stdout, stderr = invoke(arguments)

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["command"] == command
    _, positional, keywords = RecordingService.instances[-1].calls[-1]
    assert positional == ()
    panel_id = "presence-neutral" if neutral else "presence-thinking"
    assert keywords == {
        "panel_id": panel_id,
        "candidate_id": f"{panel_id}-candidate-1",
        "reviewed_artifacts": (
            f"authoring/panels/{panel_id}/attempt-1/raw.png",
            f"authoring/panels/{panel_id}/attempt-1/panel.png",
            f"authoring/panels/{panel_id}/attempt-1/validation.json",
        ),
        "approver": "Kathy",
        "notes": "Reviewed every candidate artifact.",
        **(
            {"identity_lock": PortraitIdentityLock.model_validate_json(identity_lock_json())}
            if command == "approve-panel"
            else {}
        ),
    }


def test_composite_approval_dispatches_exactly_one_reviewed_artifact(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    artifact = "authoring/composites/presence-v1.png"

    exit_code, stdout, stderr = invoke(
        [
            "approve-composite",
            "--workspace",
            str(workspace),
            "--composite",
            "presence-composite-v1",
            "--reviewed-artifact",
            artifact,
            "--approver",
            "Kathy",
            "--notes",
            "Reviewed the complete family sheet.",
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["command"] == "approve-composite"
    assert RecordingService.instances[-1].calls[-1] == (
        "approve-composite",
        (),
        {
            "composite_id": "presence-composite-v1",
            "reviewed_artifacts": (artifact,),
            "approver": "Kathy",
            "notes": "Reviewed the complete family sheet.",
        },
    )

    exit_code, stdout, stderr = invoke(
        [
            "approve-composite",
            "--workspace",
            str(workspace),
            "--composite",
            "presence-composite-v1",
            "--reviewed-artifact",
            artifact,
            "--reviewed-artifact",
            "authoring/composites/extra.png",
            "--approver",
            "Kathy",
            "--notes",
            "Invalid review scope.",
        ]
    )
    assert exit_code == 2
    assert stdout == ""
    assert json.loads(stderr)["error"]["code"] == "usage_error"


@pytest.mark.parametrize(
    ("command", "expected_result"),
    [
        ("status", {"recorded": "status"}),
        ("validate", {"recorded": "validate"}),
    ],
)
def test_provider_free_queries_emit_success_envelopes(
    command: str,
    expected_result: object,
    tmp_path: Path,
) -> None:
    exit_code, stdout, stderr = invoke([command, "--workspace", str(tmp_path / "workspace")])

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout) == {
        "command": command,
        "ok": True,
        "result": expected_result,
    }


def test_seal_delegates_explicit_output_path(tmp_path: Path) -> None:
    destination = tmp_path / "sealed-package"

    exit_code, stdout, stderr = invoke(
        [
            "seal",
            "--workspace",
            str(tmp_path / "workspace"),
            "--output",
            str(destination),
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["command"] == "seal"
    assert RecordingService.instances[-1].calls[-1] == (
        "seal",
        (destination,),
        {},
    )


def test_usage_errors_are_one_json_line_on_stderr() -> None:
    exit_code, stdout, stderr = invoke(["status"])

    assert exit_code == 2
    assert stdout == ""
    assert stderr.count("\n") == 1
    payload = json.loads(stderr)
    assert payload["ok"] is False
    assert payload["error"]["code"] == "usage_error"
    assert payload["error"]["message"]
    assert not stderr.startswith("usage:")


def test_identity_lock_is_strict_required_for_neutral_and_forbidden_elsewhere(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"

    exit_code, stdout, stderr = invoke(
        panel_arguments("approve-panel", workspace, neutral=True)[:-2]
    )
    assert exit_code == 2
    assert stdout == ""
    assert json.loads(stderr)["error"]["code"] == "usage_error"

    invalid = panel_arguments("approve-panel", workspace, neutral=True)
    invalid[-1] = json.dumps({"palette_sha256": "secret-invalid-payload"})
    exit_code, stdout, stderr = invoke(invalid)
    assert exit_code == 3
    assert stdout == ""
    assert json.loads(stderr) == {
        "error": {
            "code": "input_validation",
            "message": "Command input failed contract validation.",
        },
        "ok": False,
    }
    assert "secret-invalid-payload" not in stderr

    non_neutral = panel_arguments("approve-panel", workspace)
    non_neutral.extend(["--identity-lock-json", identity_lock_json()])
    exit_code, stdout, stderr = invoke(non_neutral)
    assert exit_code == 2
    assert stdout == ""
    assert json.loads(stderr)["error"]["code"] == "usage_error"

    for command in ("reject-panel", "supersede-panel"):
        forbidden = panel_arguments(command, workspace)
        forbidden.extend(["--identity-lock-json", identity_lock_json()])
        exit_code, stdout, stderr = invoke(forbidden)
        assert exit_code == 2
        assert stdout == ""
        assert json.loads(stderr)["error"]["code"] == "usage_error"


@pytest.mark.parametrize(
    ("failure", "expected_code", "expected_message"),
    [
        (
            PixelPortraitWorkflowError("workflow_blocked", "Safe workflow message."),
            "workflow_blocked",
            "Safe workflow message.",
        ),
        (
            AuthoringWorkspaceError("workspace_blocked", "Safe workspace message."),
            "workspace_blocked",
            "Safe workspace message.",
        ),
        (
            OSError("C:/private/source.png secret"),
            "filesystem_failure",
            "A filesystem operation failed.",
        ),
        (
            RuntimeError("OPENAI_API_KEY=secret remote raw response"),
            "unexpected_failure",
            "An unexpected local failure interrupted the pixel portrait workflow.",
        ),
    ],
)
def test_operational_errors_use_sanitized_stderr_envelopes(
    failure: Exception,
    expected_code: str,
    expected_message: str,
    tmp_path: Path,
) -> None:
    RecordingService.failure = failure

    exit_code, stdout, stderr = invoke(["status", "--workspace", str(tmp_path / "workspace")])

    assert exit_code == 3
    assert stdout == ""
    assert stderr.count("\n") == 1
    assert json.loads(stderr) == {
        "error": {"code": expected_code, "message": expected_message},
        "ok": False,
    }
    if expected_code in {"filesystem_failure", "unexpected_failure"}:
        assert "secret" not in stderr
        assert "OPENAI_API_KEY" not in stderr


def test_unexpected_generator_factory_failure_never_leaks_provider_details(
    tmp_path: Path,
) -> None:
    def failing_factory(_args: Namespace) -> object:
        raise RuntimeError("OPENAI_API_KEY=top-secret provider response body")

    exit_code, stdout, stderr = invoke(
        ["run", "--workspace", str(tmp_path / "workspace")],
        generator_factory=failing_factory,
    )

    assert exit_code == 3
    assert stdout == ""
    assert json.loads(stderr)["error"] == {
        "code": "unexpected_failure",
        "message": "An unexpected local failure interrupted the pixel portrait workflow.",
    }
    assert "top-secret" not in stderr
    assert "OPENAI_API_KEY" not in stderr
