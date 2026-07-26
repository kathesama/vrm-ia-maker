"""Tests for the panel-first pixel portrait application service."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

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
    PixelPackageRevision,
    PixelPanelApproval,
    PixelPanelCandidate,
    PixelPanelState,
    PixelPortraitAuthoringState,
    PortraitIdentityLock,
)
from vrm_ia_maker.design.pixel_portrait.plan import (
    PIXEL_PORTRAIT_PLAN,
    PixelPanelDefinition,
    PixelPortraitPlanDefinition,
)
from vrm_ia_maker.design.pixel_portrait.ports import (
    BASE_SOURCE_FILENAMES,
    PixelWorkspaceInitialization,
)
from vrm_ia_maker.design.pixel_portrait.service import (
    PixelPortraitService,
    PixelPortraitWorkflowError,
)
from vrm_ia_maker.design.ports import (
    AuthoringWorkspaceError,
    GeneratedImage,
    GenerationRequest,
    ImageGenerationError,
)

NOW = datetime(2026, 7, 21, 12, 0, tzinfo=UTC)
_BASE_PREFIX = "sources/base-set/"
_TECHNICAL_PREFIX = "sources/talking-bust-v1/"


def artifact(path: str) -> ArtifactEvidence:
    digest = hashlib.sha256(path.encode("utf-8")).hexdigest()
    return ArtifactEvidence(
        path=path,
        sha256=digest,
        byte_length=128,
        width=512,
        height=512,
    )


def complete_rights() -> RightsMetadata:
    return RightsMetadata(
        author="Katherine E. Aguirre",
        rights_holder="Katherine E. Aguirre",
        license="Author-approved project use",
        commercial_use=True,
        modification_allowed=True,
        redistribution_allowed=True,
        attribution="Katherine E. Aguirre / Juana IA",
    )


def identity_lock() -> PortraitIdentityLock:
    return PortraitIdentityLock(
        palette_sha256="a" * 64,
        palette_max_colors=64,
        pivot=LogicalPoint(x=128, y=196),
        eye_rect=LogicalRect(x=76, y=82, width=104, height=24),
        mouth_rect=LogicalRect(x=100, y=136, width=56, height=24),
        shoulders=(LogicalPoint(x=56, y=220), LogicalPoint(x=200, y=220)),
        face_top_y=40,
        chin_y=200,
        hair_orientation=HairOrientation.VIEWER_LEFT_SHAVE_VIEWER_RIGHT_LONG,
    )


def candidate_for(
    panel_id: str,
    *,
    attempt: int = 1,
    status: CandidateStatus = CandidateStatus.PENDING,
    inputs: tuple[ArtifactEvidence, ...] | None = None,
) -> PixelPanelCandidate:
    prefix = f"candidates/{panel_id}/attempt-{attempt}"
    return PixelPanelCandidate(
        candidate_id=f"{panel_id}-attempt-{attempt}",
        panel_id=panel_id,
        attempt=attempt,
        status=status,
        provider="fake-provider",
        model="fake-model",
        prompt_id=f"pixel-panel.{panel_id}",
        prompt_version="pixel-panel-v1",
        input_artifacts=inputs or (artifact(f"inputs/{panel_id}.png"),),
        raw_artifact=artifact(f"{prefix}/raw.png"),
        normalized_panel=artifact(f"{prefix}/panel.png"),
        validation_report=artifact(f"{prefix}/validation.json"),
        created_at=NOW,
    )


def approved_panel(panel_id: str) -> PixelPanelState:
    candidate = candidate_for(panel_id, status=CandidateStatus.APPROVED)
    decision = PixelPanelApproval(
        approval_id=f"approve-{candidate.candidate_id}",
        candidate_id=candidate.candidate_id,
        panel_id=panel_id,
        decision=ApprovalDecision.APPROVE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=(
            candidate.raw_artifact.path,
            candidate.normalized_panel.path,
            candidate.validation_report.path,
        ),
        notes="Approved after reviewing every candidate artifact.",
        identity_lock=identity_lock() if panel_id == "presence-neutral" else None,
    )
    attempt = GenerationAttempt(
        attempt_id=f"{panel_id}-attempt-1",
        task_id=panel_id,
        attempt=1,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        started_at=NOW,
        completed_at=NOW,
        candidate_id=candidate.candidate_id,
    )
    return PixelPanelState(
        panel_id=panel_id,
        progress=PanelProgress.APPROVED,
        attempts=(attempt,),
        candidates=(candidate,),
        decisions=(decision,),
        approved_candidate_id=candidate.candidate_id,
    )


def reapproved_panel(panel_id: str) -> PixelPanelState:
    """Build exact superseded history followed by a second active approval."""
    first = approved_panel(panel_id)
    first_candidate = first.candidates[0].model_copy(update={"status": CandidateStatus.SUPERSEDED})
    first_approval = first.decisions[0]
    supersede = first_approval.model_copy(
        update={
            "approval_id": f"supersede-{first_candidate.candidate_id}",
            "decision": ApprovalDecision.SUPERSEDE,
        }
    )
    active_candidate = candidate_for(
        panel_id,
        attempt=2,
        status=CandidateStatus.APPROVED,
    )
    active_attempt = GenerationAttempt(
        attempt_id=f"{panel_id}-attempt-2",
        task_id=panel_id,
        attempt=2,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        started_at=NOW,
        completed_at=NOW,
        candidate_id=active_candidate.candidate_id,
    )
    active_approval = PixelPanelApproval(
        approval_id=f"approve-{active_candidate.candidate_id}",
        candidate_id=active_candidate.candidate_id,
        panel_id=panel_id,
        decision=ApprovalDecision.APPROVE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=panel_review_scope(active_candidate),
        notes="Approved replacement after reviewing every candidate artifact.",
    )
    return PixelPanelState(
        panel_id=panel_id,
        progress=PanelProgress.APPROVED,
        attempts=(*first.attempts, active_attempt),
        candidates=(first_candidate, active_candidate),
        decisions=(first_approval, supersede, active_approval),
        approved_candidate_id=active_candidate.candidate_id,
    )


def candidate_ready_panel(
    panel_id: str,
    *,
    attempt: int = 1,
    history: PixelPanelState | None = None,
) -> PixelPanelState:
    """Build one valid pending candidate, optionally after preserved history."""
    prior_attempts = (
        history.attempts
        if history is not None
        else tuple(
            GenerationAttempt(
                attempt_id=f"{panel_id}-attempt-{number}",
                task_id=panel_id,
                attempt=number,
                status=GenerationAttemptStatus.FAILED,
                started_at=NOW,
                completed_at=NOW,
                error_code="provider_failure",
                error_message="Sanitized provider failure.",
            )
            for number in range(1, attempt)
        )
    )
    if attempt != len(prior_attempts) + 1:
        raise AssertionError("Candidate attempt must follow preserved history.")
    candidate = candidate_for(panel_id, attempt=attempt)
    completed = GenerationAttempt(
        attempt_id=f"{panel_id}-attempt-{attempt}",
        task_id=panel_id,
        attempt=attempt,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        started_at=NOW,
        completed_at=NOW,
        candidate_id=candidate.candidate_id,
    )
    return PixelPanelState(
        panel_id=panel_id,
        progress=PanelProgress.CANDIDATE_READY,
        attempts=(*prior_attempts, completed),
        candidates=(*(history.candidates if history is not None else ()), candidate),
        decisions=history.decisions if history is not None else (),
    )


def panel_review_scope(candidate: PixelPanelCandidate) -> tuple[str, ...]:
    return (
        candidate.raw_artifact.path,
        candidate.normalized_panel.path,
        candidate.validation_report.path,
    )


def initial_state() -> PixelPortraitAuthoringState:
    base_sources = tuple(
        artifact(f"{_BASE_PREFIX}{filename}") for filename in BASE_SOURCE_FILENAMES
    )
    base_provenance = tuple(
        ProvenanceRecord(
            provenance_id=f"base-source-{position}",
            source_class=SourceClass.CREATIVE_CANON,
            artifact=source,
            authoritative_source="Locked base-set input.",
            rights=RightsMetadata(),
        )
        for position, source in enumerate(base_sources)
    )
    technical_paths = tuple(
        dict.fromkeys(
            panel.technical_source_path
            for panel in PIXEL_PORTRAIT_PLAN.panels
            if panel.technical_source_path is not None
        )
    )
    technical_provenance = tuple(
        ProvenanceRecord(
            provenance_id=f"v1-technical-{position}",
            source_class=SourceClass.TECHNICAL_REFERENCE,
            artifact=artifact(f"{_TECHNICAL_PREFIX}{path}"),
            authoritative_source="Locked sealed V1 technical evidence.",
            rights=complete_rights(),
        )
        for position, path in enumerate(technical_paths)
    )
    technical_hashes = {
        path: artifact(f"{_TECHNICAL_PREFIX}{path}").sha256 for path in technical_paths
    }
    unrelated = ProvenanceRecord(
        provenance_id="unrelated-technical",
        source_class=SourceClass.TECHNICAL_REFERENCE,
        artifact=artifact(f"{_TECHNICAL_PREFIX}references/unrelated.png"),
        authoritative_source="Unrelated locked evidence.",
        rights=complete_rights(),
    )
    return PixelPortraitAuthoringState(
        revision=PixelPackageRevision(
            package_id="juana-talking-bust-v2-pixel",
            identity="Juana",
            revision="1.0.0",
            base_sources=base_sources,
            base_source_rights=RightsMetadata(),
            technical_source_seal=SealEvidence(
                package_id="juana-talking-bust-v1",
                revision="1.0.0",
                sealed_at=NOW,
                file_hashes={"seal.json": "b" * 64, **technical_hashes},
                approval_ids=("approval-v1",),
                provenance_ids=("provenance-v1",),
            ),
        ),
        plan_id=PIXEL_PORTRAIT_PLAN.plan_id,
        plan_version=PIXEL_PORTRAIT_PLAN.version,
        panels={
            panel.panel_id: PixelPanelState(panel_id=panel.panel_id)
            for panel in PIXEL_PORTRAIT_PLAN.panels
        },
        provenance=(*base_provenance, *technical_provenance, unrelated),
        gaps=(
            GapRecord(
                gap_id="source-rights-incomplete",
                area="source-rights",
                description="Base-set rights are incomplete.",
                blocks_visual_seal=True,
            ),
            GapRecord(
                gap_id="measurements-missing",
                area="measurements",
                description="No measured geometry is asserted.",
                blocks_visual_seal=False,
            ),
        ),
    )


def with_approved_prefix(
    state: PixelPortraitAuthoringState,
    count: int,
) -> PixelPortraitAuthoringState:
    panels = dict(state.panels)
    for panel in PIXEL_PORTRAIT_PLAN.panels[:count]:
        panels[panel.panel_id] = approved_panel(panel.panel_id)
    payload = state.model_dump(mode="python")
    payload["panels"] = panels
    payload["identity_lock"] = identity_lock() if count else None
    return PixelPortraitAuthoringState.model_validate(payload)


def with_panel_state(
    state: PixelPortraitAuthoringState,
    panel: PixelPanelState,
) -> PixelPortraitAuthoringState:
    panels = dict(state.panels)
    panels[panel.panel_id] = panel
    payload = state.model_dump(mode="python")
    payload["panels"] = panels
    return PixelPortraitAuthoringState.model_validate(payload)


def active_panel_candidate(
    state: PixelPortraitAuthoringState,
    panel_id: str,
) -> PixelPanelCandidate:
    panel = state.panels[panel_id]
    return next(
        candidate
        for candidate in panel.candidates
        if candidate.candidate_id == panel.approved_candidate_id
    )


def family_composite(
    state: PixelPortraitAuthoringState,
    family_id: str,
    *,
    status: CompositeStatus = CompositeStatus.PENDING_REVIEW,
) -> CompositeReviewSheet:
    family = PIXEL_PORTRAIT_PLAN.family(family_id)
    version = 1 + sum(
        composite.scope is CompositeScope.FAMILY and composite.family_id == family_id
        for composite in state.composites
    )
    composite_id = f"family-{family_id}-v{version}"
    member_artifacts = tuple(
        active_panel_candidate(state, panel_id).normalized_panel for panel_id in family.panel_ids
    )
    return CompositeReviewSheet(
        composite_id=composite_id,
        scope=CompositeScope.FAMILY,
        family_id=family_id,
        member_ids=family.panel_ids,
        member_hashes=tuple(item.sha256 for item in member_artifacts),
        member_artifacts=member_artifacts,
        artifact=artifact(f"composites/family/{composite_id}/sheet.png"),
        composition_version="pixel-grid-v1",
        created_at=NOW,
        status=status,
    )


def composite_approval(composite: CompositeReviewSheet) -> CompositeApproval:
    return CompositeApproval(
        approval_id=f"approve-{composite.composite_id}",
        composite_id=composite.composite_id,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=(composite.artifact.path,),
        notes="Approved after reviewing the exact composite artifact.",
    )


def with_family_composites(
    state: PixelPortraitAuthoringState,
    statuses: dict[str, CompositeStatus],
) -> PixelPortraitAuthoringState:
    composites = tuple(
        family_composite(state, family.family_id, status=statuses[family.family_id])
        for family in PIXEL_PORTRAIT_PLAN.families
        if family.family_id in statuses
    )
    approvals = tuple(
        composite_approval(composite)
        for composite in composites
        if composite.status is CompositeStatus.APPROVED
    )
    active_ids = tuple(
        composite.composite_id
        for composite in composites
        if composite.status is CompositeStatus.APPROVED
    )
    payload = state.model_dump(mode="python")
    payload.update(
        {
            "composites": composites,
            "composite_approvals": approvals,
            "active_composite_ids": active_ids,
        }
    )
    return PixelPortraitAuthoringState.model_validate(payload)


def package_master_composite(
    state: PixelPortraitAuthoringState,
    *,
    status: CompositeStatus = CompositeStatus.PENDING_REVIEW,
) -> CompositeReviewSheet:
    composites = {item.composite_id: item for item in state.composites}
    family_sheets = tuple(
        composites[composite_id]
        for composite_id in state.active_composite_ids
        if composites[composite_id].scope is CompositeScope.FAMILY
    )
    version = 1 + sum(
        composite.scope is CompositeScope.PACKAGE_MASTER for composite in state.composites
    )
    composite_id = f"package-master-v{version}"
    member_artifacts = tuple(item.artifact for item in family_sheets)
    return CompositeReviewSheet(
        composite_id=composite_id,
        scope=CompositeScope.PACKAGE_MASTER,
        member_ids=tuple(item.composite_id for item in family_sheets),
        member_hashes=tuple(item.sha256 for item in member_artifacts),
        member_artifacts=member_artifacts,
        artifact=artifact(f"composites/package-master/{composite_id}/sheet.png"),
        composition_version="pixel-grid-v1",
        created_at=NOW,
        status=status,
    )


def with_package_master(
    state: PixelPortraitAuthoringState,
    *,
    status: CompositeStatus,
) -> PixelPortraitAuthoringState:
    master = package_master_composite(state, status=status)
    approvals = state.composite_approvals
    active_ids = state.active_composite_ids
    revision = state.revision
    if status is CompositeStatus.APPROVED:
        approvals = (*approvals, composite_approval(master))
        active_ids = (*active_ids, master.composite_id)
        revision = revision.model_copy(
            update={
                "master_reference": master.artifact.model_copy(update={"path": PACKAGE_MASTER_PATH})
            }
        )
    payload = state.model_dump(mode="python")
    payload.update(
        {
            "revision": revision,
            "composites": (*state.composites, master),
            "composite_approvals": approvals,
            "active_composite_ids": active_ids,
        }
    )
    return PixelPortraitAuthoringState.model_validate(payload)


def sealable_panel_state() -> PixelPortraitAuthoringState:
    """Build complete panel approvals with legal and visual seal gates cleared."""
    state = initial_state()
    base_paths = {source.path for source in state.revision.base_sources}
    rights = complete_rights()
    payload = state.model_dump(mode="python")
    payload.update(
        {
            "revision": state.revision.model_copy(update={"base_source_rights": rights}),
            "provenance": tuple(
                record.model_copy(update={"rights": rights})
                if record.artifact.path in base_paths
                else record
                for record in state.provenance
            ),
            "gaps": tuple(gap for gap in state.gaps if not gap.blocks_visual_seal),
        }
    )
    return with_approved_prefix(
        PixelPortraitAuthoringState.model_validate(payload),
        len(PIXEL_PORTRAIT_PLAN.panels),
    )


def sealable_state() -> PixelPortraitAuthoringState:
    """Build one complete service-level seal fixture."""
    state = sealable_panel_state()
    state = with_family_composites(
        state,
        {family.family_id: CompositeStatus.APPROVED for family in PIXEL_PORTRAIT_PLAN.families},
    )
    return with_package_master(state, status=CompositeStatus.APPROVED)


def panel_without_active_approval(
    panel_id: str,
    active_state: str,
) -> PixelPanelState:
    """Build one valid non-approved active panel state for seal-gate tests."""
    if active_state == "pending":
        return PixelPanelState(panel_id=panel_id)
    if active_state == "in_progress":
        attempt = GenerationAttempt(
            attempt_id=f"{panel_id}-attempt-1",
            task_id=panel_id,
            attempt=1,
            status=GenerationAttemptStatus.IN_PROGRESS,
            started_at=NOW,
        )
        return PixelPanelState(
            panel_id=panel_id,
            progress=PanelProgress.GENERATING,
            attempts=(attempt,),
        )

    candidate_status = {
        "rejected": CandidateStatus.REJECTED,
        "superseded": CandidateStatus.SUPERSEDED,
    }[active_state]
    candidate = candidate_for(panel_id, status=candidate_status)
    attempt = GenerationAttempt(
        attempt_id=f"{panel_id}-attempt-1",
        task_id=panel_id,
        attempt=1,
        status=GenerationAttemptStatus.CANDIDATE_READY,
        started_at=NOW,
        completed_at=NOW,
        candidate_id=candidate.candidate_id,
    )
    approve = PixelPanelApproval(
        approval_id=f"approve-{candidate.candidate_id}",
        candidate_id=candidate.candidate_id,
        panel_id=panel_id,
        decision=ApprovalDecision.APPROVE,
        approver="Kathy",
        decided_at=NOW,
        reviewed_artifacts=panel_review_scope(candidate),
        notes="Approved after reviewing every candidate artifact.",
    )
    decisions: tuple[PixelPanelApproval, ...] = (approve,)
    if active_state == "rejected":
        decisions = (
            approve.model_copy(
                update={
                    "approval_id": f"reject-{candidate.candidate_id}",
                    "decision": ApprovalDecision.REJECT,
                }
            ),
        )
    else:
        decisions = (
            approve,
            approve.model_copy(
                update={
                    "approval_id": f"supersede-{candidate.candidate_id}",
                    "decision": ApprovalDecision.SUPERSEDE,
                }
            ),
        )
    return PixelPanelState(
        panel_id=panel_id,
        progress=PanelProgress.RETRY_READY,
        attempts=(attempt,),
        candidates=(candidate,),
        decisions=decisions,
    )


class TickingClock:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self) -> datetime:
        instant = NOW + timedelta(seconds=self.calls)
        self.calls += 1
        return instant


class FakeWorkspace:
    def __init__(self, state: PixelPortraitAuthoringState | None = None) -> None:
        self.state = state or initial_state()
        self.initializations: list[PixelWorkspaceInitialization] = []
        self.saved: list[PixelPortraitAuthoringState] = []
        self.resolved: list[str] = []
        self.staged: list[tuple[str, int, tuple[ArtifactEvidence, ...]]] = []
        self.validated: list[PixelPortraitAuthoringState] = []
        self.composed: list[CompositeReviewSheet] = []
        self.compose_states: list[PixelPortraitAuthoringState] = []
        self.sealed: list[tuple[PixelPortraitAuthoringState, Path, datetime]] = []
        self.stage_error: BaseException | None = None
        self.compose_error: BaseException | None = None
        self.seal_error: BaseException | None = None
        self.resolve_error: AuthoringWorkspaceError | None = None
        self.validate_error: BaseException | None = None
        self.save_errors: dict[int, BaseException] = {}
        self.save_calls = 0
        self.events: list[str] = []
        self.in_lock = False
        self.lock_entries = 0
        self.load_lock_states: list[bool] = []

    def initialize(
        self,
        command: PixelWorkspaceInitialization,
    ) -> PixelPortraitAuthoringState:
        self.initializations.append(command)
        return self.state

    def load_state(self) -> PixelPortraitAuthoringState:
        self.load_lock_states.append(self.in_lock)
        return self.state

    def save_state(self, state: PixelPortraitAuthoringState) -> None:
        assert self.in_lock
        self.save_calls += 1
        self.events.append("save")
        error = self.save_errors.pop(self.save_calls, None)
        if error is not None:
            raise error
        self.state = state
        self.saved.append(state)

    def resolve_artifact(self, relative_path: str) -> Path:
        assert self.in_lock
        self.events.append("resolve")
        if self.resolve_error is not None:
            raise self.resolve_error
        self.resolved.append(relative_path)
        return Path("locked-workspace", *relative_path.split("/"))

    def stage_candidate(
        self,
        *,
        panel: PixelPanelDefinition,
        attempt: int,
        generated: GeneratedImage,
        input_artifacts: tuple[ArtifactEvidence, ...],
        created_at: datetime,
    ) -> PixelPanelCandidate:
        assert self.in_lock
        self.events.append("stage")
        if self.stage_error is not None:
            raise self.stage_error
        panel_id = panel.panel_id
        self.staged.append((panel_id, attempt, input_artifacts))
        candidate = candidate_for(panel_id, attempt=attempt, inputs=input_artifacts)
        return candidate.model_copy(
            update={
                "provider": generated.provider,
                "model": generated.model,
                "created_at": created_at,
            }
        )

    def compose(
        self,
        *,
        state: PixelPortraitAuthoringState,
        scope: CompositeScope,
        family_id: str | None,
        created_at: datetime,
    ) -> CompositeReviewSheet:
        assert self.in_lock
        self.events.append("compose")
        self.compose_states.append(state)
        if self.compose_error is not None:
            raise self.compose_error
        if scope is CompositeScope.FAMILY:
            if family_id is None:
                raise AssertionError("Family composition requires family_id.")
            sheet = family_composite(state, family_id)
        else:
            if family_id is not None:
                raise AssertionError("Package-master composition rejects family_id.")
            sheet = package_master_composite(state)
        sheet = sheet.model_copy(update={"created_at": created_at})
        self.composed.append(sheet)
        return sheet

    def seal(
        self,
        state: PixelPortraitAuthoringState,
        destination: Path,
        sealed_at: datetime,
    ) -> SealEvidence:
        assert self.in_lock
        self.events.append("seal")
        self.sealed.append((state, destination, sealed_at))
        if self.seal_error is not None:
            raise self.seal_error
        return SealEvidence(
            package_id=state.revision.package_id,
            revision=state.revision.revision,
            sealed_at=sealed_at,
            file_hashes={"package.json": "d" * 64},
            approval_ids=("seal-fixture-approval",),
            provenance_ids=("seal-fixture-provenance",),
        )

    def validate(self, state: PixelPortraitAuthoringState) -> None:
        assert self.in_lock
        self.events.append("validate")
        self.validated.append(state)
        if self.validate_error is not None:
            raise self.validate_error

    @contextmanager
    def exclusive(self) -> Iterator[None]:
        assert not self.in_lock
        self.in_lock = True
        self.lock_entries += 1
        try:
            yield
        finally:
            self.in_lock = False


class FakeGenerator:
    def __init__(
        self,
        workspace: FakeWorkspace,
        responses: list[GeneratedImage | BaseException] | None = None,
    ) -> None:
        self.workspace = workspace
        self.responses = responses or [
            GeneratedImage(data=b"fake-png", provider="fake-provider", model="fake-model")
        ]
        self.requests: list[GenerationRequest] = []
        self.progress_seen: list[PanelProgress] = []

    def generate(self, request: GenerationRequest) -> GeneratedImage:
        assert self.workspace.in_lock
        self.workspace.events.append("generate")
        self.requests.append(request)
        self.progress_seen.append(self.workspace.state.panels[request.task_id].progress)
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def service_with(
    workspace: FakeWorkspace,
    generator: FakeGenerator | None = None,
) -> PixelPortraitService:
    return PixelPortraitService(
        workspace=workspace,
        generator=generator,
        clock=TickingClock(),
    )


def test_initialize_is_provider_free() -> None:
    workspace = FakeWorkspace()
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    command = PixelWorkspaceInitialization(
        base_sources=tuple(Path("inputs", name) for name in BASE_SOURCE_FILENAMES),
        technical_package=Path("technical-package"),
        package_id="juana-talking-bust-v2-pixel",
        identity="Juana",
        revision="1.0.0",
        authoritative_source="User-approved base set.",
    )

    result = service.initialize(command)

    assert result == workspace.state
    assert workspace.initializations == [command]
    assert generator.requests == []


def test_run_stages_first_neutral_with_exact_locked_inputs_and_fixed_prompt() -> None:
    workspace = FakeWorkspace()
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    result = service.run()

    assert result.panel_id == "presence-neutral"
    assert result.attempt == 1
    assert result.candidate.panel_id == "presence-neutral"
    assert len(generator.requests) == 1
    assert generator.progress_seen == [PanelProgress.GENERATING]
    assert workspace.events[:2] == ["validate", "save"]
    assert workspace.events.index("generate") > workspace.events.index("resolve")
    assert workspace.saved[0].panels["presence-neutral"].attempts[0].status is (
        GenerationAttemptStatus.IN_PROGRESS
    )
    expected_artifacts = (
        *workspace.state.revision.base_sources,
        next(
            record.artifact
            for record in workspace.state.provenance
            if record.artifact.path == f"{_TECHNICAL_PREFIX}references/face/neutral-front.png"
        ),
    )
    request = generator.requests[0]
    assert request.task_id == "presence-neutral"
    assert request.prompt_id == "pixel-panel.presence-neutral"
    assert request.prompt_version == "pixel-panel-v1"
    assert request.prompt == (
        f"{PIXEL_PORTRAIT_PLAN.base_prompt} "
        f"{PIXEL_PORTRAIT_PLAN.panel('presence-neutral').prompt_instruction}"
    )
    assert (request.width, request.height) == (1024, 1024)
    assert request.input_paths == tuple(
        Path("locked-workspace", *item.path.split("/")) for item in expected_artifacts
    )
    assert workspace.staged == [("presence-neutral", 1, expected_artifacts)]
    restored = workspace.state.panels["presence-neutral"]
    assert restored.progress is PanelProgress.CANDIDATE_READY
    assert restored.attempts[0].status is GenerationAttemptStatus.CANDIDATE_READY
    assert restored.candidates == (result.candidate,)
    assert workspace.lock_entries == 1


def test_run_integrity_preflight_fails_before_attempt_or_provider() -> None:
    workspace = FakeWorkspace()
    initial_panel = workspace.state.panels["presence-neutral"]
    workspace.validate_error = AuthoringWorkspaceError(
        "integrity_failure",
        "Locked input bytes changed.",
    )
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "integrity_failure"
    assert workspace.events == ["validate"]
    assert workspace.state.panels["presence-neutral"] == initial_panel
    assert workspace.state.panels["presence-neutral"].attempts == ()
    assert workspace.saved == []
    assert generator.requests == []


def test_run_unexpected_preflight_failure_is_generic_and_provider_free() -> None:
    secret = "local-integrity-secret"
    workspace = FakeWorkspace()
    workspace.validate_error = RuntimeError(secret)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "unexpected_failure"
    assert secret not in str(caught.value)
    assert workspace.events == ["validate"]
    assert workspace.state.panels["presence-neutral"].attempts == ()
    assert generator.requests == []


def test_pending_candidate_blocks_another_provider_call() -> None:
    workspace = FakeWorkspace()
    generator = FakeGenerator(
        workspace,
        responses=[
            GeneratedImage(data=b"first", provider="fake", model="model"),
            GeneratedImage(data=b"second", provider="fake", model="model"),
        ],
    )
    service = service_with(workspace, generator)
    service.run()

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "pending_review"
    assert len(generator.requests) == 1


def test_later_presence_uses_only_character_sheet_matching_state_and_neutral() -> None:
    state = with_approved_prefix(initial_state(), 1)
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    result = service.run()

    neutral = state.panels["presence-neutral"].candidates[0].normalized_panel
    expected = (
        next(
            item
            for item in state.revision.base_sources
            if item.path.endswith("/juana-avatar-character-sheet.png")
        ),
        next(
            item
            for item in state.revision.base_sources
            if item.path.endswith("/juana-avatar-thinking.png")
        ),
        neutral,
    )
    assert result.panel_id == "presence-thinking"
    assert generator.requests[0].input_paths == tuple(
        Path("locked-workspace", *item.path.split("/")) for item in expected
    )
    assert workspace.staged[0][2] == expected


def test_technical_panel_uses_only_character_sheet_neutral_and_exact_v1_evidence() -> None:
    state = with_approved_prefix(initial_state(), 7)
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    result = service.run()

    technical_path = f"{_TECHNICAL_PREFIX}references/face/left-profile.png"
    expected = (
        next(
            item
            for item in state.revision.base_sources
            if item.path.endswith("/juana-avatar-character-sheet.png")
        ),
        state.panels["presence-neutral"].candidates[0].normalized_panel,
        next(
            record.artifact for record in state.provenance if record.artifact.path == technical_path
        ),
    )
    assert result.panel_id == "face-left-profile"
    assert workspace.staged[0][2] == expected
    assert workspace.resolved == [item.path for item in expected]


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ImageGenerationError("provider_failure", "Provider request failed."), "provider_failure"),
        (
            ImageGenerationError("moderation_blocked", "The request was moderated."),
            "moderation_blocked",
        ),
    ],
)
def test_sanitized_generation_failure_consumes_one_attempt(
    error: ImageGenerationError,
    code: str,
) -> None:
    workspace = FakeWorkspace()
    generator = FakeGenerator(workspace, responses=[error])
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    panel = workspace.state.panels["presence-neutral"]
    assert caught.value.code == code
    assert len(generator.requests) == 1
    assert panel.progress is PanelProgress.RETRY_READY
    assert len(panel.attempts) == 1
    assert panel.attempts[0].status is GenerationAttemptStatus.FAILED
    assert panel.attempts[0].error_code == code
    assert panel.attempts[0].error_message == str(error)


def test_staging_failure_consumes_one_attempt() -> None:
    workspace = FakeWorkspace()
    workspace.stage_error = AuthoringWorkspaceError(
        "invalid_candidate",
        "Generated bytes failed local validation.",
    )
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    panel = workspace.state.panels["presence-neutral"]
    assert caught.value.code == "invalid_candidate"
    assert len(generator.requests) == 1
    assert panel.progress is PanelProgress.RETRY_READY
    assert panel.attempts[0].error_code == "invalid_candidate"


def test_sanitized_completed_state_save_failure_records_one_failed_attempt() -> None:
    secret = "filesystem-secret"
    workspace = FakeWorkspace()
    workspace.save_errors[2] = AuthoringWorkspaceError(
        "state_save_failed",
        "Completed candidate state could not be persisted.",
    )
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    panel = workspace.state.panels["presence-neutral"]
    assert caught.value.code == "state_save_failed"
    assert secret not in str(caught.value)
    assert len(generator.requests) == 1
    assert len(workspace.staged) == 1
    assert panel.progress is PanelProgress.RETRY_READY
    assert len(panel.attempts) == 1
    assert panel.attempts[0].status is GenerationAttemptStatus.FAILED
    assert panel.attempts[0].error_code == "state_save_failed"
    assert secret not in (panel.attempts[0].error_message or "")


def test_unexpected_completed_state_save_failure_recovers_on_next_run() -> None:
    secret = "unexpected-filesystem-secret"
    workspace = FakeWorkspace()
    workspace.save_errors[2] = RuntimeError(secret)
    generator = FakeGenerator(
        workspace,
        responses=[
            GeneratedImage(data=b"first", provider="fake", model="model"),
            GeneratedImage(data=b"retry", provider="fake", model="model"),
        ],
    )
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "unexpected_failure"
    assert secret not in str(caught.value)
    assert workspace.state.panels["presence-neutral"].progress is PanelProgress.GENERATING
    assert len(generator.requests) == 1
    assert len(workspace.staged) == 1

    result = service.run()

    attempts = workspace.state.panels["presence-neutral"].attempts
    assert result.attempt == 2
    assert attempts[0].error_code == "interrupted_attempt"
    assert attempts[1].status is GenerationAttemptStatus.CANDIDATE_READY
    assert len(generator.requests) == 2
    assert len(workspace.staged) == 2


def test_three_failures_exhaust_panel_and_fourth_run_is_provider_free() -> None:
    workspace = FakeWorkspace()
    generator = FakeGenerator(
        workspace,
        responses=[
            ImageGenerationError("provider_failure", "Sanitized failure.") for _ in range(3)
        ],
    )
    service = service_with(workspace, generator)

    for expected_attempt in (1, 2, 3):
        with pytest.raises(PixelPortraitWorkflowError) as caught:
            service.run()
        assert caught.value.code == "provider_failure"
        assert len(workspace.state.panels["presence-neutral"].attempts) == expected_attempt

    with pytest.raises(PixelPortraitWorkflowError) as exhausted:
        service.run()

    assert exhausted.value.code == "attempts_exhausted"
    assert workspace.state.panels["presence-neutral"].progress is PanelProgress.EXHAUSTED
    assert len(generator.requests) == 3


def test_interrupted_attempt_is_persisted_failed_before_next_attempt() -> None:
    state = initial_state()
    interrupted = GenerationAttempt(
        attempt_id="presence-neutral-attempt-1",
        task_id="presence-neutral",
        attempt=1,
        status=GenerationAttemptStatus.IN_PROGRESS,
        started_at=NOW,
    )
    panels = dict(state.panels)
    panels["presence-neutral"] = PixelPanelState(
        panel_id="presence-neutral",
        progress=PanelProgress.GENERATING,
        attempts=(interrupted,),
    )
    state = state.model_copy(update={"panels": panels})
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    result = service.run()

    panel = workspace.state.panels["presence-neutral"]
    assert result.attempt == 2
    assert workspace.saved[0].panels["presence-neutral"].attempts[0].error_code == (
        "interrupted_attempt"
    )
    assert [attempt.status for attempt in panel.attempts] == [
        GenerationAttemptStatus.FAILED,
        GenerationAttemptStatus.CANDIDATE_READY,
    ]
    assert len(generator.requests) == 1


def test_run_requires_generator_but_other_methods_do_not() -> None:
    workspace = FakeWorkspace()
    service = service_with(workspace)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "generator_not_configured"
    assert workspace.lock_entries == 0


def test_run_rejects_dependent_panel_when_injected_plan_dependency_is_unmet() -> None:
    neutral = PIXEL_PORTRAIT_PLAN.panel("presence-neutral")
    thinking = PIXEL_PORTRAIT_PLAN.panel("presence-thinking")
    injected_plan = PixelPortraitPlanDefinition.model_construct(
        plan_id=PIXEL_PORTRAIT_PLAN.plan_id,
        version=PIXEL_PORTRAIT_PLAN.version,
        base_prompt=PIXEL_PORTRAIT_PLAN.base_prompt,
        families=PIXEL_PORTRAIT_PLAN.families,
        panels=(
            thinking,
            neutral,
            *(
                panel
                for panel in PIXEL_PORTRAIT_PLAN.panels
                if panel.panel_id not in {neutral.panel_id, thinking.panel_id}
            ),
        ),
    )
    workspace = FakeWorkspace()
    generator = FakeGenerator(workspace)
    service = PixelPortraitService(
        workspace=workspace,
        generator=generator,
        plan=injected_plan,
        clock=TickingClock(),
    )

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "dependency_not_approved"
    assert generator.requests == []


def test_run_rejects_dependent_panel_without_neutral_identity_lock() -> None:
    state = initial_state()
    panels = dict(state.panels)
    panels["presence-neutral"] = approved_panel("presence-neutral")
    state = state.model_copy(update={"panels": panels, "identity_lock": None})
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "identity_lock_required"
    assert generator.requests == []


@pytest.mark.parametrize(
    "drift",
    ["plan_id", "plan_version", "panel_keys", "embedded_panel_id"],
)
def test_status_rejects_exact_plan_drift(drift: str) -> None:
    state = initial_state()
    if drift == "plan_id":
        state = state.model_copy(update={"plan_id": "unreviewed-plan"})
    elif drift == "plan_version":
        state = state.model_copy(update={"plan_version": "unreviewed-version"})
    elif drift == "panel_keys":
        panels = dict(state.panels)
        panels.pop("material-combined-palette")
        state = state.model_copy(update={"panels": panels})
    else:
        panels = dict(state.panels)
        panels["presence-neutral"] = PixelPanelState(panel_id="presence-thinking")
        state = state.model_copy(update={"panels": panels})
    service = service_with(FakeWorkspace(state))

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.status()

    assert caught.value.code == "plan_mismatch"


def test_run_rejects_technical_provenance_that_disagrees_with_v1_seal() -> None:
    state = with_approved_prefix(initial_state(), 7)
    technical_path = f"{_TECHNICAL_PREFIX}references/face/left-profile.png"
    provenance = tuple(
        record.model_copy(
            update={"artifact": record.artifact.model_copy(update={"sha256": "f" * 64})}
        )
        if record.artifact.path == technical_path
        else record
        for record in state.provenance
    )
    state = state.model_copy(update={"provenance": provenance})
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "source_evidence_invalid"
    assert generator.requests == []
    assert workspace.saved == []


def test_status_and_validate_are_provider_free_and_validation_is_locked() -> None:
    workspace = FakeWorkspace()
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    status = service.status()
    validation = service.validate()

    assert status == workspace.state
    assert validation.valid is True
    assert validation.incomplete_panels == tuple(
        panel.panel_id for panel in PIXEL_PORTRAIT_PLAN.panels
    )
    assert validation.blocking_gaps == ("source-rights-incomplete",)
    assert validation.panel_progress["presence-neutral"] is PanelProgress.PENDING
    assert workspace.validated == [workspace.state]
    assert workspace.lock_entries == 1
    assert generator.requests == []


def test_validate_translates_sanitized_workspace_error() -> None:
    workspace = FakeWorkspace()
    workspace.validate_error = AuthoringWorkspaceError(
        "integrity_failure",
        "Locked evidence changed.",
    )
    service = service_with(workspace)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.validate()

    assert caught.value.code == "integrity_failure"
    assert str(caught.value) == "Locked evidence changed."


def test_set_rights_updates_only_base_sources_and_clears_only_rights_gap() -> None:
    workspace = FakeWorkspace()
    generator = FakeGenerator(workspace)
    imported_before = tuple(
        record
        for record in workspace.state.provenance
        if record.artifact.path.startswith(_TECHNICAL_PREFIX)
    )
    service = service_with(workspace, generator)
    rights = complete_rights()

    updated = service.set_rights(
        rights,
        authoritative_source="User-approved base-set source.",
    )

    assert tuple(record.artifact.path for record in updated) == tuple(
        f"{_BASE_PREFIX}{name}" for name in BASE_SOURCE_FILENAMES
    )
    assert all(record.rights == rights for record in updated)
    assert all(
        record.authoritative_source == "User-approved base-set source." for record in updated
    )
    assert workspace.state.revision.base_source_rights == rights
    imported_after = tuple(
        record
        for record in workspace.state.provenance
        if record.artifact.path.startswith(_TECHNICAL_PREFIX)
    )
    assert imported_after == imported_before
    assert {gap.gap_id for gap in workspace.state.gaps} == {"measurements-missing"}
    assert workspace.lock_entries == 1
    assert generator.requests == []


@pytest.mark.parametrize(
    ("rights", "source", "code"),
    [
        (RightsMetadata(author="Katherine E. Aguirre"), "Approved source.", "incomplete_rights"),
        (complete_rights(), "   ", "invalid_authoritative_source"),
    ],
)
def test_set_rights_rejects_invalid_metadata(
    rights: RightsMetadata,
    source: str,
    code: str,
) -> None:
    service = service_with(FakeWorkspace())

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.set_rights(rights, authoritative_source=source)

    assert caught.value.code == code


def test_set_rights_does_not_overwrite_complete_revision_rights() -> None:
    state = initial_state()
    state = state.model_copy(
        update={
            "revision": state.revision.model_copy(update={"base_source_rights": complete_rights()})
        }
    )
    service = service_with(FakeWorkspace(state))

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.set_rights(
            complete_rights(),
            authoritative_source="Replacement source.",
        )

    assert caught.value.code == "rights_already_complete"


@pytest.mark.parametrize("failure_point", ["provider", "staging"])
def test_unexpected_failure_is_sanitized_and_recovered_on_next_run(
    failure_point: str,
) -> None:
    secret = "remote-secret-token"
    workspace = FakeWorkspace()
    responses: list[GeneratedImage | BaseException]
    if failure_point == "provider":
        responses = [
            RuntimeError(secret),
            GeneratedImage(data=b"retry", provider="fake", model="model"),
        ]
    else:
        responses = [
            GeneratedImage(data=b"first", provider="fake", model="model"),
            GeneratedImage(data=b"retry", provider="fake", model="model"),
        ]
        workspace.stage_error = RuntimeError(secret)
    generator = FakeGenerator(workspace, responses=responses)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "unexpected_failure"
    assert secret not in str(caught.value)
    in_progress = workspace.state.panels["presence-neutral"].attempts[0]
    assert in_progress.status is GenerationAttemptStatus.IN_PROGRESS
    assert in_progress.error_message is None

    workspace.stage_error = None
    result = service.run()

    attempts = workspace.state.panels["presence-neutral"].attempts
    assert result.attempt == 2
    assert attempts[0].error_code == "interrupted_attempt"
    assert secret not in (attempts[0].error_message or "")


def test_all_approved_panels_report_authoring_complete_without_provider_call() -> None:
    state = with_approved_prefix(initial_state(), len(PIXEL_PORTRAIT_PLAN.panels))
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.run()

    assert caught.value.code == "authoring_complete"
    assert generator.requests == []


def test_approve_panel_records_exact_scope_and_neutral_identity_lock() -> None:
    pending_panel = candidate_ready_panel("presence-neutral")
    workspace = FakeWorkspace(with_panel_state(initial_state(), pending_panel))
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]

    decision = service.approve_panel(
        panel_id="presence-neutral",
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Approved neutral identity and every candidate artifact.",
        identity_lock=identity_lock(),
    )

    restored = workspace.state.panels["presence-neutral"]
    assert decision.approval_id == f"approve-{candidate.candidate_id}"
    assert decision.reviewed_artifacts == panel_review_scope(candidate)
    assert restored.progress is PanelProgress.APPROVED
    assert restored.candidates[0].status is CandidateStatus.APPROVED
    assert restored.approved_candidate_id == candidate.candidate_id
    assert workspace.state.identity_lock == identity_lock()
    assert generator.requests == []


@pytest.mark.parametrize(
    ("attempt", "expected_progress"),
    [(1, PanelProgress.RETRY_READY), (3, PanelProgress.EXHAUSTED)],
)
def test_reject_panel_preserves_history_and_reopens_by_attempt_budget(
    attempt: int,
    expected_progress: PanelProgress,
) -> None:
    pending_panel = candidate_ready_panel("presence-neutral", attempt=attempt)
    workspace = FakeWorkspace(with_panel_state(initial_state(), pending_panel))
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]

    decision = service.reject_panel(
        panel_id="presence-neutral",
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Rejected after reviewing all candidate evidence.",
    )

    restored = workspace.state.panels["presence-neutral"]
    assert decision.approval_id == f"reject-{candidate.candidate_id}"
    assert restored.progress is expected_progress
    assert restored.attempts == pending_panel.attempts
    assert restored.candidates[0].status is CandidateStatus.REJECTED
    assert restored.decisions == (decision,)
    assert generator.requests == []


def test_supersede_panel_preserves_approved_history_and_clears_neutral_lock() -> None:
    state = with_approved_prefix(initial_state(), 1)
    panel = state.panels["presence-neutral"]
    candidate = panel.candidates[0]
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    decision = service.supersede_panel(
        panel_id="presence-neutral",
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Superseded after reviewing the active neutral evidence.",
    )

    restored = workspace.state.panels["presence-neutral"]
    assert decision.approval_id == f"supersede-{candidate.candidate_id}"
    assert restored.progress is PanelProgress.RETRY_READY
    assert restored.attempts == panel.attempts
    assert restored.candidates[0].status is CandidateStatus.SUPERSEDED
    assert restored.decisions == (*panel.decisions, decision)
    assert restored.approved_candidate_id is None
    assert workspace.state.identity_lock is None
    assert generator.requests == []


def test_panel_approval_does_not_compose_before_its_family_is_complete() -> None:
    state = with_approved_prefix(initial_state(), 1)
    pending_panel = candidate_ready_panel("presence-thinking")
    workspace = FakeWorkspace(with_panel_state(state, pending_panel))
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]

    service.approve_panel(
        panel_id=pending_panel.panel_id,
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Approved after complete panel review.",
    )

    assert workspace.composed == []
    assert workspace.state.composites == ()
    assert generator.requests == []


def test_last_family_panel_approval_composes_one_pending_family_sheet() -> None:
    state = with_approved_prefix(initial_state(), 5)
    pending_panel = candidate_ready_panel("presence-error")
    workspace = FakeWorkspace(with_panel_state(state, pending_panel))
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]

    service.approve_panel(
        panel_id=pending_panel.panel_id,
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Approved final presence-state panel.",
    )

    assert len(workspace.composed) == 1
    composite = workspace.composed[0]
    family = PIXEL_PORTRAIT_PLAN.family("presence-states")
    assert composite.composite_id == "family-presence-states-v1"
    assert composite.scope is CompositeScope.FAMILY
    assert composite.family_id == family.family_id
    assert composite.member_ids == family.panel_ids
    assert composite.status is CompositeStatus.PENDING_REVIEW
    assert workspace.state.composites == (composite,)
    assert workspace.events[-3:] == ["validate", "compose", "save"]
    assert workspace.lock_entries == 1
    assert generator.requests == []


def test_all_nine_family_approvals_compose_one_pending_package_master() -> None:
    state = with_approved_prefix(initial_state(), len(PIXEL_PORTRAIT_PLAN.panels))
    state = with_family_composites(
        state,
        {
            family.family_id: CompositeStatus.PENDING_REVIEW
            for family in PIXEL_PORTRAIT_PLAN.families
        },
    )
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    for family in reversed(PIXEL_PORTRAIT_PLAN.families):
        composite = next(
            item for item in workspace.state.composites if item.family_id == family.family_id
        )
        service.approve_composite(
            composite_id=composite.composite_id,
            reviewed_artifacts=(composite.artifact.path,),
            approver="Kathy",
            notes=f"Approved the exact {family.family_id} review sheet.",
        )

    family_ids = tuple(
        composite_id
        for composite_id in workspace.state.active_composite_ids
        if composite_id.startswith("family-")
    )
    assert family_ids == tuple(
        f"family-{family.family_id}-v1" for family in PIXEL_PORTRAIT_PLAN.families
    )
    assert len(workspace.composed) == 1
    master = workspace.composed[0]
    assert master.composite_id == "package-master-v1"
    assert master.scope is CompositeScope.PACKAGE_MASTER
    assert master.member_ids == family_ids
    assert master.status is CompositeStatus.PENDING_REVIEW
    assert workspace.state.composites[-1] == master
    assert generator.requests == []


def test_package_master_approval_sets_canonical_content_evidence() -> None:
    state = with_approved_prefix(initial_state(), len(PIXEL_PORTRAIT_PLAN.panels))
    state = with_family_composites(
        state,
        {family.family_id: CompositeStatus.APPROVED for family in PIXEL_PORTRAIT_PLAN.families},
    )
    state = with_package_master(state, status=CompositeStatus.PENDING_REVIEW)
    master = state.composites[-1]
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    decision = service.approve_composite(
        composite_id=master.composite_id,
        reviewed_artifacts=(master.artifact.path,),
        approver="Kathy",
        notes="Approved the exact deterministic package master.",
    )

    restored_master = workspace.state.composites[-1]
    reference = workspace.state.revision.master_reference
    assert decision.approval_id == f"approve-{master.composite_id}"
    assert restored_master.status is CompositeStatus.APPROVED
    assert workspace.state.active_composite_ids[-1] == master.composite_id
    assert reference is not None
    assert reference.path == PACKAGE_MASTER_PATH
    assert (
        reference.sha256,
        reference.byte_length,
        reference.width,
        reference.height,
    ) == (
        master.artifact.sha256,
        master.artifact.byte_length,
        master.artifact.width,
        master.artifact.height,
    )
    assert reference.path != master.artifact.path
    assert generator.requests == []


def fully_composed_approved_state() -> PixelPortraitAuthoringState:
    state = with_approved_prefix(initial_state(), len(PIXEL_PORTRAIT_PLAN.panels))
    state = with_family_composites(
        state,
        {family.family_id: CompositeStatus.APPROVED for family in PIXEL_PORTRAIT_PLAN.families},
    )
    return with_package_master(state, status=CompositeStatus.APPROVED)


def test_supersede_stales_only_owning_family_and_every_master() -> None:
    state = fully_composed_approved_state()
    pending_family = family_composite(state, "expressions")
    pending_master = package_master_composite(state)
    payload = state.model_dump(mode="python")
    payload["composites"] = (*state.composites, pending_family, pending_master)
    state = PixelPortraitAuthoringState.model_validate(payload)
    target = state.panels["expression-happy"]
    candidate = active_panel_candidate(state, target.panel_id)
    approvals_before = state.composite_approvals
    sibling = next(item for item in state.composites if item.family_id == "presence-states")
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    service.supersede_panel(
        panel_id=target.panel_id,
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Superseded the active expression after exact evidence review.",
    )

    restored = workspace.state
    invalidated = tuple(
        item
        for item in restored.composites
        if item.family_id == "expressions" or item.scope is CompositeScope.PACKAGE_MASTER
    )
    assert len(invalidated) == 4
    assert all(item.status is CompositeStatus.STALE for item in invalidated)
    assert (
        next(item for item in restored.composites if item.composite_id == sibling.composite_id)
        == sibling
    )
    assert sibling.composite_id in restored.active_composite_ids
    assert not any(item.composite_id in restored.active_composite_ids for item in invalidated)
    assert restored.composite_approvals == approvals_before
    assert restored.revision.master_reference is None
    assert generator.requests == []


def test_reapproval_after_stale_revision_recomposes_family_then_master() -> None:
    state = fully_composed_approved_state()
    target = state.panels["expression-happy"]
    first_candidate = active_panel_candidate(state, target.panel_id)
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    service.supersede_panel(
        panel_id=target.panel_id,
        candidate_id=first_candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(first_candidate),
        approver="Kathy",
        notes="Superseded the active expression after exact evidence review.",
    )
    superseded_panel = workspace.state.panels[target.panel_id]
    pending_panel = candidate_ready_panel(
        target.panel_id,
        attempt=2,
        history=superseded_panel,
    )
    workspace.state = with_panel_state(workspace.state, pending_panel)
    second_candidate = pending_panel.candidates[-1]

    service.approve_panel(
        panel_id=target.panel_id,
        candidate_id=second_candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(second_candidate),
        approver="Kathy",
        notes="Approved the replacement expression after full review.",
    )

    replacement_family = workspace.state.composites[-1]
    assert replacement_family.composite_id == "family-expressions-v2"
    assert replacement_family.status is CompositeStatus.PENDING_REVIEW
    assert workspace.state.panels[target.panel_id].decisions[-1].candidate_id == (
        second_candidate.candidate_id
    )

    service.approve_composite(
        composite_id=replacement_family.composite_id,
        reviewed_artifacts=(replacement_family.artifact.path,),
        approver="Kathy",
        notes="Approved the recomposed expression family sheet.",
    )

    replacement_master = workspace.state.composites[-1]
    assert replacement_master.composite_id == "package-master-v2"
    assert replacement_master.status is CompositeStatus.PENDING_REVIEW
    assert workspace.state.composites[9].status is CompositeStatus.STALE
    assert generator.requests == []


def test_neutral_approval_requires_identity_lock_without_mutation() -> None:
    pending_panel = candidate_ready_panel("presence-neutral")
    workspace = FakeWorkspace(with_panel_state(initial_state(), pending_panel))
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]
    before = workspace.state

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.approve_panel(
            panel_id=pending_panel.panel_id,
            candidate_id=candidate.candidate_id,
            reviewed_artifacts=panel_review_scope(candidate),
            approver="Kathy",
            notes="Reviewed every neutral candidate artifact.",
        )

    assert caught.value.code == "identity_lock_required"
    assert workspace.state == before
    assert workspace.events == ["validate"]
    assert workspace.saved == []
    assert generator.requests == []


def test_non_neutral_approval_rejects_identity_lock() -> None:
    state = with_approved_prefix(initial_state(), 1)
    pending_panel = candidate_ready_panel("presence-thinking")
    workspace = FakeWorkspace(with_panel_state(state, pending_panel))
    service = service_with(workspace)
    candidate = pending_panel.candidates[0]

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.approve_panel(
            panel_id=pending_panel.panel_id,
            candidate_id=candidate.candidate_id,
            reviewed_artifacts=panel_review_scope(candidate),
            approver="Kathy",
            notes="Reviewed every thinking-state artifact.",
            identity_lock=identity_lock(),
        )

    assert caught.value.code == "identity_lock_not_allowed"
    assert workspace.saved == []


def test_neutral_supersede_rejects_any_dependent_panel_history() -> None:
    state = with_approved_prefix(initial_state(), 2)
    neutral = active_panel_candidate(state, "presence-neutral")
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.supersede_panel(
            panel_id="presence-neutral",
            candidate_id=neutral.candidate_id,
            reviewed_artifacts=panel_review_scope(neutral),
            approver="Kathy",
            notes="Requested neutral replacement after dependent history.",
        )

    assert caught.value.code == "dependent_history_exists"
    assert workspace.state == state
    assert workspace.saved == []
    assert generator.requests == []


@pytest.mark.parametrize(
    ("approver", "notes", "code"),
    [
        ("   ", "Reviewed every artifact.", "invalid_approver"),
        ("Kathy", "\t", "invalid_notes"),
    ],
)
def test_panel_decisions_reject_blank_human_evidence_before_lock(
    approver: str,
    notes: str,
    code: str,
) -> None:
    pending_panel = candidate_ready_panel("presence-neutral")
    workspace = FakeWorkspace(with_panel_state(initial_state(), pending_panel))
    service = service_with(workspace)
    candidate = pending_panel.candidates[0]

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.reject_panel(
            panel_id=pending_panel.panel_id,
            candidate_id=candidate.candidate_id,
            reviewed_artifacts=panel_review_scope(candidate),
            approver=approver,
            notes=notes,
        )

    assert caught.value.code == code
    assert workspace.lock_entries == 0
    assert workspace.saved == []


@pytest.mark.parametrize(
    ("panel_id", "candidate_id", "reviewed_artifacts", "code"),
    [
        ("unknown-panel", "presence-neutral-attempt-1", (), "unknown_panel"),
        ("presence-neutral", "wrong-candidate", (), "unknown_candidate"),
        (
            "presence-neutral",
            "presence-neutral-attempt-1",
            ("candidates/presence-neutral/attempt-1/raw.png",),
            "review_scope_mismatch",
        ),
    ],
)
def test_panel_decisions_reject_wrong_ids_and_review_scope(
    panel_id: str,
    candidate_id: str,
    reviewed_artifacts: tuple[str, ...],
    code: str,
) -> None:
    pending_panel = candidate_ready_panel("presence-neutral")
    workspace = FakeWorkspace(with_panel_state(initial_state(), pending_panel))
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.reject_panel(
            panel_id=panel_id,
            candidate_id=candidate_id,
            reviewed_artifacts=reviewed_artifacts,
            approver="Kathy",
            notes="Reviewed the requested evidence.",
        )

    assert caught.value.code == code
    assert workspace.saved == []
    assert generator.requests == []


def test_duplicate_panel_decision_is_provider_free_and_history_is_immutable() -> None:
    pending_panel = candidate_ready_panel("presence-neutral")
    workspace = FakeWorkspace(with_panel_state(initial_state(), pending_panel))
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]
    first = service.reject_panel(
        panel_id=pending_panel.panel_id,
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Rejected after exact evidence review.",
    )

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.reject_panel(
            panel_id=pending_panel.panel_id,
            candidate_id=candidate.candidate_id,
            reviewed_artifacts=panel_review_scope(candidate),
            approver="Kathy",
            notes="Rejected after exact evidence review.",
        )

    panel = workspace.state.panels[pending_panel.panel_id]
    assert caught.value.code == "decision_conflict"
    assert panel.attempts == pending_panel.attempts
    assert panel.decisions == (first,)
    assert len(panel.candidates) == 1
    assert generator.requests == []


def state_with_pending_family_composite() -> PixelPortraitAuthoringState:
    state = with_approved_prefix(initial_state(), len(PIXEL_PORTRAIT_PLAN.panels))
    return with_family_composites(
        state,
        {"presence-states": CompositeStatus.PENDING_REVIEW},
    )


@pytest.mark.parametrize(
    ("case", "code"),
    [
        ("unknown", "unknown_composite"),
        ("wrong_scope", "review_scope_mismatch"),
        ("stale_status", "composite_not_pending"),
        ("stale_members", "composite_stale"),
    ],
)
def test_composite_approval_rejects_wrong_duplicate_or_stale_evidence(
    case: str,
    code: str,
) -> None:
    state = state_with_pending_family_composite()
    composite = state.composites[0]
    composite_id = composite.composite_id
    reviewed_artifacts: tuple[str, ...] = (composite.artifact.path,)
    if case == "unknown":
        composite_id = "unknown-composite"
    elif case == "wrong_scope":
        reviewed_artifacts = (
            composite.artifact.path,
            "composites/extra.png",
        )
    elif case == "stale_status":
        payload = state.model_dump(mode="python")
        payload["composites"] = (composite.model_copy(update={"status": CompositeStatus.STALE}),)
        state = PixelPortraitAuthoringState.model_validate(payload)
    elif case == "stale_members":
        state = with_panel_state(
            state,
            reapproved_panel(PIXEL_PORTRAIT_PLAN.family("presence-states").panel_ids[1]),
        )
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.approve_composite(
            composite_id=composite_id,
            reviewed_artifacts=reviewed_artifacts,
            approver="Kathy",
            notes="Reviewed the requested composite evidence.",
        )

    assert caught.value.code == code
    assert workspace.saved == []
    assert generator.requests == []


def test_duplicate_composite_approval_preserves_one_human_record() -> None:
    state = state_with_pending_family_composite()
    composite = state.composites[0]
    workspace = FakeWorkspace(state)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    approval = service.approve_composite(
        composite_id=composite.composite_id,
        reviewed_artifacts=(composite.artifact.path,),
        approver="Kathy",
        notes="Approved the exact family composite.",
    )

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.approve_composite(
            composite_id=composite.composite_id,
            reviewed_artifacts=(composite.artifact.path,),
            approver="Kathy",
            notes="Approved the exact family composite.",
        )

    assert caught.value.code == "composite_not_pending"
    assert workspace.state.composite_approvals == (approval,)
    assert workspace.events[:2] == ["validate", "save"]
    assert generator.requests == []


def test_new_family_approval_replaces_old_active_id_without_erasing_history() -> None:
    state = with_approved_prefix(initial_state(), len(PIXEL_PORTRAIT_PLAN.panels))
    state = with_family_composites(
        state,
        {"presence-states": CompositeStatus.APPROVED},
    )
    old = state.composites[0]
    replacement = family_composite(state, "presence-states")
    payload = state.model_dump(mode="python")
    payload["composites"] = (*state.composites, replacement)
    state = PixelPortraitAuthoringState.model_validate(payload)
    workspace = FakeWorkspace(state)
    service = service_with(workspace)

    replacement_approval = service.approve_composite(
        composite_id=replacement.composite_id,
        reviewed_artifacts=(replacement.artifact.path,),
        approver="Kathy",
        notes="Approved the replacement family composite.",
    )

    assert workspace.state.active_composite_ids == (replacement.composite_id,)
    assert workspace.state.composites[0] == old
    assert workspace.state.composites[0].status is CompositeStatus.APPROVED
    assert workspace.state.composite_approvals == (
        composite_approval(old),
        replacement_approval,
    )


def test_family_replacement_invalidates_active_master_and_recomposes() -> None:
    state = fully_composed_approved_state()
    old_master = next(
        item for item in state.composites if item.scope is CompositeScope.PACKAGE_MASTER
    )
    replacement = family_composite(state, "expressions")
    payload = state.model_dump(mode="python")
    payload["composites"] = (*state.composites, replacement)
    state = PixelPortraitAuthoringState.model_validate(payload)
    workspace = FakeWorkspace(state)
    service = service_with(workspace)

    service.approve_composite(
        composite_id=replacement.composite_id,
        reviewed_artifacts=(replacement.artifact.path,),
        approver="Kathy",
        notes="Approved the replacement expression-family composite.",
    )

    restored_old_master = next(
        item for item in workspace.state.composites if item.composite_id == old_master.composite_id
    )
    new_master = workspace.state.composites[-1]
    assert restored_old_master.status is CompositeStatus.STALE
    assert old_master.composite_id not in workspace.state.active_composite_ids
    assert workspace.state.revision.master_reference is None
    assert replacement.composite_id in workspace.state.active_composite_ids
    assert new_master.composite_id == "package-master-v2"
    assert new_master.status is CompositeStatus.PENDING_REVIEW


def test_compose_then_save_failure_retry_reuses_id_without_duplicate_history() -> None:
    state = with_approved_prefix(initial_state(), 5)
    pending_panel = candidate_ready_panel("presence-error")
    initial = with_panel_state(state, pending_panel)
    workspace = FakeWorkspace(initial)
    workspace.save_errors[1] = AuthoringWorkspaceError(
        "state_save_failed",
        "Decision state could not be persisted.",
    )
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]
    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.approve_panel(
            panel_id=pending_panel.panel_id,
            candidate_id=candidate.candidate_id,
            reviewed_artifacts=panel_review_scope(candidate),
            approver="Kathy",
            notes="Approved final family member after exact review.",
        )

    assert caught.value.code == "state_save_failed"
    assert workspace.state == initial
    assert [item.composite_id for item in workspace.composed] == ["family-presence-states-v1"]

    decision = service.approve_panel(
        panel_id=pending_panel.panel_id,
        candidate_id=candidate.candidate_id,
        reviewed_artifacts=panel_review_scope(candidate),
        approver="Kathy",
        notes="Approved final family member after exact review.",
    )

    panel = workspace.state.panels[pending_panel.panel_id]
    assert [item.composite_id for item in workspace.composed] == [
        "family-presence-states-v1",
        "family-presence-states-v1",
    ]
    assert len(workspace.state.composites) == 1
    assert workspace.state.composites[0].composite_id == "family-presence-states-v1"
    assert panel.decisions == (decision,)
    assert len(panel.candidates) == 1
    assert generator.requests == []


def test_unexpected_decision_compose_failure_is_sanitized_and_atomic() -> None:
    secret = "local-compose-secret"
    state = with_approved_prefix(initial_state(), 5)
    pending_panel = candidate_ready_panel("presence-error")
    initial = with_panel_state(state, pending_panel)
    workspace = FakeWorkspace(initial)
    workspace.compose_error = RuntimeError(secret)
    generator = FakeGenerator(workspace)
    service = service_with(workspace, generator)
    candidate = pending_panel.candidates[0]

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service.approve_panel(
            panel_id=pending_panel.panel_id,
            candidate_id=candidate.candidate_id,
            reviewed_artifacts=panel_review_scope(candidate),
            approver="Kathy",
            notes="Approved final family member after exact review.",
        )

    assert caught.value.code == "unexpected_failure"
    assert secret not in str(caught.value)
    assert workspace.state == initial
    assert workspace.saved == []
    assert generator.requests == []


def test_seal_validates_under_lock_then_delegates_without_a_provider() -> None:
    state = sealable_state()
    workspace = FakeWorkspace(state)
    service = service_with(workspace)
    destination = Path("published-pixel-package")

    evidence = service.seal(destination)

    assert evidence.package_id == state.revision.package_id
    assert workspace.load_lock_states == [True]
    assert workspace.validated == [state]
    assert workspace.sealed == [(state, destination, NOW)]
    assert workspace.events == ["validate", "seal"]
    assert workspace.lock_entries == 1


def test_seal_rejects_fixed_plan_drift_before_integrity_or_publication() -> None:
    state = sealable_state().model_copy(update={"plan_version": "drifted-plan"})
    workspace = FakeWorkspace(state)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "plan_mismatch"
    assert workspace.load_lock_states == [True]
    assert workspace.events == []
    assert workspace.validated == []
    assert workspace.sealed == []


def test_seal_rejects_failed_workspace_integrity_before_publication() -> None:
    workspace = FakeWorkspace(sealable_state())
    workspace.validate_error = AuthoringWorkspaceError(
        "integrity_failure",
        "Pixel portrait workspace integrity validation failed.",
    )

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "integrity_failure"
    assert workspace.events == ["validate"]
    assert workspace.sealed == []


@pytest.mark.parametrize(
    "active_state",
    ["pending", "in_progress", "rejected", "superseded"],
)
def test_seal_requires_one_active_approval_for_every_panel(active_state: str) -> None:
    state = sealable_panel_state()
    panel_id = PIXEL_PORTRAIT_PLAN.panels[-1].panel_id
    state = with_panel_state(
        state,
        panel_without_active_approval(panel_id, active_state),
    )
    workspace = FakeWorkspace(state)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "incomplete_authoring"
    assert panel_id in str(caught.value)
    assert workspace.events == ["validate"]
    assert workspace.sealed == []


def test_seal_rejects_any_visual_seal_blocking_gap() -> None:
    state = sealable_panel_state()
    blocking_gap = GapRecord(
        gap_id="visual-review-incomplete",
        area="visual-review",
        description="A visual review remains incomplete.",
        blocks_visual_seal=True,
    )
    state = state.model_copy(update={"gaps": (*state.gaps, blocking_gap)})
    workspace = FakeWorkspace(state)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "blocking_gap"
    assert "visual-review-incomplete" in str(caught.value)
    assert workspace.events == ["validate"]
    assert workspace.sealed == []


@pytest.mark.parametrize("invalid_family_state", ["missing", "out_of_order", "not_current"])
def test_seal_requires_nine_current_active_family_composites_in_plan_order(
    invalid_family_state: str,
) -> None:
    state = sealable_panel_state()
    if invalid_family_state != "missing":
        state = with_family_composites(
            state,
            {family.family_id: CompositeStatus.APPROVED for family in PIXEL_PORTRAIT_PLAN.families},
        )
    if invalid_family_state == "out_of_order":
        payload = state.model_dump(mode="python")
        payload["active_composite_ids"] = tuple(reversed(state.active_composite_ids))
        state = PixelPortraitAuthoringState.model_validate(payload)
    elif invalid_family_state == "not_current":
        first_id = state.active_composite_ids[0]
        composites = tuple(
            composite.model_copy(update={"member_hashes": ("e" * 64, *composite.member_hashes[1:])})
            if composite.composite_id == first_id
            else composite
            for composite in state.composites
        )
        state = state.model_copy(update={"composites": composites})
    workspace = FakeWorkspace(state)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "family_composites_incomplete"
    assert workspace.events == ["validate"]
    assert workspace.sealed == []


def test_seal_requires_one_current_active_approved_package_master() -> None:
    state = with_family_composites(
        sealable_panel_state(),
        {family.family_id: CompositeStatus.APPROVED for family in PIXEL_PORTRAIT_PLAN.families},
    )
    workspace = FakeWorkspace(state)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "package_master_incomplete"
    assert workspace.events == ["validate"]
    assert workspace.sealed == []


@pytest.mark.parametrize("master_evidence", ["missing", "content_mismatch"])
def test_seal_requires_current_canonical_revision_master_evidence(
    master_evidence: str,
) -> None:
    state = sealable_state()
    master_reference = state.revision.master_reference
    assert master_reference is not None
    replacement = (
        None
        if master_evidence == "missing"
        else master_reference.model_copy(update={"sha256": "f" * 64})
    )
    revision = state.revision.model_copy(update={"master_reference": replacement})
    state = state.model_copy(update={"revision": revision})
    workspace = FakeWorkspace(state)

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "master_reference_invalid"
    assert workspace.events == ["validate"]
    assert workspace.sealed == []


@pytest.mark.parametrize("failure_stage", ["integrity", "publication"])
def test_seal_sanitizes_unexpected_adapter_failures(failure_stage: str) -> None:
    workspace = FakeWorkspace(sealable_state())
    secret = RuntimeError("private adapter detail must not escape")
    if failure_stage == "integrity":
        workspace.validate_error = secret
    else:
        workspace.seal_error = secret

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("published-pixel-package"))

    assert caught.value.code == "unexpected_failure"
    assert "private adapter detail" not in str(caught.value)
    expected_events = ["validate"] if failure_stage == "integrity" else ["validate", "seal"]
    assert workspace.events == expected_events


def test_seal_preserves_sanitized_adapter_publication_diagnostic() -> None:
    workspace = FakeWorkspace(sealable_state())
    workspace.seal_error = AuthoringWorkspaceError(
        "destination_exists",
        "The package destination already exists.",
    )

    with pytest.raises(PixelPortraitWorkflowError) as caught:
        service_with(workspace).seal(Path("adapter-owned-destination"))

    assert caught.value.code == "destination_exists"
    assert str(caught.value) == "The package destination already exists."
    assert workspace.events == ["validate", "seal"]
