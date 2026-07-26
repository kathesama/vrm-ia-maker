"""Tests for the panel-first pixel portrait filesystem boundary."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
from datetime import UTC, datetime
from inspect import Parameter, signature
from pathlib import Path

import pytest
from PIL import Image
from pydantic import ValidationError

from vrm_ia_maker.design.adapters.filesystem import (
    CandidateValidationError,
    FilesystemAuthoringWorkspace,
    PackageDestinationExistsError,
    PackageIntegrityError,
    PackageSealError,
    WorkspaceAlreadyExistsError,
    WorkspaceError,
    WorkspaceLockedError,
    WorkspacePathError,
)
from vrm_ia_maker.design.contracts import (
    ApprovalDecision,
    ArtifactEvidence,
    CandidateStatus,
    GapRecord,
    GenerationAttempt,
    GenerationAttemptStatus,
    ProvenanceRecord,
    RightsMetadata,
    SealEvidence,
    SourceClass,
)
from vrm_ia_maker.design.pixel_portrait.adapters.filesystem import (
    FilesystemPixelPortraitWorkspace,
)
from vrm_ia_maker.design.pixel_portrait.contracts import (
    PACKAGE_MASTER_PATH,
    CompositeApproval,
    CompositeReviewSheet,
    CompositeScope,
    CompositeStatus,
    LogicalPoint,
    LogicalRect,
    PanelProgress,
    PixelPanelApproval,
    PixelPanelCandidate,
    PixelPanelState,
    PixelPortraitAuthoringState,
    PortraitIdentityLock,
)
from vrm_ia_maker.design.pixel_portrait.plan import PIXEL_PORTRAIT_PLAN
from vrm_ia_maker.design.pixel_portrait.ports import (
    BASE_SOURCE_FILENAMES,
    PixelPortraitWorkspacePort,
    PixelWorkspaceInitialization,
)
from vrm_ia_maker.design.ports import GeneratedImage

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
TECHNICAL_PACKAGE_DIRECTORIES = (
    "references/master",
    "references/body",
    "references/face",
    "references/expressions",
    "references/visemes",
    "references/hair",
    "references/outfit",
    "references/materials",
    "measurements",
    "landmarks",
    "palette",
    "materials",
    "expressions",
    "visemes",
    "hair",
    "outfit",
    "assets/base",
    "assets/hair",
    "assets/outfit",
    "assets/accessories",
    "adapters",
)
TECHNICAL_PROVENANCE_PREFIX = "talking-bust-v1:"


def png_bytes(
    size: tuple[int, int],
    color: tuple[int, int, int, int] = (20, 40, 60, 255),
) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", size, color).save(buffer, format="PNG")
    return buffer.getvalue()


def gradient_png_bytes() -> bytes:
    horizontal = Image.linear_gradient("L").rotate(90, expand=False)
    horizontal = horizontal.resize((1024, 1024), Image.Resampling.BILINEAR)
    vertical = Image.linear_gradient("L").resize(
        (1024, 1024),
        Image.Resampling.BILINEAR,
    )
    blue = Image.new("L", (1024, 1024), 127)
    alpha = Image.new("L", (1024, 1024), 255)
    image = Image.merge("RGBA", (horizontal, vertical, blue, alpha))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    return buffer.getvalue()


def complete_rights() -> RightsMetadata:
    return RightsMetadata(
        author="Synthetic fixture author",
        rights_holder="Synthetic fixture owner",
        license="CC-BY-4.0",
        commercial_use=True,
        modification_allowed=True,
        redistribution_allowed=True,
        attribution="Synthetic fixture author",
    )


def create_base_sources(tmp_path: Path) -> tuple[Path, ...]:
    source_root = tmp_path / "base-set"
    source_root.mkdir()
    paths: list[Path] = []
    for index, filename in enumerate(BASE_SOURCE_FILENAMES):
        path = source_root / filename
        path.write_bytes(
            png_bytes(
                (64 + index, 80 + index),
                (10 + index, 20 + index, 30 + index, 255),
            )
        )
        paths.append(path)
    return tuple(paths)


def technical_source_paths() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                panel.technical_source_path
                for panel in PIXEL_PORTRAIT_PLAN.panels
                if panel.technical_source_path is not None
            }
        )
    )


def artifact_evidence(
    path: str,
    data: bytes,
    *,
    width: int = 512,
    height: int = 512,
) -> ArtifactEvidence:
    return ArtifactEvidence(
        path=path,
        sha256=hashlib.sha256(data).hexdigest(),
        byte_length=len(data),
        width=width,
        height=height,
    )


def write_technical_provenance(
    package: Path,
    records: tuple[ProvenanceRecord, ...],
) -> None:
    payload = {
        "schema_version": "1.0",
        "records": [record.model_dump(mode="json") for record in records],
    }
    (package / "provenance.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def seal_technical_package(
    package: Path,
    provenance_ids: tuple[str, ...],
) -> SealEvidence:
    files = sorted(
        path for path in package.rglob("*") if path.is_file() and path.name != "seal.json"
    )
    evidence = SealEvidence(
        package_id="juana-talking-bust-v1",
        revision="2026-07-16-gh-19-r2",
        sealed_at=NOW,
        file_hashes={
            path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in files
        },
        approval_ids=("approval-source-package",),
        provenance_ids=provenance_ids,
    )
    (package / "seal.json").write_text(evidence.model_dump_json(), encoding="utf-8")
    return evidence


def replace_technical_provenance(
    package: Path,
    records: tuple[ProvenanceRecord, ...],
) -> SealEvidence:
    write_technical_provenance(package, records)
    return seal_technical_package(
        package,
        tuple(record.provenance_id for record in records),
    )


def technical_provenance_records(package: Path) -> tuple[ProvenanceRecord, ...]:
    payload = json.loads((package / "provenance.json").read_text(encoding="utf-8"))
    return tuple(ProvenanceRecord.model_validate(record) for record in payload["records"])


def create_technical_package(tmp_path: Path) -> tuple[Path, SealEvidence]:
    package = tmp_path / "technical-package"
    package.mkdir()
    for relative in TECHNICAL_PACKAGE_DIRECTORIES:
        (package / relative).mkdir(parents=True, exist_ok=True)
    metadata = {
        "package.json": b'{"package_id":"juana-talking-bust-v1"}\n',
        "approvals.json": b'{"approvals":[]}\n',
        "gaps.json": b'{"gaps":[]}\n',
    }
    for relative, data in metadata.items():
        (package / relative).write_bytes(data)
    master_path = "references/master/master-character-sheet.png"
    master_data = png_bytes((512, 512), (70, 60, 50, 255))
    (package / master_path).write_bytes(master_data)
    master_artifact = artifact_evidence(master_path, master_data)
    records = [
        ProvenanceRecord(
            provenance_id="source-package",
            source_class=SourceClass.CREATIVE_CANON,
            artifact=master_artifact,
            authoritative_source="Synthetic sealed V1 master reference.",
            rights=complete_rights(),
        )
    ]
    for index, relative_path in enumerate(technical_source_paths(), start=1):
        data = png_bytes(
            (512, 512),
            (
                20 + index,
                40 + index,
                60 + index,
                255,
            ),
        )
        path = package / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        provenance_id = (
            "panel-neutral-front"
            if relative_path == "references/face/neutral-front.png"
            else f"panel-{index:02d}"
        )
        records.append(
            ProvenanceRecord(
                provenance_id=provenance_id,
                source_class=SourceClass.TECHNICAL_REFERENCE,
                artifact=artifact_evidence(relative_path, data),
                authoritative_source="Synthetic sealed V1 technical reference.",
                rights_basis_provenance_id="source-package",
                derived_from_sha256=(master_artifact.sha256,),
                provider="synthetic-provider",
                model="synthetic-v1",
                prompt_id=f"fixture.technical-panel-{index:02d}",
                prompt_version="1.0",
            )
        )
    optional_path = "references/face/optional-guide.png"
    optional_data = png_bytes((512, 512), (120, 121, 122, 255))
    (package / optional_path).write_bytes(optional_data)
    records.append(
        ProvenanceRecord(
            provenance_id="optional-guide",
            source_class=SourceClass.TECHNICAL_REFERENCE,
            artifact=artifact_evidence(optional_path, optional_data),
            authoritative_source="Synthetic optional V1 technical reference.",
            rights=complete_rights(),
        )
    )
    write_technical_provenance(package, tuple(records))
    evidence = seal_technical_package(
        package,
        tuple(record.provenance_id for record in records),
    )
    return package, evidence


def snapshot_files(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def change_one_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-10] ^= 1
    path.write_bytes(data)


def create_windows_junction(link: Path, target: Path) -> None:
    result = subprocess.run(
        ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
        check=False,
        capture_output=True,
    )
    if result.returncode != 0:
        pytest.skip("Windows junctions are unavailable in this environment.")


def create_directory_link(link: Path, target: Path) -> None:
    try:
        os.symlink(target, link, target_is_directory=True)
    except OSError as exc:
        if os.name != "nt":
            pytest.skip(f"Directory symlinks are unavailable in this environment: {exc}")
        create_windows_junction(link, target)


def initialization(
    base_sources: tuple[Path, ...],
    technical_package: Path,
    *,
    base_rights: RightsMetadata | None = None,
) -> PixelWorkspaceInitialization:
    return PixelWorkspaceInitialization(
        base_sources=base_sources,
        technical_package=technical_package,
        package_id="juana-talking-bust-v2-pixel",
        identity="juana",
        revision="2026-07-21-gh-23-r1",
        authoritative_source="Synthetic user-supplied base set",
        base_rights=base_rights,
    )


def initialized_workspace(
    tmp_path: Path,
    *,
    base_rights: RightsMetadata | None = None,
) -> tuple[
    FilesystemPixelPortraitWorkspace,
    PixelPortraitAuthoringState,
    tuple[Path, ...],
    Path,
]:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    workspace = FilesystemPixelPortraitWorkspace(tmp_path / "workspace")
    state = workspace.initialize(
        initialization(
            base_sources,
            technical_package,
            base_rights=base_rights,
        )
    )
    return workspace, state, base_sources, technical_package


def portrait_identity_lock() -> PortraitIdentityLock:
    neutral_palette = [list(panel_fixture_color("presence-neutral"))]
    return PortraitIdentityLock(
        palette_sha256=hashlib.sha256(
            json.dumps(neutral_palette, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        palette_max_colors=64,
        pivot=LogicalPoint(x=128, y=224),
        eye_rect=LogicalRect(x=80, y=72, width=96, height=24),
        mouth_rect=LogicalRect(x=96, y=136, width=64, height=24),
        shoulders=(LogicalPoint(x=48, y=220), LogicalPoint(x=208, y=220)),
        face_top_y=40,
        chin_y=200,
    )


def panel_fixture_color(panel_id: str) -> tuple[int, int, int, int]:
    index = next(
        position
        for position, panel in enumerate(PIXEL_PORTRAIT_PLAN.panels, start=1)
        if panel.panel_id == panel_id
    )
    return (index, 100 + index, 200 - index, 255)


def approved_state_for_families(
    workspace: FilesystemPixelPortraitWorkspace,
    state: PixelPortraitAuthoringState,
    family_ids: tuple[str, ...],
) -> PixelPortraitAuthoringState:
    selected_panel_ids = {
        "presence-neutral",
        *(
            panel_id
            for family_id in family_ids
            for panel_id in PIXEL_PORTRAIT_PLAN.family(family_id).panel_ids
        ),
    }
    lock = portrait_identity_lock()
    panels = dict(state.panels)
    base_by_name = {Path(artifact.path).name: artifact for artifact in state.revision.base_sources}
    technical_by_path = {
        record.artifact.path: record.artifact
        for record in state.provenance
        if record.artifact.path.startswith("sources/talking-bust-v1/")
    }
    for panel in PIXEL_PORTRAIT_PLAN.panels:
        if panel.panel_id not in selected_panel_ids:
            continue
        attempt_root = f"candidates/{panel.panel_id}/attempt-1"
        raw_data = png_bytes((1024, 1024), panel_fixture_color(panel.panel_id))
        panel_data = png_bytes((512, 512), panel_fixture_color(panel.panel_id))
        palette = [list(panel_fixture_color(panel.panel_id))]
        palette_sha256 = hashlib.sha256(
            json.dumps(palette, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        report_data = (
            json.dumps(
                {
                    "attempt": 1,
                    "normalized_sha256": hashlib.sha256(panel_data).hexdigest(),
                    "normalization": {
                        "actual_colors": 1,
                        "dither": "NONE",
                        "downsample": "LANCZOS",
                        "file_size": [512, 512],
                        "logical_pixel_scale": 2,
                        "logical_size": [256, 256],
                        "max_colors": 64,
                        "method": "FASTOCTREE",
                        "upscale": "NEAREST",
                    },
                    "palette": palette,
                    "palette_sha256": palette_sha256,
                    "panel_id": panel.panel_id,
                    "raw_sha256": hashlib.sha256(raw_data).hexdigest(),
                    "schema_version": "1.0",
                    "valid": True,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8")
        artifacts = (
            artifact_evidence(
                f"{attempt_root}/raw.png",
                raw_data,
                width=1024,
                height=1024,
            ),
            artifact_evidence(f"{attempt_root}/panel.png", panel_data),
            artifact_evidence(
                f"{attempt_root}/validation-report.json",
                report_data,
                width=1,
                height=1,
            ),
        )
        for evidence, data in zip(
            artifacts,
            (raw_data, panel_data, report_data),
            strict=True,
        ):
            path = workspace.resolve_artifact(evidence.path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        if panel.panel_id == "presence-neutral":
            technical_path = f"sources/talking-bust-v1/{panel.technical_source_path}"
            input_artifacts = (
                *(base_by_name[filename] for filename in BASE_SOURCE_FILENAMES),
                technical_by_path[technical_path],
            )
        elif panel.family_id == "presence-states":
            assert panel.base_source_role is not None
            neutral = panels["presence-neutral"].candidates[0].normalized_panel
            input_artifacts = (
                base_by_name["juana-avatar-character-sheet.png"],
                base_by_name[f"juana-avatar-{panel.base_source_role}.png"],
                neutral,
            )
        else:
            assert panel.technical_source_path is not None
            neutral = panels["presence-neutral"].candidates[0].normalized_panel
            technical_path = f"sources/talking-bust-v1/{panel.technical_source_path}"
            input_artifacts = (
                base_by_name["juana-avatar-character-sheet.png"],
                neutral,
                technical_by_path[technical_path],
            )
        candidate = PixelPanelCandidate(
            candidate_id=f"{panel.panel_id}-attempt-1",
            panel_id=panel.panel_id,
            attempt=1,
            status=CandidateStatus.APPROVED,
            provider="synthetic",
            model="synthetic-v1",
            prompt_id=panel.prompt_id,
            prompt_version=panel.prompt_version,
            input_artifacts=input_artifacts,
            raw_artifact=artifacts[0],
            normalized_panel=artifacts[1],
            validation_report=artifacts[2],
            created_at=NOW,
        )
        attempt = GenerationAttempt(
            attempt_id=f"{panel.panel_id}-attempt-1",
            task_id=panel.panel_id,
            attempt=1,
            status=GenerationAttemptStatus.CANDIDATE_READY,
            started_at=NOW,
            completed_at=NOW,
            candidate_id=candidate.candidate_id,
        )
        approval = PixelPanelApproval(
            approval_id=f"approve-{candidate.candidate_id}",
            candidate_id=candidate.candidate_id,
            panel_id=panel.panel_id,
            decision=ApprovalDecision.APPROVE,
            approver="Synthetic reviewer",
            decided_at=NOW,
            reviewed_artifacts=tuple(evidence.path for evidence in artifacts),
            notes="Synthetic composition fixture approval.",
            identity_lock=(lock if panel.panel_id == "presence-neutral" else None),
        )
        panels[panel.panel_id] = PixelPanelState(
            panel_id=panel.panel_id,
            progress=PanelProgress.APPROVED,
            attempts=(attempt,),
            candidates=(candidate,),
            decisions=(approval,),
            approved_candidate_id=candidate.candidate_id,
        )
    return PixelPortraitAuthoringState.model_validate(
        state.model_copy(update={"panels": panels, "identity_lock": lock}).model_dump(mode="python")
    )


def approve_composite(
    state: PixelPortraitAuthoringState,
    composite: CompositeReviewSheet,
) -> PixelPortraitAuthoringState:
    approved = composite.model_copy(update={"status": CompositeStatus.APPROVED})
    approval = CompositeApproval(
        approval_id=f"approve-{approved.composite_id}",
        composite_id=approved.composite_id,
        decision=ApprovalDecision.APPROVE,
        approver="Synthetic reviewer",
        decided_at=NOW,
        reviewed_artifacts=(approved.artifact.path,),
        notes="Synthetic composition fixture approval.",
    )
    return PixelPortraitAuthoringState.model_validate(
        state.model_copy(
            update={
                "composites": (*state.composites, approved),
                "composite_approvals": (*state.composite_approvals, approval),
                "active_composite_ids": (*state.active_composite_ids, approved.composite_id),
            }
        ).model_dump(mode="python")
    )


def complete_sealable_state(
    workspace: FilesystemPixelPortraitWorkspace,
    initial: PixelPortraitAuthoringState,
) -> PixelPortraitAuthoringState:
    """Build one complete synthetic state without invoking a provider."""
    family_ids = tuple(family.family_id for family in PIXEL_PORTRAIT_PLAN.families)
    state = approved_state_for_families(workspace, initial, family_ids)
    for family in PIXEL_PORTRAIT_PLAN.families:
        state = approve_composite(
            state,
            workspace.compose(
                state=state,
                scope=CompositeScope.FAMILY,
                family_id=family.family_id,
                created_at=NOW,
            ),
        )
    master = workspace.compose(
        state=state,
        scope=CompositeScope.PACKAGE_MASTER,
        family_id=None,
        created_at=NOW,
    )
    approved_master = master.model_copy(update={"status": CompositeStatus.APPROVED})
    master_approval = CompositeApproval(
        approval_id=f"approve-{master.composite_id}",
        composite_id=master.composite_id,
        approver="Synthetic reviewer",
        decided_at=NOW,
        reviewed_artifacts=(master.artifact.path,),
        notes="Synthetic package-master fixture approval.",
    )
    return PixelPortraitAuthoringState.model_validate(
        state.model_copy(
            update={
                "revision": state.revision.model_copy(
                    update={
                        "master_reference": master.artifact.model_copy(
                            update={"path": PACKAGE_MASTER_PATH}
                        )
                    }
                ),
                "composites": (*state.composites, approved_master),
                "composite_approvals": (*state.composite_approvals, master_approval),
                "active_composite_ids": (*state.active_composite_ids, master.composite_id),
            }
        ).model_dump(mode="python")
    )


def same_hash_replacement_panel(
    workspace: FilesystemPixelPortraitWorkspace,
    panel_state: PixelPanelState,
) -> PixelPanelState:
    original = panel_state.candidates[0]
    replacement_root = f"candidates/{panel_state.panel_id}/attempt-2"
    source_artifacts = (
        original.raw_artifact,
        original.normalized_panel,
        original.validation_report,
    )
    replacement_paths = (
        f"{replacement_root}/raw.png",
        f"{replacement_root}/panel.png",
        f"{replacement_root}/validation-report.json",
    )
    replacement_artifacts: list[ArtifactEvidence] = []
    for source, replacement_path in zip(
        source_artifacts,
        replacement_paths,
        strict=True,
    ):
        data = workspace.resolve_artifact(source.path).read_bytes()
        destination = workspace.resolve_artifact(replacement_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
        replacement_artifacts.append(
            artifact_evidence(
                replacement_path,
                data,
                width=source.width,
                height=source.height,
            )
        )

    superseded = original.model_copy(update={"status": CandidateStatus.SUPERSEDED})
    replacement = original.model_copy(
        update={
            "candidate_id": f"{panel_state.panel_id}-attempt-2",
            "attempt": 2,
            "status": CandidateStatus.APPROVED,
            "raw_artifact": replacement_artifacts[0],
            "normalized_panel": replacement_artifacts[1],
            "validation_report": replacement_artifacts[2],
            "created_at": NOW.replace(hour=13),
        }
    )
    replacement_attempt = GenerationAttempt(
        attempt_id=f"{panel_state.panel_id}-attempt-2",
        task_id=panel_state.panel_id,
        attempt=2,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        started_at=NOW.replace(hour=13),
        completed_at=NOW.replace(hour=13),
        candidate_id=replacement.candidate_id,
    )
    supersession = PixelPanelApproval(
        approval_id=f"supersede-{original.candidate_id}",
        candidate_id=original.candidate_id,
        panel_id=panel_state.panel_id,
        decision=ApprovalDecision.SUPERSEDE,
        approver="Synthetic reviewer",
        decided_at=NOW.replace(hour=13),
        reviewed_artifacts=(
            original.raw_artifact.path,
            original.normalized_panel.path,
            original.validation_report.path,
        ),
        notes="Superseded by a same-content rerender fixture.",
    )
    replacement_approval = PixelPanelApproval(
        approval_id=f"approve-{replacement.candidate_id}",
        candidate_id=replacement.candidate_id,
        panel_id=panel_state.panel_id,
        decision=ApprovalDecision.APPROVE,
        approver="Synthetic reviewer",
        decided_at=NOW.replace(hour=13),
        reviewed_artifacts=tuple(artifact.path for artifact in replacement_artifacts),
        notes="Approved same-content rerender fixture.",
    )
    return PixelPanelState(
        panel_id=panel_state.panel_id,
        progress=PanelProgress.APPROVED,
        attempts=(*panel_state.attempts, replacement_attempt),
        candidates=(superseded, replacement),
        decisions=(*panel_state.decisions, supersession, replacement_approval),
        approved_candidate_id=replacement.candidate_id,
    )


def test_initialization_contract_requires_exact_named_sources_and_forbids_extra(
    tmp_path: Path,
) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    valid = initialization(base_sources, technical_package)

    for invalid_sources in (
        base_sources[:-1],
        (*base_sources, tmp_path / "extra.png"),
        (*base_sources[:-1], tmp_path / "wrong-name.png"),
    ):
        payload = valid.model_dump()
        payload["base_sources"] = invalid_sources
        with pytest.raises(ValidationError, match="seven named base-set paths"):
            PixelWorkspaceInitialization.model_validate(payload)

    payload = valid.model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="unexpected"):
        PixelWorkspaceInitialization.model_validate(payload)


def test_port_and_stage_signature_expose_the_approved_boundary() -> None:
    methods = {
        "initialize",
        "load_state",
        "save_state",
        "resolve_artifact",
        "stage_candidate",
        "compose",
        "seal",
        "validate",
        "exclusive",
    }
    assert methods <= set(PixelPortraitWorkspacePort.__dict__)

    parameters = signature(FilesystemPixelPortraitWorkspace.stage_candidate).parameters
    assert tuple(parameters) == (
        "self",
        "panel",
        "attempt",
        "generated",
        "input_artifacts",
        "created_at",
    )
    assert all(
        parameters[name].kind is Parameter.KEYWORD_ONLY
        for name in (
            "panel",
            "attempt",
            "generated",
            "input_artifacts",
            "created_at",
        )
    )


def test_initialize_locks_all_sources_without_mutating_upstream_bytes(
    tmp_path: Path,
) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, technical_seal = create_technical_package(tmp_path)
    original_base = {path.name: path.read_bytes() for path in base_sources}
    original_technical = snapshot_files(technical_package)
    workspace = FilesystemPixelPortraitWorkspace(tmp_path / "workspace")

    state = workspace.initialize(initialization(base_sources, technical_package))

    expected_source_paths = tuple(
        f"sources/base-set/{filename}" for filename in BASE_SOURCE_FILENAMES
    )
    assert tuple(source.path for source in state.revision.base_sources) == (expected_source_paths)
    assert state.revision.technical_source_seal == technical_seal
    assert state.revision.base_source_rights == RightsMetadata()
    assert tuple(state.panels) == tuple(panel.panel_id for panel in PIXEL_PORTRAIT_PLAN.panels)
    assert workspace.load_state() == state
    workspace.validate(state)
    base_provenance = tuple(
        record
        for record in state.provenance
        if record.artifact.path.startswith("sources/base-set/")
    )
    assert len(base_provenance) == 7
    assert all(
        record.source_class is SourceClass.CREATIVE_CANON
        and record.rights == RightsMetadata()
        and record.authoritative_source == "Synthetic user-supplied base set"
        for record in base_provenance
    )
    assert len(state.provenance) == 7 + len(technical_source_paths()) + 2
    assert any(gap.gap_id == "source-rights-incomplete" for gap in state.gaps)
    for source, evidence in zip(base_sources, state.revision.base_sources, strict=True):
        data = original_base[source.name]
        assert source.read_bytes() == data
        assert workspace.resolve_artifact(evidence.path).read_bytes() == data
        assert evidence.byte_length == len(data)
        assert evidence.sha256 == hashlib.sha256(data).hexdigest()
        with Image.open(source) as image:
            assert (evidence.width, evidence.height) == image.size
    locked_technical = workspace.root / "sources/talking-bust-v1"
    assert snapshot_files(technical_package) == original_technical
    assert snapshot_files(locked_technical) == original_technical
    assert (workspace.root / workspace.PLAN_FILE).is_file()


def test_initialize_records_complete_rights_without_a_rights_gap(tmp_path: Path) -> None:
    rights = complete_rights()
    workspace, state, _, _ = initialized_workspace(tmp_path, base_rights=rights)

    assert workspace.load_state().revision.base_source_rights == rights
    assert all(
        record.rights == rights
        for record in state.provenance
        if record.artifact.path.startswith("sources/base-set/")
    )
    assert "source-rights-incomplete" not in {gap.gap_id for gap in state.gaps}


def test_initialize_imports_remapped_technical_provenance_and_rights_chain(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    technical_records = tuple(
        record
        for record in state.provenance
        if record.artifact.path.startswith("sources/talking-bust-v1/")
    )
    by_path = {record.artifact.path: record for record in technical_records}
    neutral = by_path["sources/talking-bust-v1/references/face/neutral-front.png"]
    rights_basis = next(
        record
        for record in technical_records
        if record.provenance_id == f"{TECHNICAL_PROVENANCE_PREFIX}source-package"
    )

    assert len(technical_records) == len(technical_source_paths()) + 2
    assert neutral.provenance_id == (f"{TECHNICAL_PROVENANCE_PREFIX}panel-neutral-front")
    assert neutral.source_class is SourceClass.TECHNICAL_REFERENCE
    assert neutral.authoritative_source == ("Synthetic sealed V1 technical reference.")
    assert neutral.rights is None
    assert neutral.rights_basis_provenance_id == rights_basis.provenance_id
    assert neutral.derived_from_sha256 == (rights_basis.artifact.sha256,)
    assert (
        neutral.provider,
        neutral.model,
        neutral.prompt_id,
        neutral.prompt_version,
    ) == (
        "synthetic-provider",
        "synthetic-v1",
        "fixture.technical-panel-"
        f"{technical_source_paths().index('references/face/neutral-front.png') + 1:02d}",
        "1.0",
    )
    assert rights_basis.rights == complete_rights()
    assert rights_basis.artifact.path == (
        "sources/talking-bust-v1/references/master/master-character-sheet.png"
    )
    assert all(
        record.provenance_id.startswith(TECHNICAL_PROVENANCE_PREFIX) for record in technical_records
    )
    assert len({record.provenance_id for record in state.provenance}) == len(state.provenance)
    assert all(not record.artifact.path.endswith(".json") for record in technical_records)
    neutral_data = workspace.resolve_artifact(neutral.artifact.path).read_bytes()
    assert neutral.artifact.sha256 == hashlib.sha256(neutral_data).hexdigest()
    assert neutral.artifact.byte_length == len(neutral_data)
    assert (neutral.artifact.width, neutral.artifact.height) == (512, 512)


def test_initialize_rejects_missing_required_technical_provenance(
    tmp_path: Path,
) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    records = tuple(
        record
        for record in technical_provenance_records(technical_package)
        if record.artifact.path != "references/face/neutral-front.png"
    )
    replace_technical_provenance(technical_package, records)
    workspace = FilesystemPixelPortraitWorkspace(tmp_path / "workspace")

    with pytest.raises(
        PackageIntegrityError,
        match="required technical source provenance",
    ):
        workspace.initialize(initialization(base_sources, technical_package))

    assert not workspace.root.exists()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    (
        ("sha256", "0" * 64, "digest"),
        ("byte_length", 1, "byte length"),
        ("width", 1, "dimensions"),
    ),
)
def test_initialize_rejects_mismatched_technical_provenance_evidence(
    tmp_path: Path,
    field: str,
    value: object,
    message: str,
) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    records = list(technical_provenance_records(technical_package))
    index = next(
        position
        for position, record in enumerate(records)
        if record.artifact.path == "references/face/neutral-front.png"
    )
    record_payload = records[index].model_dump(mode="python")
    artifact_payload = records[index].artifact.model_dump(mode="python")
    artifact_payload[field] = value
    record_payload["artifact"] = artifact_payload
    records[index] = ProvenanceRecord.model_validate(record_payload)
    replace_technical_provenance(technical_package, tuple(records))
    workspace = FilesystemPixelPortraitWorkspace(tmp_path / "workspace")

    with pytest.raises(PackageIntegrityError, match=message):
        workspace.initialize(initialization(base_sources, technical_package))

    assert not workspace.root.exists()


def test_validate_rejects_missing_required_technical_provenance(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    incomplete = state.model_copy(
        update={
            "provenance": tuple(
                record
                for record in state.provenance
                if record.artifact.path
                != "sources/talking-bust-v1/references/face/neutral-front.png"
            )
        }
    )

    with pytest.raises(
        PackageIntegrityError,
        match="required technical source provenance",
    ):
        workspace.validate(incomplete)


def test_validate_rejects_candidate_technical_input_without_state_provenance(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    optional = next(
        (
            record
            for record in state.provenance
            if record.artifact.path == "sources/talking-bust-v1/references/face/optional-guide.png"
        ),
        None,
    )
    assert optional is not None
    panel = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    candidate = workspace.stage_candidate(
        panel=panel,
        attempt=1,
        generated=GeneratedImage(
            data=gradient_png_bytes(),
            provider="fake",
            model="fake-v1",
        ),
        input_artifacts=(optional.artifact,),
        created_at=NOW,
    )
    attempt = GenerationAttempt(
        attempt_id="presence-neutral-attempt-1",
        task_id=panel.panel_id,
        attempt=1,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        started_at=NOW,
        completed_at=NOW,
        candidate_id=candidate.candidate_id,
    )
    panels = dict(state.panels)
    panels[panel.panel_id] = PixelPanelState(
        panel_id=panel.panel_id,
        progress=PanelProgress.CANDIDATE_READY,
        attempts=(attempt,),
        candidates=(candidate,),
    )
    incomplete = PixelPortraitAuthoringState.model_validate(
        state.model_copy(
            update={
                "panels": panels,
                "provenance": tuple(
                    record
                    for record in state.provenance
                    if record.provenance_id != optional.provenance_id
                ),
            }
        ).model_dump(mode="python")
    )

    with pytest.raises(PackageIntegrityError, match="candidate technical input"):
        workspace.validate(incomplete)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sha256", "0" * 64),
        ("byte_length", 1),
        ("width", 1),
        ("height", 1),
    ),
)
def test_validate_rejects_candidate_base_input_evidence_drift(
    tmp_path: Path,
    field: str,
    value: object,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    panel = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    candidate = workspace.stage_candidate(
        panel=panel,
        attempt=1,
        generated=GeneratedImage(
            data=png_bytes((1024, 1024)),
            provider="fake",
            model="fake-v1",
        ),
        input_artifacts=(state.revision.base_sources[0],),
        created_at=NOW,
    )
    drifted_input = state.revision.base_sources[0].model_copy(update={field: value})
    drifted_candidate = candidate.model_copy(update={"input_artifacts": (drifted_input,)})
    attempt = GenerationAttempt(
        attempt_id="presence-neutral-attempt-1",
        task_id=panel.panel_id,
        attempt=1,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        started_at=NOW,
        completed_at=NOW,
        candidate_id=drifted_candidate.candidate_id,
    )
    panels = dict(state.panels)
    panels[panel.panel_id] = PixelPanelState(
        panel_id=panel.panel_id,
        progress=PanelProgress.CANDIDATE_READY,
        attempts=(attempt,),
        candidates=(drifted_candidate,),
    )
    drifted = PixelPortraitAuthoringState.model_validate(
        state.model_copy(update={"panels": panels}).model_dump(mode="python")
    )

    with pytest.raises(PackageIntegrityError, match="candidate base input evidence"):
        workspace.validate(drifted)


def test_initialize_refuses_missing_sources_existing_workspace_and_invalid_seal(
    tmp_path: Path,
) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    base_sources[0].unlink()
    workspace = FilesystemPixelPortraitWorkspace(tmp_path / "missing-workspace")
    with pytest.raises(WorkspaceError, match="unavailable"):
        workspace.initialize(initialization(base_sources, technical_package))
    assert not workspace.root.exists()

    replacement = base_sources[0]
    replacement.write_bytes(png_bytes((64, 80)))
    existing = tmp_path / "existing-workspace"
    existing.mkdir()
    with pytest.raises(WorkspaceAlreadyExistsError, match="already exists"):
        FilesystemPixelPortraitWorkspace(existing).initialize(
            initialization(base_sources, technical_package)
        )

    (technical_package / "package.json").write_text("changed", encoding="utf-8")
    invalid = FilesystemPixelPortraitWorkspace(tmp_path / "invalid-seal-workspace")
    with pytest.raises(PackageIntegrityError, match="digest mismatch"):
        invalid.initialize(initialization(base_sources, technical_package))
    assert not invalid.root.exists()


def test_initialize_rejects_undeclared_technical_source_files(tmp_path: Path) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    (technical_package / "undeclared.txt").write_text(
        "not covered by the source seal",
        encoding="utf-8",
    )
    workspace = FilesystemPixelPortraitWorkspace(tmp_path / "workspace")

    with pytest.raises(PackageIntegrityError, match="undeclared files"):
        workspace.initialize(initialization(base_sources, technical_package))

    assert not workspace.root.exists()


def test_atomic_state_failure_leaves_the_previous_state_readable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, original, _, _ = initialized_workspace(tmp_path)
    changed = original.model_copy(
        update={"plan_version": "atomic-write-test"},
    )

    def fail_replace(source: Path, destination: Path) -> None:
        raise OSError("injected replace failure")

    monkeypatch.setattr(
        "vrm_ia_maker.design.pixel_portrait.adapters.filesystem.os.replace",
        fail_replace,
    )

    with pytest.raises(OSError, match="injected replace failure"):
        workspace.save_state(changed)

    assert workspace.load_state() == original
    assert not list(workspace.root.glob(f".{workspace.STATE_FILE}.*.tmp"))


def test_state_json_is_canonical_and_strict(tmp_path: Path) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    expected = (json.dumps(state.model_dump(mode="json"), indent=2, sort_keys=True) + "\n").encode(
        "utf-8"
    )

    assert (workspace.root / workspace.STATE_FILE).read_bytes() == expected
    payload = state.model_dump(mode="json")
    payload["unexpected"] = True
    (workspace.root / workspace.STATE_FILE).write_text(
        json.dumps(payload),
        encoding="utf-8",
    )
    with pytest.raises(ValidationError, match="unexpected"):
        workspace.load_state()


def test_resolve_artifact_rejects_traversal_and_symlink_escape(tmp_path: Path) -> None:
    workspace, _, _, _ = initialized_workspace(tmp_path)

    with pytest.raises(WorkspacePathError, match="safe package-relative path"):
        workspace.resolve_artifact("../outside.png")

    outside = tmp_path / "outside"
    outside.mkdir()
    link = workspace.root / "escape"
    try:
        os.symlink(outside, link, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Symlinks are unavailable in this environment: {exc}")
    with pytest.raises(WorkspacePathError, match="escapes the authoring workspace"):
        workspace.resolve_artifact("escape/file.png")


def test_initialize_rejects_a_symlinked_workspace_parent(tmp_path: Path) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    target = tmp_path / "symlink-target"
    target.mkdir()
    linked_parent = tmp_path / "symlink-parent"
    try:
        os.symlink(target, linked_parent, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"Directory symlinks are unavailable in this environment: {exc}")

    workspace = FilesystemPixelPortraitWorkspace(linked_parent / "workspace")
    try:
        with pytest.raises(WorkspacePathError, match="root ancestry"):
            workspace.initialize(initialization(base_sources, technical_package))
        assert not (target / "workspace").exists()
    finally:
        linked_parent.unlink(missing_ok=True)


@pytest.mark.skipif(os.name != "nt", reason="Windows junction regression")
def test_initialize_rejects_a_windows_junction_workspace_parent(tmp_path: Path) -> None:
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    target = tmp_path / "junction-target"
    target.mkdir()
    junction_parent = tmp_path / "junction-parent"
    create_windows_junction(junction_parent, target)

    workspace = FilesystemPixelPortraitWorkspace(junction_parent / "workspace")
    try:
        with pytest.raises(WorkspacePathError, match="root ancestry"):
            workspace.initialize(initialization(base_sources, technical_package))
        assert not (target / "workspace").exists()
    finally:
        if junction_parent.exists():
            os.rmdir(junction_parent)


def test_save_state_rechecks_root_ancestry_after_construction(tmp_path: Path) -> None:
    real_parent = tmp_path / "workspace-parent"
    real_parent.mkdir()
    base_sources = create_base_sources(tmp_path)
    technical_package, _ = create_technical_package(tmp_path)
    workspace = FilesystemPixelPortraitWorkspace(real_parent / "workspace")
    state = workspace.initialize(initialization(base_sources, technical_package))

    original_parent = tmp_path / "original-workspace-parent"
    real_parent.rename(original_parent)
    redirect_target = tmp_path / "redirect-target"
    redirected_workspace = redirect_target / "workspace"
    redirected_workspace.mkdir(parents=True)
    create_directory_link(real_parent, redirect_target)
    try:
        with pytest.raises(WorkspacePathError, match="root ancestry"):
            workspace.save_state(state)
        assert not (redirected_workspace / workspace.STATE_FILE).exists()
    finally:
        if real_parent.is_symlink():
            real_parent.unlink()
        elif real_parent.exists() and os.name == "nt":
            os.rmdir(real_parent)


def test_validate_rejects_changed_base_and_technical_source_locks(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    base_path = workspace.resolve_artifact(state.revision.base_sources[0].path)
    change_one_byte(base_path)
    with pytest.raises(PackageIntegrityError, match="digest changed"):
        workspace.validate(state)

    other = tmp_path / "other"
    other.mkdir()
    workspace, state, _, _ = initialized_workspace(other)
    technical_file = workspace.root / "sources/talking-bust-v1/package.json"
    technical_file.write_text("changed", encoding="utf-8")
    with pytest.raises(PackageIntegrityError, match="digest mismatch"):
        workspace.validate(state)


def test_stage_candidate_preserves_raw_and_normalizes_a_deterministic_pixel_grid(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    panel = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    raw_png = gradient_png_bytes()

    candidate = workspace.stage_candidate(
        panel=panel,
        attempt=1,
        generated=GeneratedImage(data=raw_png, provider="fake", model="fake-v1"),
        input_artifacts=state.revision.base_sources,
        created_at=NOW,
    )

    assert candidate.raw_artifact.path.endswith("/raw.png")
    assert candidate.normalized_panel.path.endswith("/panel.png")
    assert candidate.validation_report.path.endswith("/validation-report.json")
    assert workspace.resolve_artifact(candidate.raw_artifact.path).read_bytes() == raw_png
    assert candidate.raw_artifact.sha256 == hashlib.sha256(raw_png).hexdigest()
    assert (candidate.raw_artifact.width, candidate.raw_artifact.height) == (1024, 1024)
    panel_path = workspace.resolve_artifact(candidate.normalized_panel.path)
    panel_data = panel_path.read_bytes()
    assert candidate.normalized_panel.sha256 == hashlib.sha256(panel_data).hexdigest()
    assert candidate.normalized_panel.byte_length == len(panel_data)
    with Image.open(panel_path) as image:
        pixels = image.convert("RGBA")
        assert image.size == (512, 512)
        colors = pixels.getcolors(maxcolors=65)
        assert colors is not None
        assert len(colors) <= 64
        for y in range(0, 512, 2):
            for x in range(0, 512, 2):
                assert (
                    len({pixels.getpixel((x + dx, y + dy)) for dx in (0, 1) for dy in (0, 1)}) == 1
                )
    report_path = workspace.resolve_artifact(candidate.validation_report.path)
    report_data = report_path.read_bytes()
    report = json.loads(report_data)
    assert report["normalization"] == {
        "actual_colors": len(report["palette"]),
        "dither": "NONE",
        "downsample": "LANCZOS",
        "file_size": [512, 512],
        "logical_pixel_scale": 2,
        "logical_size": [256, 256],
        "max_colors": 64,
        "method": "FASTOCTREE",
        "upscale": "NEAREST",
    }
    assert report["valid"] is True
    assert len(report["palette"]) <= 64
    assert report["palette"] == sorted(report["palette"])
    assert candidate.validation_report.sha256 == hashlib.sha256(report_data).hexdigest()
    assert (candidate.validation_report.width, candidate.validation_report.height) == (1, 1)


def test_pixel_normalization_palette_and_panel_bytes_are_repeatable(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    panel = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    generated = GeneratedImage(
        data=gradient_png_bytes(),
        provider="fake",
        model="fake-v1",
    )

    first = workspace.stage_candidate(
        panel=panel,
        attempt=1,
        generated=generated,
        input_artifacts=state.revision.base_sources,
        created_at=NOW,
    )
    second = workspace.stage_candidate(
        panel=panel,
        attempt=2,
        generated=generated,
        input_artifacts=state.revision.base_sources,
        created_at=NOW,
    )

    assert workspace.resolve_artifact(first.normalized_panel.path).read_bytes() == (
        workspace.resolve_artifact(second.normalized_panel.path).read_bytes()
    )
    first_report = json.loads(
        workspace.resolve_artifact(first.validation_report.path).read_text(encoding="utf-8")
    )
    second_report = json.loads(
        workspace.resolve_artifact(second.validation_report.path).read_text(encoding="utf-8")
    )
    assert first_report["palette"] == second_report["palette"]
    assert first_report["palette_sha256"] == second_report["palette_sha256"]


def test_stage_candidate_rejects_wrong_raw_size_but_preserves_the_raw_png(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    panel = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    raw_png = png_bytes((512, 512))

    with pytest.raises(CandidateValidationError, match="1024x1024"):
        workspace.stage_candidate(
            panel=panel,
            attempt=1,
            generated=GeneratedImage(data=raw_png, provider="fake", model="fake"),
            input_artifacts=state.revision.base_sources,
            created_at=NOW,
        )

    attempt = workspace.root / "candidates/presence-neutral/attempt-1"
    assert (attempt / "raw.png").read_bytes() == raw_png
    assert not (attempt / "panel.png").exists()
    assert not (attempt / "validation-report.json").exists()


def test_stage_candidate_rejects_changed_inputs_before_creating_an_attempt(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    source = state.revision.base_sources[0]
    change_one_byte(workspace.resolve_artifact(source.path))

    with pytest.raises(PackageIntegrityError, match="digest changed"):
        workspace.stage_candidate(
            panel=PIXEL_PORTRAIT_PLAN.panel("presence-neutral"),
            attempt=1,
            generated=GeneratedImage(
                data=gradient_png_bytes(),
                provider="fake",
                model="fake",
            ),
            input_artifacts=(source,),
            created_at=NOW,
        )

    assert not (workspace.root / "candidates/presence-neutral/attempt-1").exists()


def test_stage_candidate_never_overwrites_an_existing_attempt(tmp_path: Path) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    panel = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    first_data = gradient_png_bytes()
    first = workspace.stage_candidate(
        panel=panel,
        attempt=1,
        generated=GeneratedImage(data=first_data, provider="fake", model="fake"),
        input_artifacts=state.revision.base_sources,
        created_at=NOW,
    )

    with pytest.raises(WorkspaceAlreadyExistsError, match="attempt already exists"):
        workspace.stage_candidate(
            panel=panel,
            attempt=1,
            generated=GeneratedImage(
                data=png_bytes((1024, 1024), (1, 2, 3, 255)),
                provider="fake",
                model="fake",
            ),
            input_artifacts=state.revision.base_sources,
            created_at=NOW,
        )

    assert workspace.resolve_artifact(first.raw_artifact.path).read_bytes() == first_data


def test_workspace_lock_rejects_a_second_writer_and_recovers(tmp_path: Path) -> None:
    workspace, _, _, _ = initialized_workspace(tmp_path)

    with (
        workspace.exclusive(),
        pytest.raises(
            WorkspaceLockedError,
            match="already locked",
        ),
        workspace.exclusive(),
    ):
        pass

    with workspace.exclusive():
        pass


def test_save_state_honors_a_lock_held_by_another_workspace_instance(
    tmp_path: Path,
) -> None:
    workspace, original, _, _ = initialized_workspace(tmp_path)
    competing = FilesystemPixelPortraitWorkspace(workspace.root)
    changed = original.model_copy(update={"plan_version": "competing-write"})

    with (
        workspace.exclusive(),
        pytest.raises(
            WorkspaceLockedError,
            match="already locked",
        ),
    ):
        competing.save_state(changed)

    assert workspace.load_state() == original


def test_stage_candidate_honors_a_lock_held_by_another_workspace_instance(
    tmp_path: Path,
) -> None:
    workspace, state, _, _ = initialized_workspace(tmp_path)
    competing = FilesystemPixelPortraitWorkspace(workspace.root)

    with (
        workspace.exclusive(),
        pytest.raises(
            WorkspaceLockedError,
            match="already locked",
        ),
    ):
        competing.stage_candidate(
            panel=PIXEL_PORTRAIT_PLAN.panel("presence-neutral"),
            attempt=1,
            generated=GeneratedImage(
                data=gradient_png_bytes(),
                provider="fake",
                model="fake",
            ),
            input_artifacts=state.revision.base_sources,
            created_at=NOW,
        )

    assert not (workspace.root / "candidates/presence-neutral/attempt-1").exists()


def test_artifact_evidence_inputs_remain_strict_models() -> None:
    with pytest.raises(ValidationError, match="unexpected"):
        ArtifactEvidence.model_validate(
            {
                "path": "sources/base-set/source.png",
                "sha256": "a" * 64,
                "byte_length": 1,
                "width": 1,
                "height": 1,
                "unexpected": True,
            }
        )


def test_compose_family_writes_exact_pixel_grid_and_slot_map(tmp_path: Path) -> None:
    workspace, initial, _, _ = initialized_workspace(tmp_path)
    family = PIXEL_PORTRAIT_PLAN.family("presence-states")
    state = approved_state_for_families(workspace, initial, (family.family_id,))

    composite = workspace.compose(
        state=state,
        scope=CompositeScope.FAMILY,
        family_id=family.family_id,
        created_at=NOW,
    )

    assert composite.composite_id == "family-presence-states-v1"
    assert composite.artifact.path == ("composites/family/family-presence-states-v1/sheet.png")
    assert composite.member_ids == family.panel_ids
    assert composite.member_hashes == tuple(
        state.panels[panel_id].candidates[0].normalized_panel.sha256
        for panel_id in family.panel_ids
    )
    assert composite.member_artifacts == tuple(
        state.panels[panel_id].candidates[0].normalized_panel for panel_id in family.panel_ids
    )
    assert composite.composition_version == "pixel-grid-v1"
    assert composite.status is CompositeStatus.PENDING_REVIEW
    assert (composite.artifact.width, composite.artifact.height) == (1540, 1026)
    sheet_path = workspace.resolve_artifact(composite.artifact.path)
    with Image.open(sheet_path) as sheet:
        rgba = sheet.convert("RGBA")
        assert rgba.size == (1540, 1026)
        assert rgba.getpixel((512, 0)) == (0, 0, 0, 0)
        assert rgba.getpixel((513, 511)) == (0, 0, 0, 0)
        assert rgba.getpixel((0, 512)) == (0, 0, 0, 0)
        assert rgba.getpixel((511, 513)) == (0, 0, 0, 0)
        assert {color for _, color in rgba.getcolors(maxcolors=8) or ()} == {
            (0, 0, 0, 0),
            *(panel_fixture_color(panel_id) for panel_id in family.panel_ids),
        }

    members = []
    for index, panel_id in enumerate(family.panel_ids):
        members.append(
            {
                "height": 512,
                "member_id": panel_id,
                "path": composite.member_artifacts[index].path,
                "sha256": composite.member_hashes[index],
                "width": 512,
                "x": (index % family.columns) * 514,
                "y": (index // family.columns) * 514,
            }
        )
    slot_map_path = sheet_path.with_name("slot-map.json")
    assert json.loads(slot_map_path.read_text(encoding="utf-8")) == {
        "cell": {"alignment": "top_left", "height": 512, "width": 512},
        "composite_id": composite.composite_id,
        "composition_version": "pixel-grid-v1",
        "created_at": NOW.isoformat(),
        "family_id": family.family_id,
        "grid": {"columns": 3, "gap": 2, "rows": 2},
        "members": members,
        "output": {"height": 1026, "width": 1540},
        "schema_version": "1.0",
        "scope": "family",
    }
    assert slot_map_path.read_bytes().endswith(b"\n")

    first_bytes = sheet_path.read_bytes()
    repeated = workspace.compose(
        state=state,
        scope=CompositeScope.FAMILY,
        family_id=family.family_id,
        created_at=NOW.replace(hour=13),
    )
    assert repeated == composite
    assert sheet_path.read_bytes() == first_bytes


def test_compose_family_rejects_unknown_incomplete_and_existing_mismatch(
    tmp_path: Path,
) -> None:
    workspace, initial, _, _ = initialized_workspace(tmp_path)
    family = PIXEL_PORTRAIT_PLAN.family("presence-states")
    state = approved_state_for_families(workspace, initial, (family.family_id,))

    with pytest.raises(PackageIntegrityError, match="fixed plan"):
        workspace.compose(
            state=state,
            scope=CompositeScope.FAMILY,
            family_id="wrong-family",
            created_at=NOW,
        )

    panels = dict(state.panels)
    panels[family.panel_ids[-1]] = initial.panels[family.panel_ids[-1]]
    incomplete = PixelPortraitAuthoringState.model_validate(
        state.model_copy(update={"panels": panels}).model_dump(mode="python")
    )
    with pytest.raises(PackageIntegrityError, match="every ordered member"):
        workspace.compose(
            state=incomplete,
            scope=CompositeScope.FAMILY,
            family_id=family.family_id,
            created_at=NOW,
        )

    version_dir = workspace.root / "composites/family/family-presence-states-v1"
    version_dir.mkdir(parents=True)
    marker = version_dir / "unexpected.txt"
    marker.write_text("do not overwrite", encoding="utf-8")
    with pytest.raises(PackageIntegrityError, match="existing composite"):
        workspace.compose(
            state=state,
            scope=CompositeScope.FAMILY,
            family_id=family.family_id,
            created_at=NOW,
        )
    assert marker.read_text(encoding="utf-8") == "do not overwrite"


def test_compose_package_master_uses_fixed_three_by_three_plan_order_without_resampling(
    tmp_path: Path,
) -> None:
    workspace, initial, _, _ = initialized_workspace(tmp_path)
    family_ids = tuple(family.family_id for family in PIXEL_PORTRAIT_PLAN.families)
    state = approved_state_for_families(workspace, initial, family_ids)
    approved_families: list[CompositeReviewSheet] = []
    for family in PIXEL_PORTRAIT_PLAN.families:
        composed = workspace.compose(
            state=state,
            scope=CompositeScope.FAMILY,
            family_id=family.family_id,
            created_at=NOW,
        )
        approved = composed.model_copy(update={"status": CompositeStatus.APPROVED})
        approved_families.append(approved)
        state = approve_composite(state, composed)

    master = workspace.compose(
        state=state,
        scope=CompositeScope.PACKAGE_MASTER,
        family_id=None,
        created_at=NOW,
    )

    assert master.composite_id == "package-master-v1"
    assert master.member_ids == tuple(composite.composite_id for composite in approved_families)
    assert master.member_hashes == tuple(
        composite.artifact.sha256 for composite in approved_families
    )
    assert master.member_artifacts == tuple(composite.artifact for composite in approved_families)
    assert master.artifact.path == ("composites/package-master/package-master-v1/sheet.png")
    assert (master.artifact.width, master.artifact.height) == (4624, 3082)
    with Image.open(workspace.resolve_artifact(master.artifact.path)) as sheet:
        rgba = sheet.convert("RGBA")
        assert rgba.size == (4624, 3082)
        for index, composite in enumerate(approved_families):
            x = (index % 3) * 1542
            y = (index // 3) * 1028
            with Image.open(workspace.resolve_artifact(composite.artifact.path)) as family_sheet:
                family_rgba = family_sheet.convert("RGBA")
                assert (
                    rgba.crop((x, y, x + family_rgba.width, y + family_rgba.height)).tobytes()
                    == family_rgba.tobytes()
                )
        assert rgba.getpixel((1540, 0)) == (0, 0, 0, 0)
        assert rgba.getpixel((1541, 1025)) == (0, 0, 0, 0)
        narrow = approved_families[3]
        assert narrow.artifact.width == 1026
        narrow_x = 0
        narrow_y = 1028
        assert rgba.getpixel((narrow_x + 1026, narrow_y)) == (0, 0, 0, 0)

    approved_master = master.model_copy(update={"status": CompositeStatus.APPROVED})
    master_approval = CompositeApproval(
        approval_id=f"approve-{master.composite_id}",
        composite_id=master.composite_id,
        approver="Synthetic reviewer",
        decided_at=NOW,
        reviewed_artifacts=(master.artifact.path,),
        notes="Synthetic package-master approval.",
    )
    active_master_state = PixelPortraitAuthoringState.model_validate(
        state.model_copy(
            update={
                "revision": state.revision.model_copy(
                    update={
                        "master_reference": master.artifact.model_copy(
                            update={"path": PACKAGE_MASTER_PATH}
                        )
                    }
                ),
                "composites": (*state.composites, approved_master),
                "composite_approvals": (*state.composite_approvals, master_approval),
                "active_composite_ids": (*state.active_composite_ids, master.composite_id),
            }
        ).model_dump(mode="python")
    )
    workspace.validate(active_master_state)

    stale_master = approved_master.model_copy(update={"status": CompositeStatus.STALE})
    stale_master_state = PixelPortraitAuthoringState.model_validate(
        active_master_state.model_copy(
            update={
                "revision": active_master_state.revision.model_copy(
                    update={"master_reference": None}
                ),
                "composites": (*active_master_state.composites[:-1], stale_master),
                "active_composite_ids": active_master_state.active_composite_ids[:-1],
            }
        ).model_dump(mode="python")
    )
    workspace.validate(stale_master_state)


def test_package_master_requires_all_nine_current_approved_families(
    tmp_path: Path,
) -> None:
    workspace, initial, _, _ = initialized_workspace(tmp_path)
    family = PIXEL_PORTRAIT_PLAN.families[0]
    state = approved_state_for_families(workspace, initial, (family.family_id,))
    state = approve_composite(
        state,
        workspace.compose(
            state=state,
            scope=CompositeScope.FAMILY,
            family_id=family.family_id,
            created_at=NOW,
        ),
    )

    with pytest.raises(PackageIntegrityError, match="exactly one current approved"):
        workspace.compose(
            state=state,
            scope=CompositeScope.PACKAGE_MASTER,
            family_id=None,
            created_at=NOW,
        )


def test_validate_rejects_tampered_composite_sheet_and_slot_map_but_accepts_stale_history(
    tmp_path: Path,
) -> None:
    workspace, initial, _, _ = initialized_workspace(tmp_path)
    family = PIXEL_PORTRAIT_PLAN.family("presence-states")
    state = approved_state_for_families(workspace, initial, (family.family_id,))
    state = approve_composite(
        state,
        workspace.compose(
            state=state,
            scope=CompositeScope.FAMILY,
            family_id=family.family_id,
            created_at=NOW,
        ),
    )
    stale = state.composites[0].model_copy(update={"status": CompositeStatus.STALE})
    stale_state = PixelPortraitAuthoringState.model_validate(
        state.model_copy(update={"composites": (stale,), "active_composite_ids": ()}).model_dump(
            mode="python"
        )
    )
    workspace.validate(stale_state)

    sheet_path = workspace.resolve_artifact(stale.artifact.path)
    original_sheet = sheet_path.read_bytes()
    sheet_path.write_bytes(png_bytes((1540, 1026), (1, 2, 3, 255)))
    with pytest.raises(PackageIntegrityError, match="composite sheet"):
        workspace.validate(stale_state)
    sheet_path.write_bytes(original_sheet)

    slot_map_path = sheet_path.with_name("slot-map.json")
    payload = json.loads(slot_map_path.read_text(encoding="utf-8"))
    payload["members"][0]["x"] = 2
    slot_map_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(PackageIntegrityError, match="slot map"):
        workspace.validate(stale_state)


def test_validate_stale_family_uses_exact_member_artifacts_for_same_hash_replacement(
    tmp_path: Path,
) -> None:
    workspace, initial, _, _ = initialized_workspace(tmp_path)
    family = PIXEL_PORTRAIT_PLAN.family("presence-states")
    state = approved_state_for_families(workspace, initial, (family.family_id,))
    state = approve_composite(
        state,
        workspace.compose(
            state=state,
            scope=CompositeScope.FAMILY,
            family_id=family.family_id,
            created_at=NOW,
        ),
    )
    replacement_panel_id = family.panel_ids[-1]
    panels = dict(state.panels)
    panels[replacement_panel_id] = same_hash_replacement_panel(
        workspace,
        panels[replacement_panel_id],
    )
    old_artifact = state.panels[replacement_panel_id].candidates[0].normalized_panel
    replacement_artifact = panels[replacement_panel_id].candidates[-1].normalized_panel
    assert old_artifact.path != replacement_artifact.path
    assert old_artifact.sha256 == replacement_artifact.sha256
    stale = state.composites[0].model_copy(update={"status": CompositeStatus.STALE})
    stale_state = PixelPortraitAuthoringState.model_validate(
        state.model_copy(
            update={
                "panels": panels,
                "composites": (stale,),
                "active_composite_ids": (),
            }
        ).model_dump(mode="python")
    )

    workspace.validate(stale_state)


def test_seal_publishes_schema_1_1_package_and_validates_offline(tmp_path: Path) -> None:
    workspace, initial, _, technical_package = initialized_workspace(
        tmp_path,
        base_rights=complete_rights(),
    )
    state = complete_sealable_state(workspace, initial)
    technical_before = snapshot_files(technical_package)
    destination = tmp_path / "published-pixel-package"

    evidence = workspace.seal(state, destination, NOW)

    package = json.loads((destination / "package.json").read_text(encoding="utf-8"))
    assert package["package_id"] == "juana-talking-bust-v2-pixel"
    assert package["schema_version"] == "1.1"
    assert package["profile"] == "pixel-talking-portrait"
    assert package["master_reference"]["path"] == PACKAGE_MASTER_PATH
    assert len(package["approved_reference_sheets"]) == 9
    assert [item["family_id"] for item in package["approved_reference_sheets"]] == [
        family.family_id for family in PIXEL_PORTRAIT_PLAN.families
    ]
    assert not (destination / "runtime").exists()
    assert all((destination / relative).is_dir() for relative in TECHNICAL_PACKAGE_DIRECTORIES)
    assert (destination / "sources/base-set").is_dir()
    assert (destination / "sources/talking-bust-v1").is_dir()
    assert (destination / "authoring/panel-validation-reports").is_dir()
    assert (destination / "authoring/composite-slot-maps").is_dir()
    assert (
        sum((destination / panel.package_path).is_file() for panel in PIXEL_PORTRAIT_PLAN.panels)
        == 49
    )
    assert (
        sum(
            (destination / family.sheet_package_path).is_file()
            for family in PIXEL_PORTRAIT_PLAN.families
        )
        == 9
    )
    assert (destination / PACKAGE_MASTER_PATH).is_file()
    assert set(evidence.file_hashes) == {
        path.relative_to(destination).as_posix()
        for path in destination.rglob("*")
        if path.is_file() and path.relative_to(destination).as_posix() != "seal.json"
    }
    assert FilesystemPixelPortraitWorkspace.validate_sealed_package(destination) == evidence
    assert snapshot_files(technical_package) == technical_before
    assert FilesystemAuthoringWorkspace.validate_sealed_package(technical_package)


def test_seal_rejects_existing_or_workspace_contained_destination_without_partial_output(
    tmp_path: Path,
) -> None:
    workspace, initial, _, _ = initialized_workspace(
        tmp_path,
        base_rights=complete_rights(),
    )
    state = complete_sealable_state(workspace, initial)
    existing = tmp_path / "existing-package"
    existing.mkdir()
    marker = existing / "marker.txt"
    marker.write_text("preserve", encoding="utf-8")

    with pytest.raises(PackageDestinationExistsError):
        workspace.seal(state, existing, NOW)
    with pytest.raises(WorkspacePathError, match="inside"):
        workspace.seal(state, workspace.root / "published", NOW)

    real_publish_parent = tmp_path / "real-publish-parent"
    real_publish_parent.mkdir()
    linked_publish_parent = tmp_path / "linked-publish-parent"
    create_directory_link(linked_publish_parent, real_publish_parent)
    with pytest.raises(WorkspacePathError, match="ancestry"):
        workspace.seal(state, linked_publish_parent / "published", NOW)

    assert marker.read_text(encoding="utf-8") == "preserve"
    assert not (workspace.root / "published").exists()
    assert not tuple(tmp_path.glob(".published-pixel-package.seal-*.tmp"))


def write_canonical_json(path: Path, payload: object) -> None:
    path.write_bytes((json.dumps(payload, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def refresh_outer_seal(
    package: Path,
    *,
    seal_updates: dict[str, object] | None = None,
) -> SealEvidence:
    current = SealEvidence.model_validate_json((package / "seal.json").read_text(encoding="utf-8"))
    file_hashes = {
        path.relative_to(package).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(package.rglob("*"))
        if path.is_file() and path.relative_to(package).as_posix() != "seal.json"
    }
    refreshed = current.model_copy(update={"file_hashes": file_hashes, **(seal_updates or {})})
    write_canonical_json(
        package / "seal.json",
        refreshed.model_dump(mode="json"),
    )
    return refreshed


@pytest.fixture(scope="module")
def sealed_pixel_package(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("sealed-pixel-package")
    workspace, initial, _, _ = initialized_workspace(
        root,
        base_rights=complete_rights(),
    )
    destination = root / "package"
    workspace.seal(complete_sealable_state(workspace, initial), destination, NOW)
    return destination


def copy_sealed_package(source: Path, destination: Path) -> Path:
    shutil.copytree(source, destination)
    return destination


@pytest.mark.parametrize(
    "relative_path",
    (
        "sources/base-set/juana-avatar-character-sheet.png",
        PIXEL_PORTRAIT_PLAN.panels[0].package_path,
        "authoring/panel-validation-reports/presence-neutral.json",
        "authoring/composite-slot-maps/presence-states.json",
    ),
)
def test_offline_validation_rejects_source_panel_report_and_slot_map_mutation(
    sealed_pixel_package: Path,
    tmp_path: Path,
    relative_path: str,
) -> None:
    package = copy_sealed_package(sealed_pixel_package, tmp_path / "mutated")
    change_one_byte(package / relative_path)

    with pytest.raises(PackageIntegrityError, match="digest mismatch"):
        FilesystemPixelPortraitWorkspace.validate_sealed_package(package)


@pytest.mark.parametrize(
    "mutation",
    (
        "panel_approver",
        "panel_decided_at",
        "panel_notes",
        "panel_decision",
        "panel_identity_lock",
        "panel_review_scope",
        "composite_approver",
        "composite_decided_at",
        "composite_notes",
        "composite_decision",
        "composite_review_scope",
    ),
)
def test_offline_validation_rejects_resealed_approval_evidence_rewrite(
    sealed_pixel_package: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    package = copy_sealed_package(sealed_pixel_package, tmp_path / "mutated")
    path = package / "approvals.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    if mutation.startswith("panel_"):
        approval = payload["panel_decisions"][0]
    else:
        approval = payload["composite_approvals"][0]

    if mutation.endswith("approver"):
        approval["approver"] = "Mallory"
    elif mutation.endswith("decided_at"):
        approval["decided_at"] = "2030-01-01T00:00:00+00:00"
    elif mutation.endswith("notes"):
        approval["notes"] = "Rewritten approval evidence."
    elif mutation == "panel_decision":
        approval["decision"] = "reject"
        approval["identity_lock"] = None
    elif mutation == "panel_identity_lock":
        approval["identity_lock"]["palette_max_colors"] = 32
    elif mutation == "panel_review_scope":
        approval["reviewed_artifacts"] = [PIXEL_PORTRAIT_PLAN.panels[0].package_path]
    elif mutation == "composite_decision":
        approval["decision"] = "reject"
    else:
        approval["reviewed_artifacts"] = [PIXEL_PORTRAIT_PLAN.panels[0].package_path]

    write_canonical_json(path, payload)
    refresh_outer_seal(package)

    with pytest.raises(PackageIntegrityError):
        FilesystemPixelPortraitWorkspace.validate_sealed_package(package)


@pytest.mark.parametrize(
    "mutation",
    (
        "schema",
        "profile",
        "master",
        "panel_inventory",
        "family_inventory",
        "timestamps",
    ),
)
def test_offline_validation_rejects_noncanonical_package_metadata(
    sealed_pixel_package: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    package = copy_sealed_package(sealed_pixel_package, tmp_path / "mutated")
    if mutation in {"schema", "profile", "master", "family_inventory", "timestamps"}:
        path = package / "package.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "schema":
            payload["schema_version"] = "9.9"
        elif mutation == "profile":
            payload["profile"] = "wrong-profile"
        elif mutation == "master":
            payload["master_reference"]["path"] = "references/master/wrong.png"
        elif mutation == "timestamps":
            payload["created_at"] = "2030-01-01T00:00:00+00:00"
            payload["updated_at"] = "2030-01-01T00:00:00+00:00"
        else:
            payload["approved_reference_sheets"].pop()
    else:
        path = package / "authoring/panel-definitions.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["panels"].pop()
    write_canonical_json(path, payload)
    refresh_outer_seal(package)

    with pytest.raises(PackageIntegrityError):
        FilesystemPixelPortraitWorkspace.validate_sealed_package(package)


@pytest.mark.parametrize("mutation", ("missing", "extra", "digest", "runtime"))
def test_offline_validation_rejects_manifest_and_runtime_drift(
    sealed_pixel_package: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    package = copy_sealed_package(sealed_pixel_package, tmp_path / "mutated")
    if mutation == "missing":
        (package / "authoring/pixel-style.json").unlink()
        refresh_outer_seal(package)
    elif mutation == "extra":
        write_canonical_json(package / "authoring/extra.json", {"extra": True})
        refresh_outer_seal(package)
    elif mutation == "runtime":
        runtime = package / "runtime"
        runtime.mkdir()
        (runtime / "portrait.png").write_bytes(png_bytes((1, 1)))
        refresh_outer_seal(package)
    else:
        change_one_byte(package / "package.json")

    with pytest.raises(PackageIntegrityError):
        FilesystemPixelPortraitWorkspace.validate_sealed_package(package)


@pytest.mark.parametrize("mutation", ("rights", "blocking_gap", "path_escape"))
def test_offline_validation_rejects_rights_gaps_and_unsafe_metadata_paths(
    sealed_pixel_package: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    package = copy_sealed_package(sealed_pixel_package, tmp_path / "mutated")
    seal_updates: dict[str, object] = {}
    if mutation == "rights":
        path = package / "provenance.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["records"][0]["rights"]["license"] = None
    elif mutation == "blocking_gap":
        path = package / "gaps.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["gaps"].append(
            GapRecord(
                gap_id="blocking-fixture",
                area="visual-review",
                description="Synthetic blocking gap.",
                blocks_visual_seal=True,
            ).model_dump(mode="json")
        )
        seal_updates["unresolved_gap_ids"] = ("blocking-fixture",)
    else:
        path = package / "package.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["master_reference"]["path"] = "../escape.png"
    write_canonical_json(path, payload)
    refresh_outer_seal(package, seal_updates=seal_updates)

    with pytest.raises(PackageIntegrityError):
        FilesystemPixelPortraitWorkspace.validate_sealed_package(package)


@pytest.mark.parametrize("mutation", ("non_alpha", "dimensions"))
def test_offline_validation_rejects_master_alpha_and_dimension_drift(
    sealed_pixel_package: Path,
    tmp_path: Path,
    mutation: str,
) -> None:
    package = copy_sealed_package(sealed_pixel_package, tmp_path / "mutated")
    if mutation == "non_alpha":
        image = Image.new("RGB", (4624, 3082), (20, 40, 60))
    else:
        image = Image.new("RGBA", (64, 64), (20, 40, 60, 255))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    image.close()
    data = buffer.getvalue()
    (package / PACKAGE_MASTER_PATH).write_bytes(data)
    with Image.open(io.BytesIO(data)) as updated:
        width, height = updated.size
    artifact = artifact_evidence(
        PACKAGE_MASTER_PATH,
        data,
        width=width,
        height=height,
    ).model_dump(mode="json")
    package_payload = json.loads((package / "package.json").read_text(encoding="utf-8"))
    package_payload["master_reference"] = artifact
    write_canonical_json(package / "package.json", package_payload)
    provenance = json.loads((package / "provenance.json").read_text(encoding="utf-8"))
    next(
        record
        for record in provenance["records"]
        if record["provenance_id"] == "pixel-package-master"
    )["artifact"] = artifact
    write_canonical_json(package / "provenance.json", provenance)
    composites = json.loads(
        (package / "authoring/composite-sheets.json").read_text(encoding="utf-8")
    )
    composites["active_master"]["package_artifact"] = artifact
    write_canonical_json(package / "authoring/composite-sheets.json", composites)
    refresh_outer_seal(package)

    message = "alpha channel" if mutation == "non_alpha" else "not deterministic"
    with pytest.raises(PackageIntegrityError, match=message):
        FilesystemPixelPortraitWorkspace.validate_sealed_package(package)


def test_offline_validation_rejects_symlink_entry_when_supported(
    sealed_pixel_package: Path,
    tmp_path: Path,
) -> None:
    package = copy_sealed_package(sealed_pixel_package, tmp_path / "mutated")
    target = package / PIXEL_PORTRAIT_PLAN.panels[0].package_path
    outside = tmp_path / "outside.png"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    try:
        os.symlink(outside, target)
    except OSError as exc:
        pytest.skip(f"File symlinks are unavailable in this environment: {exc}")

    with pytest.raises(PackageIntegrityError, match="links or reparse"):
        FilesystemPixelPortraitWorkspace.validate_sealed_package(package)


def test_seal_preconditions_reject_rights_gap_panels_composites_and_master(
    tmp_path: Path,
) -> None:
    workspace, initial, _, _ = initialized_workspace(
        tmp_path,
        base_rights=complete_rights(),
    )
    state = complete_sealable_state(workspace, initial)
    final_panel = PIXEL_PORTRAIT_PLAN.panels[-1].panel_id
    variants = (
        state.model_copy(
            update={
                "revision": state.revision.model_copy(
                    update={"base_source_rights": RightsMetadata()}
                )
            }
        ),
        state.model_copy(
            update={
                "gaps": (
                    GapRecord(
                        gap_id="blocking-fixture",
                        area="visual-review",
                        description="Synthetic blocking gap.",
                        blocks_visual_seal=True,
                    ),
                )
            }
        ),
        state.model_copy(
            update={
                "panels": {
                    **state.panels,
                    final_panel: state.panels[final_panel].model_copy(
                        update={"progress": PanelProgress.PENDING}
                    ),
                }
            }
        ),
        state.model_copy(update={"active_composite_ids": state.active_composite_ids[:-1]}),
        state.model_copy(
            update={"revision": state.revision.model_copy(update={"master_reference": None})}
        ),
    )

    for invalid in variants:
        with pytest.raises(PackageSealError):
            workspace._validate_seal_state(invalid)


def test_seal_build_and_offline_validation_failures_leave_no_destination_or_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace, initial, _, _ = initialized_workspace(
        tmp_path,
        base_rights=complete_rights(),
    )
    state = complete_sealable_state(workspace, initial)
    original_writer = FilesystemPixelPortraitWorkspace._write_pixel_package_metadata
    original_validator = FilesystemPixelPortraitWorkspace.validate_sealed_package.__func__

    def fail_build(*args: object, **kwargs: object) -> tuple[str, ...]:
        raise PackageSealError("Injected package build failure.")

    monkeypatch.setattr(
        FilesystemPixelPortraitWorkspace,
        "_write_pixel_package_metadata",
        fail_build,
    )
    build_destination = tmp_path / "build-failure"
    with pytest.raises(PackageSealError, match="Injected package build"):
        workspace.seal(state, build_destination, NOW)
    assert not build_destination.exists()
    assert not tuple(tmp_path.glob(".build-failure.seal-*.tmp"))

    monkeypatch.setattr(
        FilesystemPixelPortraitWorkspace,
        "_write_pixel_package_metadata",
        original_writer,
    )

    def fail_validation(cls: type[FilesystemPixelPortraitWorkspace], root: Path) -> SealEvidence:
        raise PackageIntegrityError("Injected offline validation failure.")

    monkeypatch.setattr(
        FilesystemPixelPortraitWorkspace,
        "validate_sealed_package",
        classmethod(fail_validation),
    )
    validation_destination = tmp_path / "validation-failure"
    with pytest.raises(PackageIntegrityError, match="Injected offline validation"):
        workspace.seal(state, validation_destination, NOW)
    assert not validation_destination.exists()
    assert not tuple(tmp_path.glob(".validation-failure.seal-*.tmp"))
    monkeypatch.setattr(
        FilesystemPixelPortraitWorkspace,
        "validate_sealed_package",
        classmethod(original_validator),
    )
