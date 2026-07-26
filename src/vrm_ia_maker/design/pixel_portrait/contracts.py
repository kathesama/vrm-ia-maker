"""Strict contracts for panel-first pixel portrait authoring."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import AwareDatetime, ConfigDict, Field, model_validator

from ..contracts import (
    SHA256,
    ApprovalDecision,
    ArtifactEvidence,
    CandidateStatus,
    GapRecord,
    GenerationAttempt,
    GenerationAttemptStatus,
    NonEmptyString,
    PackageRelativePath,
    PositiveAttempt,
    ProvenanceRecord,
    RightsMetadata,
    SealEvidence,
    StrictDesignModel,
)

LOGICAL_CANVAS_SIZE = 256
NEUTRAL_PANEL_ID = "presence-neutral"
PACKAGE_MASTER_PATH = "references/master/master-character-sheet.png"

LogicalCoordinate = Annotated[
    int,
    Field(strict=True, ge=0, lt=LOGICAL_CANVAS_SIZE),
]
LogicalExtent = Annotated[
    int,
    Field(strict=True, gt=0, le=LOGICAL_CANVAS_SIZE),
]


class PanelRuntimeRole(StrEnum):
    """Future runtime role of an approved authoring panel."""

    AUTHORING_ONLY = "authoring_only"
    STATE = "state"
    EYE_PATCH = "eye_patch"
    MOUTH_PATCH = "mouth_patch"


class CompositeScope(StrEnum):
    """Composition level represented by a deterministic review sheet."""

    FAMILY = "family"
    PACKAGE_MASTER = "package_master"


class CompositeStatus(StrEnum):
    """Human-review and currency state of a deterministic composite."""

    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    STALE = "stale"


class HairOrientation(StrEnum):
    """Fixed screen-facing hair orientation for this package profile."""

    VIEWER_LEFT_SHAVE_VIEWER_RIGHT_LONG = "viewer_left_shave_viewer_right_long"


class PanelProgress(StrEnum):
    """Derived progress of one independently authored panel."""

    PENDING = "pending"
    GENERATING = "generating"
    CANDIDATE_READY = "candidate_ready"
    RETRY_READY = "retry_ready"
    APPROVED = "approved"
    EXHAUSTED = "exhausted"


class LogicalPoint(StrictDesignModel):
    """One point contained by the fixed 256 by 256 logical canvas."""

    model_config = ConfigDict(frozen=True)

    x: LogicalCoordinate
    y: LogicalCoordinate


class LogicalRect(StrictDesignModel):
    """One positive-area rectangle contained by the logical canvas."""

    model_config = ConfigDict(frozen=True)

    x: LogicalCoordinate
    y: LogicalCoordinate
    width: LogicalExtent
    height: LogicalExtent

    @property
    def right(self) -> int:
        """Return the exclusive horizontal bound."""
        return self.x + self.width

    @property
    def bottom(self) -> int:
        """Return the exclusive vertical bound."""
        return self.y + self.height

    @model_validator(mode="after")
    def validate_canvas_bounds(self) -> LogicalRect:
        """Reject rectangles extending past the fixed logical canvas."""
        if self.right > LOGICAL_CANVAS_SIZE or self.bottom > LOGICAL_CANVAS_SIZE:
            raise ValueError("Logical rectangles must stay inside the 256 by 256 logical canvas.")
        return self


class PortraitIdentityLock(StrictDesignModel):
    """Immutable palette, geometry, and orientation approved with neutral."""

    model_config = ConfigDict(frozen=True)

    logical_width: Literal[256] = 256
    logical_height: Literal[256] = 256
    file_width: Literal[512] = 512
    file_height: Literal[512] = 512
    palette_sha256: SHA256
    palette_max_colors: Annotated[int, Field(strict=True, ge=2, le=64)]
    pivot: LogicalPoint
    eye_rect: LogicalRect
    mouth_rect: LogicalRect
    shoulders: tuple[LogicalPoint, LogicalPoint]
    face_top_y: LogicalCoordinate
    chin_y: LogicalCoordinate
    face_height_target: Literal[160] = 160
    face_height_tolerance: Literal[2] = 2
    hair_orientation: HairOrientation = HairOrientation.VIEWER_LEFT_SHAVE_VIEWER_RIGHT_LONG

    @model_validator(mode="after")
    def validate_portrait_geometry(self) -> PortraitIdentityLock:
        """Keep the approved face and portrait anchors geometrically coherent."""
        actual_face_height = self.chin_y - self.face_top_y
        if abs(actual_face_height - self.face_height_target) > self.face_height_tolerance:
            raise ValueError(
                "Identity-lock face height must meet target 160 with tolerance 2 "
                "(accepted range 158 through 162 logical pixels)."
            )
        if not (
            self.face_top_y <= self.eye_rect.y
            and self.eye_rect.bottom <= self.mouth_rect.y
            and self.mouth_rect.bottom <= self.chin_y
        ):
            raise ValueError(
                "Identity-lock geometry must place the face top, eyes above the mouth, "
                "and mouth above the chin."
            )
        viewer_left, viewer_right = self.shoulders
        if viewer_left.x >= viewer_right.x:
            raise ValueError("Identity-lock shoulders must be ordered viewer-left to viewer-right.")
        if viewer_left.y <= self.chin_y or viewer_right.y <= self.chin_y:
            raise ValueError("Identity-lock shoulders must be below the chin.")
        return self


class PixelPackageRevision(StrictDesignModel):
    """Source and master lineage for one schema-1.1 pixel package revision."""

    schema_version: Literal["1.1"] = "1.1"
    profile: Literal["pixel-talking-portrait"] = "pixel-talking-portrait"
    package_id: Literal["juana-talking-bust-v2-pixel"]
    identity: NonEmptyString
    revision: NonEmptyString
    base_sources: Annotated[tuple[ArtifactEvidence, ...], Field(min_length=1)]
    base_source_rights: RightsMetadata
    technical_source_seal: SealEvidence
    master_reference: ArtifactEvidence | None = None

    @model_validator(mode="after")
    def validate_source_and_master_lineage(self) -> PixelPackageRevision:
        """Keep fixed sources distinct and the eventual package master canonical."""
        source_paths = [source.path for source in self.base_sources]
        if len(source_paths) != len(set(source_paths)):
            raise ValueError("Base source artifact paths must be unique.")
        if self.technical_source_seal.package_id != "juana-talking-bust-v1":
            raise ValueError("The technical source seal must belong to juana-talking-bust-v1.")
        if self.master_reference is not None and self.master_reference.path != PACKAGE_MASTER_PATH:
            raise ValueError(
                "The pixel package master reference must use the canonical master path."
            )
        return self


class PixelPanelCandidate(StrictDesignModel):
    """One normalized panel candidate and its complete generation evidence."""

    candidate_id: NonEmptyString
    panel_id: NonEmptyString
    attempt: PositiveAttempt
    status: CandidateStatus = CandidateStatus.PENDING
    provider: NonEmptyString
    model: NonEmptyString
    prompt_id: NonEmptyString
    prompt_version: NonEmptyString
    input_artifacts: Annotated[tuple[ArtifactEvidence, ...], Field(min_length=1)]
    raw_artifact: ArtifactEvidence
    normalized_panel: ArtifactEvidence
    validation_report: ArtifactEvidence
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_artifact_paths(self) -> PixelPanelCandidate:
        """Reject aliases between any input, raw, normalized, or report artifact."""
        paths = [
            *(artifact.path for artifact in self.input_artifacts),
            self.raw_artifact.path,
            self.normalized_panel.path,
            self.validation_report.path,
        ]
        if len(paths) != len(set(paths)):
            raise ValueError("Candidate artifact paths must be unique.")
        return self


class PixelPanelApproval(StrictDesignModel):
    """Immutable human decision covering every output of one panel candidate."""

    model_config = ConfigDict(frozen=True)

    approval_id: NonEmptyString
    candidate_id: NonEmptyString
    panel_id: NonEmptyString
    decision: ApprovalDecision
    approver: NonEmptyString
    decided_at: AwareDatetime
    reviewed_artifacts: Annotated[
        tuple[PackageRelativePath, ...],
        Field(min_length=1),
    ]
    notes: NonEmptyString
    identity_lock: PortraitIdentityLock | None = None

    @model_validator(mode="after")
    def validate_decision_scope(self) -> PixelPanelApproval:
        """Restrict identity evidence to the approval that establishes neutral."""
        if len(self.reviewed_artifacts) != len(set(self.reviewed_artifacts)):
            raise ValueError("Reviewed artifact paths must be unique.")
        if self.identity_lock is not None and not (
            self.panel_id == NEUTRAL_PANEL_ID and self.decision is ApprovalDecision.APPROVE
        ):
            raise ValueError("An identity lock can accompany only an approval of presence-neutral.")
        return self


class PixelPanelState(StrictDesignModel):
    """Bounded attempts and immutable review history for one panel."""

    panel_id: NonEmptyString
    progress: PanelProgress = PanelProgress.PENDING
    attempts: tuple[GenerationAttempt, ...] = ()
    candidates: tuple[PixelPanelCandidate, ...] = ()
    decisions: tuple[PixelPanelApproval, ...] = ()
    approved_candidate_id: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_history(self) -> PixelPanelState:
        """Validate bounded attempts, references, decisions, and derived progress."""
        if len(self.attempts) > 3:
            raise ValueError("Pixel panels allow no more than three attempts.")
        attempt_numbers = [attempt.attempt for attempt in self.attempts]
        if attempt_numbers != list(range(1, len(self.attempts) + 1)):
            raise ValueError("Panel attempt numbers must be contiguous and ordered.")
        if len({attempt.attempt_id for attempt in self.attempts}) != len(self.attempts):
            raise ValueError("Panel attempt identifiers must be unique.")
        if any(attempt.task_id != self.panel_id for attempt in self.attempts):
            raise ValueError("Every attempt must belong to its panel state.")

        in_progress = [
            attempt
            for attempt in self.attempts
            if attempt.status is GenerationAttemptStatus.IN_PROGRESS
        ]
        if len(in_progress) > 1 or (in_progress and in_progress[0] is not self.attempts[-1]):
            raise ValueError("Only the latest panel attempt can remain in progress.")

        candidates = {candidate.candidate_id: candidate for candidate in self.candidates}
        if len(candidates) != len(self.candidates):
            raise ValueError("Candidate identifiers must be unique within a panel.")
        if any(candidate.panel_id != self.panel_id for candidate in self.candidates):
            raise ValueError("Every candidate must belong to its panel state.")
        candidate_attempts = [candidate.attempt for candidate in self.candidates]
        if len(candidate_attempts) != len(set(candidate_attempts)):
            raise ValueError("Each panel attempt can produce at most one candidate.")

        attempts_by_number = {attempt.attempt: attempt for attempt in self.attempts}
        for candidate in self.candidates:
            attempt = attempts_by_number.get(candidate.attempt)
            if (
                attempt is None
                or attempt.status is not GenerationAttemptStatus.CANDIDATE_READY
                or attempt.candidate_id != candidate.candidate_id
            ):
                raise ValueError("Every candidate must have a matching recorded candidate attempt.")
        for attempt in self.attempts:
            if (
                attempt.status is GenerationAttemptStatus.CANDIDATE_READY
                and attempt.candidate_id not in candidates
            ):
                raise ValueError("Successful attempts must reference a recorded candidate.")

        if len({decision.approval_id for decision in self.decisions}) != len(self.decisions):
            raise ValueError("Panel approval identifiers must be unique.")
        decisions_by_candidate: dict[str, list[PixelPanelApproval]] = {}
        for decision in self.decisions:
            if decision.panel_id != self.panel_id or decision.candidate_id not in candidates:
                raise ValueError("Every decision must reference a candidate in its panel state.")
            candidate = candidates[decision.candidate_id]
            expected_scope = {
                candidate.raw_artifact.path,
                candidate.normalized_panel.path,
                candidate.validation_report.path,
            }
            if set(decision.reviewed_artifacts) != expected_scope:
                raise ValueError(
                    "A panel decision must review the raw, normalized, and validation artifacts."
                )
            decisions_by_candidate.setdefault(decision.candidate_id, []).append(decision)

        expected_status_by_decisions = {
            (): CandidateStatus.PENDING,
            (ApprovalDecision.APPROVE,): CandidateStatus.APPROVED,
            (ApprovalDecision.REJECT,): CandidateStatus.REJECTED,
            (
                ApprovalDecision.APPROVE,
                ApprovalDecision.SUPERSEDE,
            ): CandidateStatus.SUPERSEDED,
        }
        for candidate in self.candidates:
            candidate_decisions = decisions_by_candidate.get(candidate.candidate_id, [])
            decision_sequence = tuple(decision.decision for decision in candidate_decisions)
            expected_status = expected_status_by_decisions.get(decision_sequence)
            if expected_status is None:
                raise ValueError("Candidate decisions must form a valid review history.")
            if candidate.status is not expected_status:
                raise ValueError("Candidate status must match its human decision history.")
            if (
                self.panel_id == NEUTRAL_PANEL_ID
                and candidate.status is CandidateStatus.APPROVED
                and candidate_decisions[0].identity_lock is None
            ):
                raise ValueError("Approving presence-neutral requires an identity lock.")

        approved_candidates = [
            candidate
            for candidate in self.candidates
            if candidate.status is CandidateStatus.APPROVED
        ]
        if len(approved_candidates) > 1:
            raise ValueError("A panel can have only one active approved candidate.")
        if self.progress is PanelProgress.APPROVED:
            if len(approved_candidates) != 1 or self.approved_candidate_id != (
                approved_candidates[0].candidate_id
            ):
                raise ValueError("Approved panels require one matching approved candidate.")
        elif self.approved_candidate_id is not None or approved_candidates:
            raise ValueError("Only approved panels can reference an approved candidate.")

        pending_candidates = [
            candidate
            for candidate in self.candidates
            if candidate.status is CandidateStatus.PENDING
        ]
        if self.progress is PanelProgress.PENDING and (
            self.attempts or self.candidates or self.decisions
        ):
            raise ValueError("Pending panels cannot contain attempts or review history.")
        if self.progress is PanelProgress.GENERATING:
            if not in_progress:
                raise ValueError("Generating panels require an in-progress attempt.")
            if pending_candidates or approved_candidates:
                raise ValueError("Generating panels cannot have an unresolved candidate.")
        elif in_progress:
            raise ValueError("In-progress attempts require generating panel progress.")
        if self.progress is PanelProgress.CANDIDATE_READY:
            if len(pending_candidates) != 1:
                raise ValueError("Candidate-ready panels require one pending candidate.")
        elif pending_candidates:
            raise ValueError("Pending candidates require candidate-ready panel progress.")
        if self.progress is PanelProgress.RETRY_READY and (
            not self.attempts or len(self.attempts) >= 3
        ):
            raise ValueError("Retry-ready panels require one or two completed attempts.")
        if self.progress is PanelProgress.EXHAUSTED and len(self.attempts) != 3:
            raise ValueError("Exhausted panels require exactly three attempts.")
        if self.attempts and not in_progress:
            latest_attempt = self.attempts[-1]
            if latest_attempt.status is GenerationAttemptStatus.FAILED:
                expected_progress = (
                    PanelProgress.EXHAUSTED
                    if len(self.attempts) == 3
                    else PanelProgress.RETRY_READY
                )
            else:
                latest_candidate = next(
                    candidate
                    for candidate in self.candidates
                    if candidate.candidate_id == latest_attempt.candidate_id
                )
                expected_progress_by_status = {
                    CandidateStatus.PENDING: PanelProgress.CANDIDATE_READY,
                    CandidateStatus.APPROVED: PanelProgress.APPROVED,
                    CandidateStatus.REJECTED: (
                        PanelProgress.EXHAUSTED
                        if len(self.attempts) == 3
                        else PanelProgress.RETRY_READY
                    ),
                    CandidateStatus.SUPERSEDED: (
                        PanelProgress.EXHAUSTED
                        if len(self.attempts) == 3
                        else PanelProgress.RETRY_READY
                    ),
                }
                expected_progress = expected_progress_by_status[latest_candidate.status]
            if self.progress is not expected_progress:
                raise ValueError("Panel progress must reflect the latest completed attempt.")
        return self


class CompositeReviewSheet(StrictDesignModel):
    """One deterministic family or package-master review composition."""

    composite_id: NonEmptyString
    scope: CompositeScope
    family_id: NonEmptyString | None = None
    member_ids: Annotated[tuple[NonEmptyString, ...], Field(min_length=1)]
    member_hashes: Annotated[tuple[SHA256, ...], Field(min_length=1)]
    member_artifacts: Annotated[tuple[ArtifactEvidence, ...], Field(min_length=1)]
    artifact: ArtifactEvidence
    composition_version: NonEmptyString
    created_at: AwareDatetime
    status: CompositeStatus = CompositeStatus.PENDING_REVIEW

    @model_validator(mode="before")
    @classmethod
    def require_member_artifacts(cls, data: object) -> object:
        """Reject composites that omit their exact ordered input evidence."""
        if isinstance(data, dict) and not data.get("member_artifacts"):
            raise ValueError("Composite member artifact evidence is required.")
        return data

    @model_validator(mode="after")
    def validate_membership(self) -> CompositeReviewSheet:
        """Keep scope metadata and ordered member evidence internally consistent."""
        if self.scope is CompositeScope.FAMILY and self.family_id is None:
            raise ValueError("Family composites require family_id.")
        if self.scope is CompositeScope.PACKAGE_MASTER and self.family_id is not None:
            raise ValueError("Package-master composites cannot declare family_id.")
        if len(self.member_ids) != len(set(self.member_ids)):
            raise ValueError("Member identifiers must be unique within a composite.")
        if len(self.member_ids) != len(self.member_hashes):
            raise ValueError("Composite sheets require one ordered hash per member.")
        if (
            len(self.member_artifacts) != len(self.member_ids)
            or tuple(artifact.sha256 for artifact in self.member_artifacts) != self.member_hashes
            or len({artifact.path for artifact in self.member_artifacts})
            != len(self.member_artifacts)
        ):
            raise ValueError("Composite member artifact evidence must align with ordered members.")
        return self


class CompositeApproval(StrictDesignModel):
    """Immutable human approval covering one deterministic composite artifact."""

    model_config = ConfigDict(frozen=True)

    approval_id: NonEmptyString
    composite_id: NonEmptyString
    decision: Literal[ApprovalDecision.APPROVE] = ApprovalDecision.APPROVE
    approver: NonEmptyString
    decided_at: AwareDatetime
    reviewed_artifacts: Annotated[
        tuple[PackageRelativePath, ...],
        Field(min_length=1),
    ]
    notes: NonEmptyString

    @model_validator(mode="after")
    def validate_review_scope(self) -> CompositeApproval:
        """Reject repeated paths in immutable composite review evidence."""
        if len(self.reviewed_artifacts) != len(set(self.reviewed_artifacts)):
            raise ValueError("Reviewed composite artifact paths must be unique.")
        return self


class PixelPortraitAuthoringState(StrictDesignModel):
    """Complete schema-1.1 state for the independent panel-first workflow."""

    schema_version: Literal["1.1"] = "1.1"
    revision: PixelPackageRevision
    plan_id: NonEmptyString
    plan_version: NonEmptyString
    panels: dict[NonEmptyString, PixelPanelState]
    composites: tuple[CompositeReviewSheet, ...] = ()
    composite_approvals: tuple[CompositeApproval, ...] = ()
    active_composite_ids: tuple[NonEmptyString, ...] = ()
    provenance: tuple[ProvenanceRecord, ...] = ()
    gaps: tuple[GapRecord, ...] = ()
    identity_lock: PortraitIdentityLock | None = None

    @model_validator(mode="after")
    def validate_authoring_state(self) -> PixelPortraitAuthoringState:
        """Validate keys, locks, composite history, and current composite evidence."""
        if any(key != panel.panel_id for key, panel in self.panels.items()):
            raise ValueError("Panel dictionary keys must match embedded panel identifiers.")
        if len({record.provenance_id for record in self.provenance}) != len(self.provenance):
            raise ValueError("Provenance identifiers must be unique.")
        if len({gap.gap_id for gap in self.gaps}) != len(self.gaps):
            raise ValueError("Gap identifiers must be unique.")

        neutral = self.panels.get(NEUTRAL_PANEL_ID)
        if neutral is not None and neutral.progress is PanelProgress.APPROVED:
            if self.identity_lock is None:
                raise ValueError("Approved neutral panel requires identity_lock.")
            neutral_approval = next(
                decision
                for decision in neutral.decisions
                if decision.candidate_id == neutral.approved_candidate_id
                and decision.decision is ApprovalDecision.APPROVE
            )
            if neutral_approval.identity_lock != self.identity_lock:
                raise ValueError("Authoring identity_lock must match the active neutral approval.")
        elif self.identity_lock is not None:
            raise ValueError("identity_lock must be absent while neutral is not approved.")
        if self.identity_lock is None and any(
            panel_id != NEUTRAL_PANEL_ID
            and (
                panel.progress is not PanelProgress.PENDING
                or panel.attempts
                or panel.candidates
                or panel.decisions
                or panel.approved_candidate_id is not None
            )
            for panel_id, panel in self.panels.items()
        ):
            raise ValueError(
                "Dependent panels must remain pending and pristine until neutral "
                "establishes the identity lock."
            )

        composites = {composite.composite_id: composite for composite in self.composites}
        if len(composites) != len(self.composites):
            raise ValueError("Composite identifiers must be unique.")
        for composite in self.composites:
            if composite.scope is CompositeScope.FAMILY:
                if any(member_id not in self.panels for member_id in composite.member_ids):
                    raise ValueError(
                        "Every family-composite member must reference a recorded panel."
                    )
                if any(
                    member_artifact
                    not in tuple(
                        candidate.normalized_panel
                        for candidate in self.panels[member_id].candidates
                    )
                    for member_id, member_artifact in zip(
                        composite.member_ids,
                        composite.member_artifacts,
                        strict=True,
                    )
                ):
                    raise ValueError(
                        "Family-composite member artifacts must reference recorded panel evidence."
                    )
            elif any(
                member_id not in composites
                or composites[member_id].scope is not CompositeScope.FAMILY
                for member_id in composite.member_ids
            ):
                raise ValueError(
                    "Every package-master member must reference a recorded family composite."
                )
            elif composite.member_artifacts != tuple(
                composites[member_id].artifact for member_id in composite.member_ids
            ):
                raise ValueError(
                    "Package-master member artifacts must match recorded family evidence."
                )
        if len({approval.approval_id for approval in self.composite_approvals}) != len(
            self.composite_approvals
        ):
            raise ValueError("Composite approval identifiers must be unique.")

        approvals_by_composite: dict[str, list[CompositeApproval]] = {}
        for approval in self.composite_approvals:
            approved_composite = composites.get(approval.composite_id)
            if approved_composite is None:
                raise ValueError("Every composite approval must reference a recorded composite.")
            if tuple(approval.reviewed_artifacts) != (approved_composite.artifact.path,):
                raise ValueError("Composite approval must review exactly its composite artifact.")
            approvals_by_composite.setdefault(approval.composite_id, []).append(approval)

        for composite in self.composites:
            approvals = approvals_by_composite.get(composite.composite_id, [])
            if len(approvals) > 1:
                raise ValueError("A composite can have only one approval record.")
            if composite.status is CompositeStatus.PENDING_REVIEW and approvals:
                raise ValueError("Pending-review composites cannot have approval evidence.")
            if composite.status is CompositeStatus.APPROVED and len(approvals) != 1:
                raise ValueError("Approved composites require one approval record.")

        if len(self.active_composite_ids) != len(set(self.active_composite_ids)):
            raise ValueError("Active composite identifiers must be unique.")
        active_composites: list[CompositeReviewSheet] = []
        for composite_id in self.active_composite_ids:
            active_composite = composites.get(composite_id)
            if active_composite is None:
                raise ValueError("Active composite identifiers must reference recorded composites.")
            if active_composite.status is not CompositeStatus.APPROVED:
                raise ValueError("Active composites must be approved and current.")
            active_composites.append(active_composite)

        active_families = [
            composite for composite in active_composites if composite.scope is CompositeScope.FAMILY
        ]
        family_ids = [composite.family_id for composite in active_families]
        if len(family_ids) != len(set(family_ids)):
            raise ValueError("Only one active composite is allowed per family.")
        active_masters = [
            composite
            for composite in active_composites
            if composite.scope is CompositeScope.PACKAGE_MASTER
        ]
        if len(active_masters) > 1:
            raise ValueError("Only one package-master composite can be active.")

        for composite in active_families:
            member_hashes: list[str] = []
            member_artifacts: list[ArtifactEvidence] = []
            for member_id in composite.member_ids:
                panel = self.panels.get(member_id)
                if panel is None or panel.progress is not PanelProgress.APPROVED:
                    raise ValueError(
                        "Active family composites require active approved member panels."
                    )
                candidate = next(
                    candidate
                    for candidate in panel.candidates
                    if candidate.candidate_id == panel.approved_candidate_id
                )
                member_hashes.append(candidate.normalized_panel.sha256)
                member_artifacts.append(candidate.normalized_panel)
            if tuple(member_hashes) != composite.member_hashes:
                raise ValueError(
                    "Active family composites must match active approved panel hashes."
                )
            if tuple(member_artifacts) != composite.member_artifacts:
                raise ValueError(
                    "Active family composites must match active approved panel evidence."
                )

        if active_masters:
            master = active_masters[0]
            expected_member_ids = tuple(composite.composite_id for composite in active_families)
            expected_member_hashes = tuple(
                composite.artifact.sha256 for composite in active_families
            )
            if master.member_ids != expected_member_ids:
                raise ValueError(
                    "An active package master must include every active family composite."
                )
            if master.member_hashes != expected_member_hashes:
                raise ValueError(
                    "An active package master must match current family composite hashes."
                )
            expected_member_artifacts = tuple(composite.artifact for composite in active_families)
            if master.member_artifacts != expected_member_artifacts:
                raise ValueError(
                    "An active package master must match current family composite evidence."
                )
            master_reference = self.revision.master_reference
            if master_reference is None:
                raise ValueError("An active package master requires a revision master reference.")
            if master_reference.path == master.artifact.path:
                raise ValueError(
                    "Revision and authoring package-master paths must remain distinct."
                )
            if (
                master_reference.sha256,
                master_reference.byte_length,
                master_reference.width,
                master_reference.height,
            ) != (
                master.artifact.sha256,
                master.artifact.byte_length,
                master.artifact.width,
                master.artifact.height,
            ):
                raise ValueError(
                    "The revision and active package master must have identical content evidence."
                )
        elif self.revision.master_reference is not None:
            raise ValueError(
                "A revision master reference requires an active package-master composite."
            )
        return self
