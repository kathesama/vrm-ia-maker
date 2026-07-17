"""Tests for the internal bounded-reference authoring CLI."""

from __future__ import annotations

import io
import json
from argparse import Namespace
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from vrm_ia_maker.design.adapters.filesystem import FilesystemAuthoringWorkspace
from vrm_ia_maker.design.cli import main
from vrm_ia_maker.design.plan import TALKING_BUST_PLAN
from vrm_ia_maker.design.ports import (
    GeneratedImage,
    GenerationRequest,
    ImageGenerationError,
)
from vrm_ia_maker.design.service import AuthoringService

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def write_png(path: Path, size: tuple[int, int] = (1200, 1600)) -> None:
    Image.new("RGB", size, (40, 80, 120)).save(path, format="PNG")


class RequestSizedGenerator:
    def __init__(self) -> None:
        self.requests: list[GenerationRequest] = []

    def generate(self, request: GenerationRequest) -> GeneratedImage:
        self.requests.append(request)
        buffer = io.BytesIO()
        Image.new("RGB", (request.width, request.height), (30, 60, 90)).save(
            buffer,
            format="PNG",
        )
        return GeneratedImage(
            data=buffer.getvalue(),
            provider="fake",
            model="fake-image-model",
        )


class FailingGenerator:
    def generate(self, request: GenerationRequest) -> GeneratedImage:
        raise ImageGenerationError("provider_failure", "Image provider failed.")


def invoke(
    arguments: list[str],
    *,
    generator_factory: object | None = None,
) -> tuple[int, str, str]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    exit_code = main(
        arguments,
        stdout=stdout,
        stderr=stderr,
        generator_factory=generator_factory,
        clock=lambda: NOW,
    )
    return exit_code, stdout.getvalue(), stderr.getvalue()


def init_arguments(workspace: Path, master: Path, *, complete_rights: bool = False) -> list[str]:
    arguments = [
        "init",
        "--workspace",
        str(workspace),
        "--master",
        str(master),
        "--package-id",
        "juana-talking-bust",
        "--character-id",
        "juana",
        "--display-name",
        "Juana",
        "--revision",
        "1.0.0",
        "--height-meters",
        "1.70",
        "--authoritative-source",
        "User-supplied repository concept sheet",
    ]
    if complete_rights:
        arguments.extend(
            [
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
                "true",
                "--attribution",
                "Katherine E. Aguirre / Juana IA",
            ]
        )
    return arguments


def set_rights_arguments(workspace: Path) -> list[str]:
    return [
        "set-rights",
        "--workspace",
        str(workspace),
        "--authoritative-source",
        "OpenAI ChatGPT image generation directed by Katherine E. Aguirre.",
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
        "true",
        "--attribution",
        "Katherine E. Aguirre / Juana IA",
    ]


