"""Tests for the local bounded-authoring workspace adapter."""

from __future__ import annotations

import hashlib
import io
import os
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from vrm_ia_maker.design.adapters.filesystem import (
    CandidateValidationError,
    FilesystemAuthoringWorkspace,
    WorkspaceAlreadyExistsError,
    WorkspaceLockedError,
    WorkspacePathError,
)
from vrm_ia_maker.design.contracts import AuthoringState, GapRecord, RightsMetadata
from vrm_ia_maker.design.plan import TALKING_BUST_PLAN
from vrm_ia_maker.design.ports import GeneratedImage, WorkspaceInitialization

NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def png_bytes(
    size: tuple[int, int],
    color: tuple[int, int, int] = (20, 40, 60),
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def grid_png_bytes() -> bytes:
    image = Image.new("RGB", (1536, 1024), "white")
    colors = [
        (255, 0, 0),
        (0, 255, 0),
        (0, 0, 255),
        (255, 255, 0),
        (255, 0, 255),
        (0, 255, 255),
    ]
    for index, color in enumerate(colors):
        column = index % 3
        row = index // 3
        image.paste(
            color,
            (column * 512, row * 512, (column + 1) * 512, (row + 1) * 512),
        )
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def initialization(master: Path) -> WorkspaceInitialization:
    return WorkspaceInitialization(
        master_source=master,
        package_id="juana-talking-bust",
        character_id="juana",
        display_name="Juana",
        revision="1.0.0",
        height_meters=1.70,
        authoritative_source="User-supplied repository concept sheet",
        rights=RightsMetadata(author="Katherine E. Aguirre"),
    )


def initialized_workspace(tmp_path: Path) -> tuple[FilesystemAuthoringWorkspace, AuthoringState]:
    master = tmp_path / "master-source.png"
    master.write_bytes(png_bytes((1200, 1600)))
    workspace = FilesystemAuthoringWorkspace(tmp_path / "workspace")
    state = workspace.initialize(initialization(master))
    return workspace, state


def test_initialize_copies_and_hashes_master_without_mutating_source(tmp_path: Path) -> None:
    master = tmp_path / "master-source.png"
    source_bytes = png_bytes((1200, 1600), (11, 22, 33))
    master.write_bytes(source_bytes)
    workspace = FilesystemAuthoringWorkspace(tmp_path / "workspace")

    state = workspace.initialize(initialization(master))

    assert master.read_bytes() == source_bytes
    assert state.revision.master_reference.path == "inputs/master.png"
    assert state.revision.master_reference.sha256 == hashlib.sha256(source_bytes).hexdigest()
    assert state.revision.master_reference.width == 1200
    assert state.revision.master_reference.height == 1600
    assert tuple(state.tasks) == tuple(task.task_id for task in TALKING_BUST_PLAN.tasks)
    assert workspace.load_state() == state
    assert workspace.resolve_artifact("inputs/master.png").read_bytes() == source_bytes
    assert (workspace.root / "authoring-plan.json").is_file()
    assert any(gap.gap_id == "source-rights-incomplete" for gap in state.gaps)


def test_initialize_refuses_an_existing_workspace(tmp_path: Path) -> None:
    master = tmp_path / "master.png"
    master.write_bytes(png_bytes((100, 100)))
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(WorkspaceAlreadyExistsError, match="already exists"):
        FilesystemAuthoringWorkspace(root).initialize(initialization(master))


def test_stage_candidate_validates_sheet_and_extracts_deterministic_previews(
    tmp_path: Path,
) -> None:
    workspace, state = initialized_workspace(tmp_path)
    task = TALKING_BUST_PLAN.task("face-turnaround")
    generated = GeneratedImage(
        data=grid_png_bytes(),
        provider="fake",
        model="fake-image-model",
    )

    candidate = workspace.stage_candidate(
        task=task,
        attempt=1,
        generated=generated,
        input_artifacts=(state.revision.master_reference,),
        created_at=NOW,
    )

    assert candidate.sheet.path == "candidates/face-turnaround/attempt-1/sheet.png"
    assert candidate.sheet.sha256 == hashlib.sha256(generated.data).hexdigest()
    assert len(candidate.previews) == 5
    assert candidate.previews[0].path.endswith("previews/neutral-front.png")
    assert candidate.previews[0].width == 512
    assert candidate.previews[0].height == 512
    with Image.open(workspace.resolve_artifact(candidate.previews[0].path)) as preview:
        assert preview.getpixel((256, 256)) == (255, 0, 0)
    with Image.open(workspace.resolve_artifact(candidate.previews[-1].path)) as preview:
        assert preview.getpixel((256, 256)) == (255, 0, 255)


@pytest.mark.parametrize(
    ("output", "message"),
    [
        (b"not a png", "valid PNG"),
        (png_bytes((1024, 1024)), "1536x1024"),
    ],
)
def test_stage_candidate_rejects_malformed_or_wrong_size_output_but_preserves_it(
    tmp_path: Path,
    output: bytes,
    message: str,
) -> None:
    workspace, state = initialized_workspace(tmp_path)

    with pytest.raises(CandidateValidationError, match=message):
        workspace.stage_candidate(
            task=TALKING_BUST_PLAN.task("face-turnaround"),
            attempt=1,
            generated=GeneratedImage(data=output, provider="fake", model="fake"),
            input_artifacts=(state.revision.master_reference,),
            created_at=NOW,
        )

    failed_output = workspace.root / "candidates/face-turnaround/attempt-1/failed-output.bin"
    assert failed_output.read_bytes() == output


def test_stage_candidate_never_overwrites_an_existing_attempt(tmp_path: Path) -> None:
    workspace, state = initialized_workspace(tmp_path)
    task = TALKING_BUST_PLAN.task("face-turnaround")
    generated = GeneratedImage(data=grid_png_bytes(), provider="fake", model="fake")
    candidate = workspace.stage_candidate(
        task=task,
        attempt=1,
        generated=generated,
        input_artifacts=(state.revision.master_reference,),
        created_at=NOW,
    )
    original = workspace.resolve_artifact(candidate.sheet.path).read_bytes()

    with pytest.raises(WorkspaceAlreadyExistsError, match="attempt already exists"):
        workspace.stage_candidate(
            task=task,
            attempt=1,
            generated=GeneratedImage(
                data=png_bytes((1536, 1024), (99, 88, 77)),
                provider="fake",
                model="fake",
            ),
            input_artifacts=(state.revision.master_reference,),
            created_at=NOW,
        )

    assert workspace.resolve_artifact(candidate.sheet.path).read_bytes() == original


def test_atomic_state_failure_leaves_prior_state_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, original = initialized_workspace(tmp_path)
    payload = original.model_dump(mode="json")
    payload["gaps"].append(
        GapRecord(
            gap_id="new-gap",
            area="test",
            description="Injected state change.",
            blocks_visual_seal=False,
        ).model_dump(mode="json")
    )
    changed = AuthoringState.model_validate(payload)

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(
        "vrm_ia_maker.design.adapters.filesystem.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="injected replace failure"):
        workspace.save_state(changed)

    assert workspace.load_state() == original
    assert not list(workspace.root.glob(".authoring-state.json.*.tmp"))


def test_workspace_lock_rejects_a_second_writer(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)

    with workspace.exclusive(), pytest.raises(
        WorkspaceLockedError,
        match="already locked",
    ), workspace.exclusive():
        pass

    with workspace.exclusive():
        pass


def test_stale_lock_file_does_not_block_process_recovery(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    (workspace.root / workspace.LOCK_FILE).write_text("stale owner", encoding="utf-8")

    with workspace.exclusive():
        assert (workspace.root / workspace.LOCK_FILE).is_file()


def test_resolve_artifact_rejects_symlink_escape(tmp_path: Path) -> None:
    workspace, _ = initialized_workspace(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace.root / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable in this environment: {exc}")

    with pytest.raises(WorkspacePathError, match="escapes the authoring workspace"):
        workspace.resolve_artifact("escape/file.png")
