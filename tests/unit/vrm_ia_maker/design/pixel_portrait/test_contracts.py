"""Unit tests for strict panel-first pixel portrait contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

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
from vrm_ia_maker.design.pixel_portrait.contracts import (
    PACKAGE_MASTER_PATH,
    CompositeApproval,
    CompositeReviewSheet,
    CompositeScope,
    CompositeStatus,
    HairOrientation,
    LogicalPoint,
    LogicalRect,
    PanelProgress,
    PanelRuntimeRole,
    PixelPackageRevision,
    PixelPanelApproval,
    PixelPanelCandidate,
    PixelPanelState,
    PixelPortraitAuthoringState,
    PortraitIdentityLock,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64
DIGEST_D = "d" * 64
NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
NEUTRAL_PANEL_ID = "presence-neutral"


def artifact(
    path: str,
    digest: str = DIGEST_A,
    *,
    width: int = 512,
    height: int = 512,
) -> ArtifactEvidence:
    return ArtifactEvidence(
        path=path,
        sha256=digest,
        byte_length=128,
        width=width,
        height=height,
    )


def source_seal() -> SealEvidence:
    return SealEvidence(
        package_id="juana-talking-bust-v1",
        revision="2026-07-16-gh-19-r2",
        sealed_at=NOW,
        file_hashes={"package.json": DIGEST_A},
        approval_ids=("approval-source-package",),
        provenance_ids=("source-package",),
    )


def package_revision(
    master_reference: ArtifactEvidence | None = None,
) -> PixelPackageRevision:
    return PixelPackageRevision(
        package_id="juana-talking-bust-v2-pixel",
        identity="juana",
        revision="2026-07-21-gh-23-r1",
        base_sources=(
            artifact("sources/base-set/character-sheet.png", DIGEST_A),
            artifact("sources/base-set/neutral.png", DIGEST_B),
        ),
        base_source_rights=RightsMetadata(author="Katherine E. Aguirre"),
        technical_source_seal=source_seal(),
        master_reference=master_reference,
    )


def identity_lock(*, palette_sha256: str = DIGEST_A) -> PortraitIdentityLock:
    return PortraitIdentityLock(
        palette_sha256=palette_sha256,
        palette_max_colors=64,
        pivot=LogicalPoint(x=128, y=224),
        eye_rect=LogicalRect(x=80, y=72, width=96, height=24),
        mouth_rect=LogicalRect(x=96, y=136, width=64, height=24),
        shoulders=(LogicalPoint(x=48, y=220), LogicalPoint(x=208, y=220)),
        face_top_y=40,
        chin_y=200,
    )


def panel_candidate(
    *,
    panel_id: str = NEUTRAL_PANEL_ID,
    attempt: int = 1,
    status: CandidateStatus = CandidateStatus.PENDING,
) -> PixelPanelCandidate:
    candidate_id = f"{panel_id}-attempt-{attempt}"
    root = f"candidates/{panel_id}/attempt-{attempt}"
    return PixelPanelCandidate(
        candidate_id=candidate_id,
        panel_id=panel_id,
        attempt=attempt,
        status=status,
        provider="fake",
        model="fake-image-model",
        prompt_id=f"pixel-portrait.{panel_id}",
        prompt_version="1.0",
        input_artifacts=(artifact("inputs/base-character-sheet.png", DIGEST_A),),
        raw_artifact=artifact(f"{root}/raw.png", DIGEST_B, width=1024, height=1024),
        normalized_panel=artifact(f"{root}/panel.png", DIGEST_C),
        validation_report=artifact(
            f"{root}/validation-report.json",
            DIGEST_D,
            width=1,
            height=1,
        ),
        created_at=NOW,
    )


def generation_attempt(
    candidate: PixelPanelCandidate,
    *,
    status: GenerationAttemptStatus = GenerationAttemptStatus.CANDIDATE_READY,
) -> GenerationAttempt:
    return GenerationAttempt(
        attempt_id=f"{candidate.panel_id}-attempt-{candidate.attempt}",
        task_id=candidate.panel_id,
        attempt=candidate.attempt,
        status=status,
        candidate_id=(
            candidate.candidate_id if status is GenerationAttemptStatus.CANDIDATE_READY else None
        ),
        started_at=NOW,
        completed_at=(NOW if status is not GenerationAttemptStatus.IN_PROGRESS else None),
    )


def failed_attempt(panel_id: str, attempt: int) -> GenerationAttempt:
    return GenerationAttempt(
        attempt_id=f"{panel_id}-attempt-{attempt}",
        task_id=panel_id,
        attempt=attempt,
        status=GenerationAttemptStatus.FAILED,
        started_at=NOW,
        completed_at=NOW,
        error_code="provider_failure",
        error_message="The provider request failed.",
    )


def panel_decision(
    candidate: PixelPanelCandidate,
    decision: ApprovalDecision,
    *,
    lock: PortraitIdentityLock | None = None,
) -> PixelPanelApproval:
    return PixelPanelApproval(
        approval_id=f"{decision.value}-{candidate.candidate_id}",
        candidate_id=candidate.candidate_id,
        panel_id=candidate.panel_id,
        decision=decision,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=(
            candidate.raw_artifact.path,
            candidate.normalized_panel.path,
            candidate.validation_report.path,
        ),
        notes=f"Human review decision: {decision.value}.",
        identity_lock=lock,
    )


def approved_panel_state(
    panel_id: str = NEUTRAL_PANEL_ID,
    *,
    lock: PortraitIdentityLock | None = None,
) -> PixelPanelState:
    candidate = panel_candidate(panel_id=panel_id, status=CandidateStatus.APPROVED)
    return PixelPanelState(
        panel_id=panel_id,
        progress=PanelProgress.APPROVED,
        attempts=(generation_attempt(candidate),),
        candidates=(candidate,),
        decisions=(
            panel_decision(
                candidate,
                ApprovalDecision.APPROVE,
                lock=lock,
            ),
        ),
        approved_candidate_id=candidate.candidate_id,
    )


def dependent_panel_state(progress: PanelProgress) -> PixelPanelState:
    panel_id = "presence-thinking"
    candidate = panel_candidate(panel_id=panel_id)
    if progress is PanelProgress.GENERATING:
        return PixelPanelState(
            panel_id=panel_id,
            progress=progress,
            attempts=(
                generation_attempt(
                    candidate,
                    status=GenerationAttemptStatus.IN_PROGRESS,
                ),
            ),
        )
    if progress is PanelProgress.CANDIDATE_READY:
        return PixelPanelState(
            panel_id=panel_id,
            progress=progress,
            attempts=(generation_attempt(candidate),),
            candidates=(candidate,),
        )
    if progress is PanelProgress.APPROVED:
        return approved_panel_state(panel_id=panel_id)
    raise AssertionError(f"Unsupported dependent panel progress: {progress}")


def family_composite(
    panel: PixelPanelState,
    *,
    composite_id: str = "family-presence-v1",
    status: CompositeStatus = CompositeStatus.APPROVED,
) -> CompositeReviewSheet:
    candidate = panel.candidates[0]
    return CompositeReviewSheet(
        composite_id=composite_id,
        scope=CompositeScope.FAMILY,
        family_id="presence-states",
        member_ids=(panel.panel_id,),
        member_hashes=(candidate.normalized_panel.sha256,),
        member_artifacts=(candidate.normalized_panel,),
        artifact=artifact("review-sheets/families/presence-states.png", DIGEST_D),
        composition_version="1.0",
        created_at=NOW,
        status=status,
    )


def composite_approval(composite: CompositeReviewSheet) -> CompositeApproval:
    return CompositeApproval(
        approval_id=f"approve-{composite.composite_id}",
        composite_id=composite.composite_id,
        decision=ApprovalDecision.APPROVE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=(composite.artifact.path,),
        notes="Composite is internally consistent.",
    )


def test_panel_first_enums_expose_only_the_approved_values() -> None:
    assert tuple(role.value for role in PanelRuntimeRole) == (
        "authoring_only",
        "state",
        "eye_patch",
        "mouth_patch",
    )
    assert tuple(scope.value for scope in CompositeScope) == (
        "family",
        "package_master",
    )
    assert tuple(status.value for status in CompositeStatus) == (
        "pending_review",
        "approved",
        "stale",
    )
    assert tuple(progress.value for progress in PanelProgress) == (
        "pending",
        "generating",
        "candidate_ready",
        "retry_ready",
        "approved",
        "exhausted",
    )
    assert HairOrientation.VIEWER_LEFT_SHAVE_VIEWER_RIGHT_LONG.value == (
        "viewer_left_shave_viewer_right_long"
    )


@pytest.mark.parametrize(
    ("contract", "message"),
    [
        (lambda: LogicalPoint(x=256, y=0), "less than 256"),
        (lambda: LogicalPoint(x=0, y=-1), "greater than or equal to 0"),
        (
            lambda: LogicalRect(x=250, y=10, width=7, height=10),
            "inside the 256 by 256 logical canvas",
        ),
        (
            lambda: LogicalRect(x=10, y=250, width=10, height=7),
            "inside the 256 by 256 logical canvas",
        ),
    ],
)
def test_logical_geometry_rejects_out_of_canvas_values(
    contract: object,
    message: str,
) -> None:
    with pytest.raises(ValidationError, match=message):
        contract()


def test_identity_lock_round_trips_fixed_geometry() -> None:
    lock = identity_lock()

    restored = PortraitIdentityLock.model_validate_json(lock.model_dump_json())

    assert restored == lock
    assert restored.logical_width == 256
    assert restored.logical_height == 256
    assert restored.file_width == 512
    assert restored.file_height == 512
    assert restored.face_height_target == 160
    assert restored.face_height_tolerance == 2
    assert restored.hair_orientation is HairOrientation.VIEWER_LEFT_SHAVE_VIEWER_RIGHT_LONG


@pytest.mark.parametrize("actual_face_height", [158, 159, 160, 161, 162])
def test_identity_lock_accepts_face_height_within_tolerance(
    actual_face_height: int,
) -> None:
    payload = identity_lock().model_dump()
    payload["face_top_y"] = 200 - actual_face_height

    lock = PortraitIdentityLock.model_validate(payload)

    assert lock.chin_y - lock.face_top_y == actual_face_height


@pytest.mark.parametrize("actual_face_height", [157, 163])
def test_identity_lock_rejects_face_height_outside_tolerance(
    actual_face_height: int,
) -> None:
    payload = identity_lock().model_dump()
    payload["face_top_y"] = 200 - actual_face_height

    with pytest.raises(ValidationError, match="target 160 with tolerance 2"):
        PortraitIdentityLock.model_validate(payload)


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"palette_max_colors": 65}, "less than or equal to 64"),
        (
            {
                "eye_rect": LogicalRect(x=80, y=150, width=96, height=24),
                "mouth_rect": LogicalRect(x=96, y=136, width=64, height=24),
            },
            "eyes above the mouth",
        ),
        (
            {
                "shoulders": (
                    LogicalPoint(x=208, y=220),
                    LogicalPoint(x=48, y=220),
                )
            },
            "viewer-left to viewer-right",
        ),
    ],
)
def test_identity_lock_rejects_invalid_geometry(
    overrides: dict[str, object],
    message: str,
) -> None:
    payload = identity_lock().model_dump()
    payload.update(overrides)

    with pytest.raises(ValidationError, match=message):
        PortraitIdentityLock.model_validate(payload)


def test_pixel_package_revision_round_trips_schema_1_1_source_metadata() -> None:
    revision = package_revision()

    restored = PixelPackageRevision.model_validate_json(revision.model_dump_json())

    assert restored == revision
    assert restored.schema_version == "1.1"
    assert restored.profile == "pixel-talking-portrait"
    assert restored.technical_source_seal.package_id == "juana-talking-bust-v1"


def test_pixel_package_revision_rejects_duplicate_source_paths_and_extra_fields() -> None:
    revision = package_revision()
    duplicate_payload = revision.model_dump()
    duplicate_payload["base_sources"] = (
        revision.base_sources[0],
        revision.base_sources[0],
    )

    with pytest.raises(ValidationError, match="Base source artifact paths must be unique"):
        PixelPackageRevision.model_validate(duplicate_payload)

    extra_payload = revision.model_dump(mode="json")
    extra_payload["invented_identity_measurement"] = 17
    with pytest.raises(ValidationError, match="invented_identity_measurement"):
        PixelPackageRevision.model_validate(extra_payload)


def test_panel_candidate_round_trips_all_attempt_evidence() -> None:
    candidate = panel_candidate()

    restored = PixelPanelCandidate.model_validate_json(candidate.model_dump_json())

    assert restored == candidate
    assert restored.attempt == 1
    assert restored.normalized_panel.width == 512


def test_panel_candidate_rejects_duplicate_artifact_paths() -> None:
    candidate = panel_candidate()
    payload = candidate.model_dump()
    payload["normalized_panel"] = candidate.raw_artifact

    with pytest.raises(ValidationError, match="Candidate artifact paths must be unique"):
        PixelPanelCandidate.model_validate(payload)


def test_panel_approval_identity_lock_is_only_allowed_for_neutral_approval() -> None:
    non_neutral = panel_candidate(panel_id="presence-thinking")

    with pytest.raises(ValidationError, match="only an approval of presence-neutral"):
        panel_decision(non_neutral, ApprovalDecision.APPROVE, lock=identity_lock())

    neutral = panel_candidate()
    with pytest.raises(ValidationError, match="only an approval of presence-neutral"):
        panel_decision(neutral, ApprovalDecision.REJECT, lock=identity_lock())


def test_panel_approval_is_immutable() -> None:
    candidate = panel_candidate()
    approval = panel_decision(candidate, ApprovalDecision.APPROVE, lock=identity_lock())

    with pytest.raises(ValidationError, match="frozen"):
        approval.notes = "Changed after review."


def test_panel_state_round_trips_valid_approved_history() -> None:
    lock = identity_lock()
    state = approved_panel_state(lock=lock)

    restored = PixelPanelState.model_validate_json(state.model_dump_json())

    assert restored == state
    assert restored.approved_candidate_id == state.candidates[0].candidate_id


def test_panel_state_rejects_noncontiguous_attempts() -> None:
    candidate = panel_candidate(attempt=2)

    with pytest.raises(ValidationError, match="contiguous and ordered"):
        PixelPanelState(
            panel_id=candidate.panel_id,
            progress=PanelProgress.CANDIDATE_READY,
            attempts=(generation_attempt(candidate),),
            candidates=(candidate,),
        )


def test_panel_state_rejects_candidate_attempt_reference_drift() -> None:
    candidate = panel_candidate(attempt=1)
    attempt = generation_attempt(candidate).model_copy(update={"candidate_id": "other-candidate"})

    with pytest.raises(ValidationError, match="matching recorded candidate"):
        PixelPanelState(
            panel_id=candidate.panel_id,
            progress=PanelProgress.CANDIDATE_READY,
            attempts=(attempt,),
            candidates=(candidate,),
        )


def test_candidate_ready_rejects_a_later_failed_attempt() -> None:
    candidate = panel_candidate(attempt=1)

    with pytest.raises(ValidationError, match="latest completed attempt"):
        PixelPanelState(
            panel_id=candidate.panel_id,
            progress=PanelProgress.CANDIDATE_READY,
            attempts=(
                generation_attempt(candidate),
                failed_attempt(candidate.panel_id, 2),
            ),
            candidates=(candidate,),
        )


def test_approved_rejects_a_later_failed_attempt() -> None:
    candidate = panel_candidate(attempt=1, status=CandidateStatus.APPROVED)
    approval = panel_decision(
        candidate,
        ApprovalDecision.APPROVE,
        lock=identity_lock(),
    )

    with pytest.raises(ValidationError, match="latest completed attempt"):
        PixelPanelState(
            panel_id=candidate.panel_id,
            progress=PanelProgress.APPROVED,
            attempts=(
                generation_attempt(candidate),
                failed_attempt(candidate.panel_id, 2),
            ),
            candidates=(candidate,),
            decisions=(approval,),
            approved_candidate_id=candidate.candidate_id,
        )


def test_panel_state_rejects_incomplete_review_scope() -> None:
    candidate = panel_candidate(status=CandidateStatus.APPROVED)
    approval = panel_decision(
        candidate,
        ApprovalDecision.APPROVE,
        lock=identity_lock(),
    ).model_copy(update={"reviewed_artifacts": (candidate.normalized_panel.path,)})

    with pytest.raises(ValidationError, match="raw, normalized, and validation artifacts"):
        PixelPanelState(
            panel_id=candidate.panel_id,
            progress=PanelProgress.APPROVED,
            attempts=(generation_attempt(candidate),),
            candidates=(candidate,),
            decisions=(approval,),
            approved_candidate_id=candidate.candidate_id,
        )


def test_panel_state_rejects_unsafe_decision_history() -> None:
    candidate = panel_candidate(status=CandidateStatus.APPROVED)
    rejection = panel_decision(candidate, ApprovalDecision.REJECT)
    approval = panel_decision(candidate, ApprovalDecision.APPROVE, lock=identity_lock())

    with pytest.raises(ValidationError, match="valid review history"):
        PixelPanelState(
            panel_id=candidate.panel_id,
            progress=PanelProgress.APPROVED,
            attempts=(generation_attempt(candidate),),
            candidates=(candidate,),
            decisions=(rejection, approval),
            approved_candidate_id=candidate.candidate_id,
        )


def test_panel_state_preserves_approve_then_supersede_history() -> None:
    candidate = panel_candidate(status=CandidateStatus.SUPERSEDED)
    approval = panel_decision(candidate, ApprovalDecision.APPROVE, lock=identity_lock())
    supersession = panel_decision(candidate, ApprovalDecision.SUPERSEDE)

    state = PixelPanelState(
        panel_id=candidate.panel_id,
        progress=PanelProgress.RETRY_READY,
        attempts=(generation_attempt(candidate),),
        candidates=(candidate,),
        decisions=(approval, supersession),
    )

    assert tuple(decision.decision for decision in state.decisions) == (
        ApprovalDecision.APPROVE,
        ApprovalDecision.SUPERSEDE,
    )


def test_panel_state_rejects_progress_that_disagrees_with_history() -> None:
    candidate = panel_candidate()

    with pytest.raises(ValidationError, match="Pending panels cannot contain attempts"):
        PixelPanelState(
            panel_id=candidate.panel_id,
            progress=PanelProgress.PENDING,
            attempts=(generation_attempt(candidate),),
            candidates=(candidate,),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {
            "composite_id": "family-presence-v1",
            "scope": CompositeScope.FAMILY,
            "member_ids": (NEUTRAL_PANEL_ID,),
            "member_hashes": (DIGEST_A,),
            "member_artifacts": (
                artifact("candidates/presence-neutral/attempt-1/panel.png", DIGEST_A),
            ),
        },
        {
            "composite_id": "package-master-v1",
            "scope": CompositeScope.PACKAGE_MASTER,
            "family_id": "presence-states",
            "member_ids": ("family-presence-v1",),
            "member_hashes": (DIGEST_A,),
            "member_artifacts": (
                artifact("composites/family/family-presence-v1/sheet.png", DIGEST_A),
            ),
        },
    ],
)
def test_composite_scope_rejects_invalid_family_id_presence(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError, match="family_id"):
        CompositeReviewSheet(
            **payload,
            artifact=artifact("review-sheets/composite.png"),
            composition_version="1.0",
            created_at=NOW,
        )


def test_composite_rejects_duplicate_members_and_hash_count_drift() -> None:
    common = {
        "composite_id": "family-presence-v1",
        "scope": CompositeScope.FAMILY,
        "family_id": "presence-states",
        "artifact": artifact("review-sheets/families/presence-states.png"),
        "composition_version": "1.0",
        "created_at": NOW,
    }

    with pytest.raises(ValidationError, match="Member identifiers must be unique"):
        CompositeReviewSheet(
            **common,
            member_ids=(NEUTRAL_PANEL_ID, NEUTRAL_PANEL_ID),
            member_hashes=(DIGEST_A, DIGEST_B),
            member_artifacts=(
                artifact("candidates/presence-neutral/attempt-1/panel.png", DIGEST_A),
                artifact("candidates/presence-neutral/attempt-2/panel.png", DIGEST_B),
            ),
        )

    with pytest.raises(ValidationError, match="one ordered hash per member"):
        CompositeReviewSheet(
            **common,
            member_ids=(NEUTRAL_PANEL_ID, "presence-thinking"),
            member_hashes=(DIGEST_A,),
            member_artifacts=(
                artifact("candidates/presence-neutral/attempt-1/panel.png", DIGEST_A),
            ),
        )


def test_composite_records_exact_ordered_member_artifact_evidence() -> None:
    member = artifact("candidates/presence-neutral/attempt-1/panel.png", DIGEST_A)

    composite = CompositeReviewSheet(
        composite_id="family-presence-v1",
        scope=CompositeScope.FAMILY,
        family_id="presence-states",
        member_ids=(NEUTRAL_PANEL_ID,),
        member_hashes=(DIGEST_A,),
        member_artifacts=(member,),
        artifact=artifact("composites/family/family-presence-v1/sheet.png", DIGEST_B),
        composition_version="pixel-grid-v1",
        created_at=NOW,
    )

    assert composite.member_artifacts == (member,)


def test_composite_requires_member_artifact_evidence() -> None:
    with pytest.raises(
        ValidationError,
        match="Composite member artifact evidence is required",
    ):
        CompositeReviewSheet(
            composite_id="family-presence-v1",
            scope=CompositeScope.FAMILY,
            family_id="presence-states",
            member_ids=(NEUTRAL_PANEL_ID,),
            member_hashes=(DIGEST_A,),
            artifact=artifact(
                "composites/family/family-presence-v1/sheet.png",
                DIGEST_B,
            ),
            composition_version="pixel-grid-v1",
            created_at=NOW,
        )


@pytest.mark.parametrize(
    "member_artifacts",
    (
        (),
        (
            artifact("candidates/presence-neutral/attempt-1/panel.png", DIGEST_A),
            artifact("candidates/presence-thinking/attempt-1/panel.png", DIGEST_B),
        ),
        (artifact("candidates/presence-neutral/attempt-1/panel.png", DIGEST_B),),
    ),
)
def test_composite_rejects_misaligned_member_artifact_evidence(
    member_artifacts: tuple[ArtifactEvidence, ...],
) -> None:
    with pytest.raises(ValidationError, match="member artifact evidence"):
        CompositeReviewSheet(
            composite_id="family-presence-v1",
            scope=CompositeScope.FAMILY,
            family_id="presence-states",
            member_ids=(NEUTRAL_PANEL_ID,),
            member_hashes=(DIGEST_A,),
            member_artifacts=member_artifacts,
            artifact=artifact("composites/family/family-presence-v1/sheet.png", DIGEST_B),
            composition_version="pixel-grid-v1",
            created_at=NOW,
        )


def test_composite_rejects_duplicate_member_artifact_paths() -> None:
    duplicate_path = "candidates/presence-neutral/attempt-1/panel.png"

    with pytest.raises(ValidationError, match="member artifact evidence"):
        CompositeReviewSheet(
            composite_id="family-presence-v1",
            scope=CompositeScope.FAMILY,
            family_id="presence-states",
            member_ids=(NEUTRAL_PANEL_ID, "presence-thinking"),
            member_hashes=(DIGEST_A, DIGEST_B),
            member_artifacts=(
                artifact(duplicate_path, DIGEST_A),
                artifact(duplicate_path, DIGEST_B),
            ),
            artifact=artifact(
                "composites/family/family-presence-v1/sheet.png",
                DIGEST_C,
            ),
            composition_version="pixel-grid-v1",
            created_at=NOW,
        )


def test_composite_approval_only_records_approve_and_is_immutable() -> None:
    panel = approved_panel_state(lock=identity_lock())
    composite = family_composite(panel)
    payload = composite_approval(composite).model_dump()
    payload["decision"] = ApprovalDecision.REJECT

    with pytest.raises(ValidationError, match="approve"):
        CompositeApproval.model_validate(payload)

    approval = composite_approval(composite)
    with pytest.raises(ValidationError, match="frozen"):
        approval.notes = "Changed after review."


def test_authoring_state_round_trips_neutral_identity_lock() -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    state = PixelPortraitAuthoringState(
        revision=package_revision(),
        plan_id="juana-pixel-talking-portrait-v1",
        plan_version="1.0",
        panels={neutral.panel_id: neutral},
        identity_lock=lock,
    )

    restored = PixelPortraitAuthoringState.model_validate_json(state.model_dump_json())

    assert restored == state
    assert restored.schema_version == "1.1"


def test_authoring_state_requires_lock_exactly_while_neutral_is_approved() -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)

    with pytest.raises(ValidationError, match="Approved neutral panel requires identity_lock"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
        )

    with pytest.raises(ValidationError, match="identity_lock must be absent"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={NEUTRAL_PANEL_ID: PixelPanelState(panel_id=NEUTRAL_PANEL_ID)},
            identity_lock=lock,
        )


@pytest.mark.parametrize(
    "progress",
    [
        PanelProgress.GENERATING,
        PanelProgress.CANDIDATE_READY,
        PanelProgress.APPROVED,
    ],
)
def test_dependent_panel_activity_requires_neutral_identity_lock(
    progress: PanelProgress,
) -> None:
    dependent = dependent_panel_state(progress)

    with pytest.raises(ValidationError, match="Dependent panels must remain pending"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={dependent.panel_id: dependent},
        )


@pytest.mark.parametrize(
    "progress",
    [
        PanelProgress.GENERATING,
        PanelProgress.CANDIDATE_READY,
        PanelProgress.APPROVED,
    ],
)
def test_dependent_panel_activity_is_valid_after_neutral_identity_lock(
    progress: PanelProgress,
) -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    dependent = dependent_panel_state(progress)

    state = PixelPortraitAuthoringState(
        revision=package_revision(),
        plan_id="juana-pixel-talking-portrait-v1",
        plan_version="1.0",
        panels={
            neutral.panel_id: neutral,
            dependent.panel_id: dependent,
        },
        identity_lock=lock,
    )

    assert state.panels[dependent.panel_id] == dependent


def test_neutral_generation_is_valid_before_identity_lock() -> None:
    candidate = panel_candidate()
    neutral = PixelPanelState(
        panel_id=NEUTRAL_PANEL_ID,
        progress=PanelProgress.GENERATING,
        attempts=(
            generation_attempt(
                candidate,
                status=GenerationAttemptStatus.IN_PROGRESS,
            ),
        ),
    )

    state = PixelPortraitAuthoringState(
        revision=package_revision(),
        plan_id="juana-pixel-talking-portrait-v1",
        plan_version="1.0",
        panels={neutral.panel_id: neutral},
    )

    assert state.identity_lock is None


def test_authoring_state_rejects_panel_dictionary_key_drift() -> None:
    with pytest.raises(ValidationError, match="Panel dictionary keys"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={"wrong-key": PixelPanelState(panel_id="presence-thinking")},
        )


@pytest.mark.parametrize("status", tuple(CompositeStatus))
def test_inactive_family_composite_rejects_a_missing_panel_member(
    status: CompositeStatus,
) -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    missing_member = family_composite(neutral).model_copy(
        update={
            "status": status,
            "member_ids": ("presence-missing",),
        }
    )
    approvals = (composite_approval(missing_member),) if status is CompositeStatus.APPROVED else ()

    with pytest.raises(ValidationError, match="recorded panel"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
            composites=(missing_member,),
            composite_approvals=approvals,
            identity_lock=lock,
        )


@pytest.mark.parametrize("status", tuple(CompositeStatus))
def test_inactive_package_master_rejects_a_missing_family_composite(
    status: CompositeStatus,
) -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    master = CompositeReviewSheet(
        composite_id="package-master-v1",
        scope=CompositeScope.PACKAGE_MASTER,
        member_ids=("family-missing-v1",),
        member_hashes=(DIGEST_A,),
        member_artifacts=(artifact("composites/family/family-missing-v1/sheet.png", DIGEST_A),),
        artifact=artifact("references/master/master-character-sheet.png", DIGEST_B),
        composition_version="1.0",
        created_at=NOW,
        status=status,
    )
    approvals = (composite_approval(master),) if status is CompositeStatus.APPROVED else ()

    with pytest.raises(ValidationError, match="recorded family composite"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
            composites=(master,),
            composite_approvals=approvals,
            identity_lock=lock,
        )


def test_inactive_stale_composite_preserves_historical_member_evidence() -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    stale_family = family_composite(neutral).model_copy(update={"status": CompositeStatus.STALE})

    state = PixelPortraitAuthoringState(
        revision=package_revision(),
        plan_id="juana-pixel-talking-portrait-v1",
        plan_version="1.0",
        panels={neutral.panel_id: neutral},
        composites=(stale_family,),
        composite_approvals=(composite_approval(stale_family),),
        identity_lock=lock,
    )

    assert state.composites == (stale_family,)


def test_authoring_state_accepts_current_approved_family_and_master_composites() -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    family = family_composite(neutral)
    master_artifact = artifact(
        "composites/package-master/package-master-v1/sheet.png",
        DIGEST_B,
    )
    master = CompositeReviewSheet(
        composite_id="package-master-v1",
        scope=CompositeScope.PACKAGE_MASTER,
        member_ids=(family.composite_id,),
        member_hashes=(family.artifact.sha256,),
        member_artifacts=(family.artifact,),
        artifact=master_artifact,
        composition_version="1.0",
        created_at=NOW,
        status=CompositeStatus.APPROVED,
    )
    canonical_master = master_artifact.model_copy(update={"path": PACKAGE_MASTER_PATH})

    state = PixelPortraitAuthoringState(
        revision=package_revision(canonical_master),
        plan_id="juana-pixel-talking-portrait-v1",
        plan_version="1.0",
        panels={neutral.panel_id: neutral},
        composites=(family, master),
        composite_approvals=(
            composite_approval(family),
            composite_approval(master),
        ),
        active_composite_ids=(family.composite_id, master.composite_id),
        identity_lock=lock,
    )

    restored = PixelPortraitAuthoringState.model_validate_json(state.model_dump_json())

    assert restored == state


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("sha256", DIGEST_C),
        ("byte_length", 129),
        ("width", 513),
        ("height", 513),
    ),
)
def test_active_package_master_requires_canonical_content_equivalence(
    field: str,
    value: object,
) -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    family = family_composite(neutral)
    active_artifact = artifact(
        "composites/package-master/package-master-v1/sheet.png",
        DIGEST_B,
    )
    master = CompositeReviewSheet(
        composite_id="package-master-v1",
        scope=CompositeScope.PACKAGE_MASTER,
        member_ids=(family.composite_id,),
        member_hashes=(family.artifact.sha256,),
        member_artifacts=(family.artifact,),
        artifact=active_artifact,
        composition_version="pixel-grid-v1",
        created_at=NOW,
        status=CompositeStatus.APPROVED,
    )
    canonical_master = active_artifact.model_copy(
        update={"path": PACKAGE_MASTER_PATH, field: value}
    )

    with pytest.raises(ValidationError, match="content evidence"):
        PixelPortraitAuthoringState(
            revision=package_revision(canonical_master),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
            composites=(family, master),
            composite_approvals=(
                composite_approval(family),
                composite_approval(master),
            ),
            active_composite_ids=(family.composite_id, master.composite_id),
            identity_lock=lock,
        )


def test_active_package_master_requires_distinct_authoring_and_package_paths() -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    family = family_composite(neutral)
    canonical_artifact = artifact(PACKAGE_MASTER_PATH, DIGEST_B)
    master = CompositeReviewSheet(
        composite_id="package-master-v1",
        scope=CompositeScope.PACKAGE_MASTER,
        member_ids=(family.composite_id,),
        member_hashes=(family.artifact.sha256,),
        member_artifacts=(family.artifact,),
        artifact=canonical_artifact,
        composition_version="pixel-grid-v1",
        created_at=NOW,
        status=CompositeStatus.APPROVED,
    )

    with pytest.raises(ValidationError, match="paths must remain distinct"):
        PixelPortraitAuthoringState(
            revision=package_revision(canonical_artifact),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
            composites=(family, master),
            composite_approvals=(
                composite_approval(family),
                composite_approval(master),
            ),
            active_composite_ids=(family.composite_id, master.composite_id),
            identity_lock=lock,
        )


def test_authoring_state_rejects_stale_or_evidence_drifted_active_composites() -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    family = family_composite(neutral)

    stale = family.model_copy(update={"status": CompositeStatus.STALE})
    with pytest.raises(ValidationError, match="Active composites must be approved"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
            composites=(stale,),
            composite_approvals=(composite_approval(stale),),
            active_composite_ids=(stale.composite_id,),
            identity_lock=lock,
        )

    drifted = family.model_copy(
        update={
            "member_artifacts": (
                family.member_artifacts[0].model_copy(
                    update={"path": "candidates/presence-neutral/attempt-2/panel.png"}
                ),
            )
        }
    )
    with pytest.raises(ValidationError, match="recorded panel evidence"):
        PixelPortraitAuthoringState(
            revision=package_revision(),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
            composites=(drifted,),
            composite_approvals=(composite_approval(drifted),),
            active_composite_ids=(drifted.composite_id,),
            identity_lock=lock,
        )


def test_package_master_must_cover_every_active_family_composite() -> None:
    lock = identity_lock()
    neutral = approved_panel_state(lock=lock)
    family = family_composite(neutral)
    second_family = family.model_copy(
        update={
            "composite_id": "family-face-v1",
            "family_id": "face-turnaround",
            "artifact": artifact("review-sheets/families/face-turnaround.png", DIGEST_C),
        }
    )
    master_artifact = artifact(
        "composites/package-master/package-master-v1/sheet.png",
        DIGEST_B,
    )
    master = CompositeReviewSheet(
        composite_id="package-master-v1",
        scope=CompositeScope.PACKAGE_MASTER,
        member_ids=(family.composite_id,),
        member_hashes=(family.artifact.sha256,),
        member_artifacts=(family.artifact,),
        artifact=master_artifact,
        composition_version="1.0",
        created_at=NOW,
        status=CompositeStatus.APPROVED,
    )

    with pytest.raises(ValidationError, match="every active family composite"):
        PixelPortraitAuthoringState(
            revision=package_revision(
                master_artifact.model_copy(update={"path": PACKAGE_MASTER_PATH})
            ),
            plan_id="juana-pixel-talking-portrait-v1",
            plan_version="1.0",
            panels={neutral.panel_id: neutral},
            composites=(family, second_family, master),
            composite_approvals=(
                composite_approval(family),
                composite_approval(second_family),
                composite_approval(master),
            ),
            active_composite_ids=(
                family.composite_id,
                second_family.composite_id,
                master.composite_id,
            ),
            identity_lock=lock,
        )


def test_authoring_state_rejects_duplicate_history_ids_and_extra_fields() -> None:
    provenance = ProvenanceRecord(
        provenance_id="base-neutral",
        source_class=SourceClass.CREATIVE_CANON,
        artifact=artifact("sources/base-set/neutral.png"),
        authoritative_source="User-supplied base set",
        rights=RightsMetadata(author="Katherine E. Aguirre"),
    )
    gap = GapRecord(
        gap_id="source-rights-incomplete",
        area="rights",
        description="Base-set rights are incomplete.",
        blocks_visual_seal=True,
    )
    common = {
        "revision": package_revision(),
        "plan_id": "juana-pixel-talking-portrait-v1",
        "plan_version": "1.0",
        "panels": {},
    }

    with pytest.raises(ValidationError, match="Provenance identifiers must be unique"):
        PixelPortraitAuthoringState(
            **common,
            provenance=(provenance, provenance),
        )

    with pytest.raises(ValidationError, match="Gap identifiers must be unique"):
        PixelPortraitAuthoringState(
            **common,
            gaps=(gap, gap),
        )

    payload = PixelPortraitAuthoringState(**common).model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="unexpected"):
        PixelPortraitAuthoringState.model_validate(payload)