def test_init_status_run_approve_and_validate_emit_stable_json(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    workspace = tmp_path / "workspace"
    write_png(master)

    exit_code, stdout, stderr = invoke(init_arguments(workspace, master))

    assert exit_code == 0
    assert stderr == ""
    initialized = json.loads(stdout)
    assert initialized["ok"] is True
    assert initialized["command"] == "init"
    assert initialized["result"]["revision"]["character_id"] == "juana"

    generator = RequestSizedGenerator()

    def factory(_: Namespace) -> RequestSizedGenerator:
        return generator

    exit_code, stdout, stderr = invoke(
        ["run", "--workspace", str(workspace), "--provider", "openai"],
        generator_factory=factory,
    )
    assert exit_code == 0
    assert stderr == ""
    generated = json.loads(stdout)
    assert generated["result"]["task_id"] == "face-turnaround"
    candidate_id = generated["result"]["candidate"]["candidate_id"]
    assert len(generator.requests) == 1

    exit_code, stdout, stderr = invoke(
        [
            "approve",
            "--workspace",
            str(workspace),
            "--task",
            "face-turnaround",
            "--candidate",
            candidate_id,
            "--approver",
            "Kathy",
            "--notes",
            "Approved every artifact.",
        ]
    )
    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"]["decision"] == "approve"

    exit_code, stdout, stderr = invoke(["status", "--workspace", str(workspace)])
    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"]["tasks"]["face-turnaround"]["progress"] == "approved"

    exit_code, stdout, stderr = invoke(["validate", "--workspace", str(workspace)])
    assert exit_code == 0
    assert stderr == ""
    validation = json.loads(stdout)["result"]
    assert validation["valid"] is True
    assert validation["sealable"] is False
    assert "facial-mechanics" in validation["incomplete_tasks"]


def test_set_rights_command_completes_existing_workspace_metadata(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    workspace = tmp_path / "workspace"
    write_png(master)
    assert invoke(init_arguments(workspace, master))[0] == 0

    exit_code, stdout, stderr = invoke(set_rights_arguments(workspace))

    assert exit_code == 0
    assert stderr == ""
    result = json.loads(stdout)["result"]
    assert result["provenance_id"] == "master-reference"
    assert result["authoritative_source"].startswith("OpenAI ChatGPT")
    assert result["rights"]["rights_holder"] == "Katherine E. Aguirre"
    state = FilesystemAuthoringWorkspace(workspace).load_state()
    assert "source-rights-incomplete" not in {gap.gap_id for gap in state.gaps}


def test_reject_command_preserves_auditable_state(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    workspace = tmp_path / "workspace"
    write_png(master)
    assert invoke(init_arguments(workspace, master))[0] == 0
    generated = json.loads(
        invoke(
            ["run", "--workspace", str(workspace), "--provider", "openai"],
            generator_factory=lambda _: RequestSizedGenerator(),
        )[1]
    )
    candidate_id = generated["result"]["candidate"]["candidate_id"]

    exit_code, stdout, stderr = invoke(
        [
            "reject",
            "--workspace",
            str(workspace),
            "--task",
            "face-turnaround",
            "--candidate",
            candidate_id,
            "--approver",
            "Kathy",
            "--notes",
            "Profile mismatch.",
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"]["decision"] == "reject"
    assert (
        FilesystemAuthoringWorkspace(workspace)
        .load_state()
        .tasks["face-turnaround"]
        .progress.value
        == "retry_ready"
    )


def test_supersede_command_reopens_an_approved_task(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    workspace = tmp_path / "workspace"
    write_png(master)
    assert invoke(init_arguments(workspace, master))[0] == 0
    generated = json.loads(
        invoke(
            ["run", "--workspace", str(workspace), "--provider", "openai"],
            generator_factory=lambda _: RequestSizedGenerator(),
        )[1]
    )
    candidate_id = generated["result"]["candidate"]["candidate_id"]
    assert invoke(
        [
            "approve",
            "--workspace",
            str(workspace),
            "--task",
            "face-turnaround",
            "--candidate",
            candidate_id,
            "--approver",
            "Kathy",
            "--notes",
            "Approved before the visual direction changed.",
        ]
    )[0] == 0

    exit_code, stdout, stderr = invoke(
        [
            "supersede",
            "--workspace",
            str(workspace),
            "--task",
            "face-turnaround",
            "--candidate",
            candidate_id,
            "--approver",
            "Kathy",
            "--notes",
            "Superseded by corrected visual canon.",
        ]
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"]["decision"] == "supersede"
    task = FilesystemAuthoringWorkspace(workspace).load_state().tasks["face-turnaround"]
    assert task.progress.value == "retry_ready"
    assert task.approved_candidate_id is None


def test_seal_command_publishes_completed_workspace(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    workspace_root = tmp_path / "workspace"
    destination = tmp_path / "package"
    write_png(master)
    assert invoke(init_arguments(workspace_root, master, complete_rights=True))[0] == 0
    workspace = FilesystemAuthoringWorkspace(workspace_root)
    service = AuthoringService(
        workspace=workspace,
        generator=RequestSizedGenerator(),
        clock=lambda: NOW,
    )
    for expected_task in TALKING_BUST_PLAN.tasks:
        result = service.run()
        assert result.task_id == expected_task.task_id
        service.approve(
            task_id=result.task_id,
            candidate_id=result.candidate.candidate_id,
            approver="Kathy",
            notes="Approved every generated artifact.",
        )

    exit_code, stdout, stderr = invoke(
        ["seal", "--workspace", str(workspace_root), "--output", str(destination)]
    )

    assert exit_code == 0
    assert stderr == ""
    assert json.loads(stdout)["result"]["package_id"] == "juana-talking-bust"
    assert (destination / "seal.json").is_file()


def test_provider_error_uses_nonzero_exit_and_never_prints_secret(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    workspace = tmp_path / "workspace"
    write_png(master)
    assert invoke(init_arguments(workspace, master))[0] == 0

    exit_code, stdout, stderr = invoke(
        ["run", "--workspace", str(workspace), "--provider", "openai"],
        generator_factory=lambda _: FailingGenerator(),
    )

    assert exit_code == 3
    assert stdout == ""
    error = json.loads(stderr)
    assert error == {
        "error": {"code": "provider_failure", "message": "Image provider failed."},
        "ok": False,
    }
    assert "OPENAI_API_KEY" not in stderr


def test_usage_errors_are_json_and_nonzero() -> None:
    exit_code, stdout, stderr = invoke(["run"])

    assert exit_code == 2
    assert stdout == ""
    error = json.loads(stderr)
    assert error["ok"] is False
    assert error["error"]["code"] == "usage_error"
    assert error["error"]["message"]
