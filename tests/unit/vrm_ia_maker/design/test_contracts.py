"""Unit tests for bounded character-reference authoring contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import TypeAdapter, ValidationError

from vrm_ia_maker.design.contracts import (
    ApprovalDecision,
    ApprovalRecord,
    ArtifactEvidence,
    AuthoringState,
    CandidateRecord,
    CandidateStatus,
    CharacterDesignPackageRevision,
    GapRecord,
    GenerationAttempt,
    GenerationAttemptStatus,
    PackageRelativePath,
    ProvenanceRecord,
    RightsMetadata,
    SealEvidence,
    SourceClass,
    TaskProgress,
    TaskState,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
NOW = datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


def artifact(path: str, digest: str = DIGEST_A) -> ArtifactEvidence:
    return ArtifactEvidence(
        path=path,
        sha256=digest,
        byte_length=128,
        width=1024,
        height=1024,
    )


@pytest.mark.parametrize(
    "unsafe_path",
    [
        "",
        ".",
        "../master.png",
        "references/../master.png",
        "/references/master.png",
        "C:/references/master.png",
        "references\\master.png",
        "references//master.png",
        "references/./master.png",
        "references/master.png\x00ignored",
    ],
)
def test_package_relative_path_rejects_unsafe_values(unsafe_path: str) -> None:
    adapter = TypeAdapter(PackageRelativePath)

    with pytest.raises(ValidationError, match="normalized POSIX package-relative path"):
        adapter.validate_python(unsafe_path)


def test_visual_revision_round_trips_strict_contract_data() -> None:
    revision = CharacterDesignPackageRevision(
        package_id="juana-talking-bust",
        character_id="juana",
        display_name="Juana",
        revision="1.0.0",
        master_reference=artifact("references/master/Juana-full-concept-white.png"),
        height_meters=1.70,
    )

    restored = CharacterDesignPackageRevision.model_validate_json(revision.model_dump_json())

    assert restored == revision
    assert restored.master_reference.path == (
        "references/master/Juana-full-concept-white.png"
    )


def test_visual_revision_rejects_unknown_fields() -> None:
    payload = {
        "package_id": "juana-talking-bust",
        "character_id": "juana",
        "display_name": "Juana",
        "revision": "1.0.0",
        "master_reference": artifact("references/master/master.png").model_dump(
            mode="json"
        ),
        "invented_measurements": {"head_width": 0.16},
    }

    with pytest.raises(ValidationError, match="invented_measurements"):
        CharacterDesignPackageRevision.model_validate(payload)


def test_provenance_can_record_an_explicitly_incomplete_rights_review() -> None:
    provenance = ProvenanceRecord(
        provenance_id="master-source",
        source_class=SourceClass.CREATIVE_CANON,
        artifact=artifact("references/master/master.png"),
        authoritative_source="User-supplied repository image",
        rights=RightsMetadata(author="Katherine E. Aguirre"),
    )

    assert provenance.rights is not None
    assert provenance.rights.is_complete is False


def test_complete_rights_metadata_requires_strict_boolean_values() -> None:
    with pytest.raises(ValidationError, match="boolean"):
        RightsMetadata.model_validate(
            {
                "author": "Katherine E. Aguirre",
                "rights_holder": "Katherine E. Aguirre",
                "license": "All rights reserved",
                "commercial_use": "yes",
                "modification_allowed": True,
                "redistribution_allowed": False,
                "attribution": "Katherine E. Aguirre",
            }
        )


def test_failed_attempt_requires_a_sanitized_error_and_no_candidate() -> None:
    with pytest.raises(ValidationError, match="Failed attempts require error_code"):
        GenerationAttempt(
            attempt_id="face-turnaround-1",
            task_id="face-turnaround",
            attempt=1,
            status=GenerationAttemptStatus.FAILED,
            started_at=NOW,
            completed_at=NOW,
        )


def test_successful_attempt_requires_a_candidate_reference() -> None:
    with pytest.raises(ValidationError, match="Successful attempts require candidate_id"):
        GenerationAttempt(
            attempt_id="face-turnaround-1",
            task_id="face-turnaround",
            attempt=1,
            status=GenerationAttemptStatus.CANDIDATE_READY,
            started_at=NOW,
            completed_at=NOW,
        )


def test_approved_task_requires_matching_candidate_and_full_review_scope() -> None:
    sheet = artifact("candidates/face-turnaround/attempt-1/sheet.png")
    preview = artifact(
        "candidates/face-turnaround/attempt-1/previews/front.png",
        DIGEST_B,
    )
    candidate = CandidateRecord(
        candidate_id="face-turnaround-1",
        task_id="face-turnaround",
        attempt=1,
        status=CandidateStatus.APPROVED,
        provider="fake",
        model="fake-image-model",
        prompt_id="talking-bust.face-turnaround",
        prompt_version="1.0",
        input_artifacts=(artifact("inputs/master.png"),),
        sheet=sheet,
        previews=(preview,),
        created_at=NOW,
    )
    attempt = GenerationAttempt(
        attempt_id="face-turnaround-1",
        task_id="face-turnaround",
        attempt=1,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        candidate_id=candidate.candidate_id,
        started_at=NOW,
        completed_at=NOW,
    )
    incomplete_approval = ApprovalRecord(
        approval_id="approval-face-turnaround-1",
        task_id="face-turnaround",
        candidate_id=candidate.candidate_id,
        decision=ApprovalDecision.APPROVE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=(sheet.path,),
        notes="The sheet preserves Juana's identity.",
    )

    with pytest.raises(ValidationError, match="sheet and every preview"):
        TaskState(
            task_id="face-turnaround",
            progress=TaskProgress.APPROVED,
            attempts=(attempt,),
            candidates=(candidate,),
            decisions=(incomplete_approval,),
            approved_candidate_id=candidate.candidate_id,
        )


def test_approved_candidate_can_be_superseded_without_erasing_approval() -> None:
    sheet = artifact("candidates/outfit-construction/attempt-1/sheet.png")
    preview = artifact(
        "candidates/outfit-construction/attempt-1/previews/front.png",
        DIGEST_B,
    )
    candidate = CandidateRecord(
        candidate_id="outfit-construction-attempt-1",
        task_id="outfit-construction",
        attempt=1,
        status=CandidateStatus.SUPERSEDED,
        provider="fake",
        model="fake-image-model",
        prompt_id="talking-bust.outfit-construction",
        prompt_version="1.1",
        input_artifacts=(artifact("inputs/master.png"),),
        sheet=sheet,
        previews=(preview,),
        created_at=NOW,
    )
    reviewed = (sheet.path, preview.path)
    approval = ApprovalRecord(
        approval_id="approve-outfit-construction-attempt-1",
        task_id="outfit-construction",
        candidate_id=candidate.candidate_id,
        decision=ApprovalDecision.APPROVE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=reviewed,
        notes="Approved before the canonical neckline changed.",
    )
    supersession = ApprovalRecord(
        approval_id="supersede-outfit-construction-attempt-1",
        task_id="outfit-construction",
        candidate_id=candidate.candidate_id,
        decision=ApprovalDecision.SUPERSEDE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=reviewed,
        notes="Superseded by the canonical open-zip outfit direction.",
    )
    attempt = GenerationAttempt(
        attempt_id="outfit-construction-attempt-1",
        task_id="outfit-construction",
        attempt=1,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        candidate_id=candidate.candidate_id,
        started_at=NOW,
        completed_at=NOW,
    )

    state = TaskState(
        task_id="outfit-construction",
        progress=TaskProgress.RETRY_READY,
        attempts=(attempt,),
        candidates=(candidate,),
        decisions=(approval, supersession),
    )

    assert state.candidates[0].status is CandidateStatus.SUPERSEDED
    assert tuple(decision.decision for decision in state.decisions) == (
        ApprovalDecision.APPROVE,
        ApprovalDecision.SUPERSEDE,
    )


def test_authoring_state_rejects_task_dictionary_key_drift() -> None:
    revision = CharacterDesignPackageRevision(
        package_id="juana-talking-bust",
        character_id="juana",
        display_name="Juana",
        revision="1.0.0",
        master_reference=artifact("inputs/master.png"),
    )

    with pytest.raises(ValidationError, match="Task dictionary keys"):
        AuthoringState(
            revision=revision,
            plan_id="talking-bust-v1",
            plan_version="1.0",
            tasks={"wrong-key": TaskState(task_id="face-turnaround")},
        )


def test_gap_and_seal_contracts_reject_extra_fields() -> None:
    gap = GapRecord(
        gap_id="measurements-missing",
        area="measurements",
        description="Metric measurements require a later approved source.",
        blocks_visual_seal=False,
    )
    evidence = SealEvidence(
        package_id="juana-talking-bust",
        revision="1.0.0",
        sealed_at=NOW,
        file_hashes={"package.json": DIGEST_A},
        approval_ids=("approval-package",),
        provenance_ids=("master-source",),
        unresolved_gap_ids=(gap.gap_id,),
    )
    payload = evidence.model_dump(mode="json")
    payload["unexpected"] = True

    with pytest.raises(ValidationError, match="unexpected"):
        SealEvidence.model_validate(payload)
