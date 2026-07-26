"""Plain application service for panel-first pixel portrait authoring."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from ..contracts import (
    ApprovalDecision,
    ArtifactEvidence,
    CandidateStatus,
    GenerationAttempt,
    GenerationAttemptStatus,
    ProvenanceRecord,
    RightsMetadata,
    SealEvidence,
    SourceClass,
    StrictDesignModel,
)
from ..ports import (
    AuthoringWorkspaceError,
    GenerationRequest,
    ImageGenerationError,
    ReferenceImageGeneratorPort,
)
from .contracts import (
    NEUTRAL_PANEL_ID,
    PACKAGE_MASTER_PATH,
    CompositeApproval,
    CompositeReviewSheet,
    CompositeScope,
    CompositeStatus,
    PanelProgress,
    PixelPanelApproval,
    PixelPanelCandidate,
    PixelPanelState,
    PixelPortraitAuthoringState,
    PortraitIdentityLock,
)
from .plan import (
    PIXEL_PORTRAIT_PLAN,
    PixelPanelDefinition,
    PixelPortraitPlanDefinition,
)
from .ports import (
    BASE_SOURCE_FILENAMES,
    PixelPortraitWorkspacePort,
    PixelWorkspaceInitialization,
)

_BASE_SOURCE_PREFIX = "sources/base-set/"
_TECHNICAL_SOURCE_PREFIX = "sources/talking-bust-v1/"
_MAX_ATTEMPTS = 3


class PixelPortraitWorkflowError(RuntimeError):
    """Stable sanitized application failure suitable for CLI translation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class PixelPortraitRunResult(StrictDesignModel):
    """Outcome of exactly one successful explicit panel generation."""

    panel_id: str
    attempt: int
    candidate: PixelPanelCandidate


class PixelPortraitValidationResult(StrictDesignModel):
    """Provider-free integrity result for the current authoring workspace."""

    valid: bool
    incomplete_panels: tuple[str, ...]
    blocking_gaps: tuple[str, ...]
    panel_progress: dict[str, PanelProgress]


class PixelPortraitService:
    """Coordinate one bounded panel transition per explicit invocation."""

    def __init__(
        self,
        *,
        workspace: PixelPortraitWorkspacePort,
        generator: ReferenceImageGeneratorPort | None = None,
        plan: PixelPortraitPlanDefinition = PIXEL_PORTRAIT_PLAN,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._plan = plan
        self._clock = clock or (lambda: datetime.now(UTC))

    def initialize(
        self,
        command: PixelWorkspaceInitialization,
    ) -> PixelPortraitAuthoringState:
        """Create one new no-clobber pixel portrait workspace."""
        return self._workspace.initialize(command)

    def status(self) -> PixelPortraitAuthoringState:
        """Return strict persisted state without invoking a provider."""
        try:
            state = self._workspace.load_state()
        except AuthoringWorkspaceError as exc:
            raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
        except Exception as exc:
            raise self._unexpected_failure(exc) from exc
        self._validate_state_plan(state)
        return state

    def set_rights(
        self,
        rights: RightsMetadata,
        *,
        authoritative_source: str,
    ) -> tuple[ProvenanceRecord, ...]:
        """Complete direct rights on the seven locked base-set sources."""
        normalized_source = authoritative_source.strip()
        if not normalized_source:
            raise PixelPortraitWorkflowError(
                "invalid_authoritative_source",
                "Base-set provenance must not be empty.",
            )
        if not rights.is_complete:
            raise PixelPortraitWorkflowError(
                "incomplete_rights",
                "Every base-set rights field is required.",
            )

        with self._workspace.exclusive():
            try:
                state = self._workspace.load_state()
                self._validate_state_plan(state)
                if state.revision.base_source_rights.is_complete:
                    raise PixelPortraitWorkflowError(
                        "rights_already_complete",
                        "Complete base-set rights are immutable for this revision.",
                    )
                base_records = self._base_provenance_by_path(state)
                updated_by_path = {
                    path: base_records[path].model_copy(
                        update={
                            "authoritative_source": normalized_source,
                            "rights": rights,
                        }
                    )
                    for path in self._canonical_base_paths()
                }
                provenance = tuple(
                    updated_by_path.get(record.artifact.path, record) for record in state.provenance
                )
                revision = state.revision.model_copy(update={"base_source_rights": rights})
                gaps = tuple(gap for gap in state.gaps if gap.gap_id != "source-rights-incomplete")
                updated_state = state.model_copy(
                    update={
                        "revision": revision,
                        "provenance": provenance,
                        "gaps": gaps,
                    }
                )
                self._workspace.save_state(updated_state)
            except PixelPortraitWorkflowError:
                raise
            except AuthoringWorkspaceError as exc:
                raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
            except Exception as exc:
                raise self._unexpected_failure(exc) from exc
            return tuple(updated_by_path[path] for path in self._canonical_base_paths())

    def validate(self) -> PixelPortraitValidationResult:
        """Validate strict state and locked artifacts without using a provider."""
        with self._workspace.exclusive():
            try:
                state = self._workspace.load_state()
                self._validate_state_plan(state)
                self._workspace.validate(state)
            except PixelPortraitWorkflowError:
                raise
            except AuthoringWorkspaceError as exc:
                raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
            except Exception as exc:
                raise self._unexpected_failure(exc) from exc

            incomplete = tuple(
                panel.panel_id
                for panel in self._plan.panels
                if state.panels[panel.panel_id].progress is not PanelProgress.APPROVED
            )
            blocking = tuple(gap.gap_id for gap in state.gaps if gap.blocks_visual_seal)
            return PixelPortraitValidationResult(
                valid=True,
                incomplete_panels=incomplete,
                blocking_gaps=blocking,
                panel_progress={
                    panel_id: panel.progress for panel_id, panel in state.panels.items()
                },
            )

    def seal(self, destination: Path) -> SealEvidence:
        """Publish one fully approved and current pixel portrait package."""
        try:
            with self._workspace.exclusive():
                state = self._workspace.load_state()
                self._validate_state_plan(state)
                self._workspace.validate(state)

                incomplete = tuple(
                    panel.panel_id
                    for definition in self._plan.panels
                    if (panel := state.panels[definition.panel_id]).progress
                    is not PanelProgress.APPROVED
                )
                if incomplete:
                    raise PixelPortraitWorkflowError(
                        "incomplete_authoring",
                        "All 49 pixel portrait panels require one active approval "
                        "before sealing: " + ", ".join(incomplete),
                    )

                blocking = tuple(gap.gap_id for gap in state.gaps if gap.blocks_visual_seal)
                if blocking:
                    raise PixelPortraitWorkflowError(
                        "blocking_gap",
                        "Visual package sealing is blocked by: " + ", ".join(blocking),
                    )

                active_families = self._active_family_composites(state)
                composites = {composite.composite_id: composite for composite in state.composites}
                active_family_ids = tuple(
                    composite_id
                    for composite_id in state.active_composite_ids
                    if (composite := composites.get(composite_id)) is not None
                    and composite.scope is CompositeScope.FAMILY
                )
                expected_family_ids = tuple(composite.composite_id for composite in active_families)
                if (
                    len(active_families) != len(self._plan.families)
                    or active_family_ids != expected_family_ids
                ):
                    raise PixelPortraitWorkflowError(
                        "family_composites_incomplete",
                        "Sealing requires exactly nine current approved family "
                        "composites in fixed plan order.",
                    )

                active_master_ids = tuple(
                    composite_id
                    for composite_id in state.active_composite_ids
                    if (composite := composites.get(composite_id)) is not None
                    and composite.scope is CompositeScope.PACKAGE_MASTER
                )
                if len(active_master_ids) != 1:
                    raise PixelPortraitWorkflowError(
                        "package_master_incomplete",
                        "Sealing requires exactly one current approved package-master composite.",
                    )
                master = composites[active_master_ids[0]]
                if (
                    state.active_composite_ids != (*expected_family_ids, master.composite_id)
                    or master.status is not CompositeStatus.APPROVED
                    or not self._is_current_package_master(state, master)
                ):
                    raise PixelPortraitWorkflowError(
                        "package_master_incomplete",
                        "Sealing requires exactly one current approved package-master composite.",
                    )

                expected_master_reference = master.artifact.model_copy(
                    update={"path": PACKAGE_MASTER_PATH}
                )
                if state.revision.master_reference != expected_master_reference:
                    raise PixelPortraitWorkflowError(
                        "master_reference_invalid",
                        "The revision master reference must be canonical and match the "
                        "current approved package master.",
                    )

                return self._workspace.seal(state, Path(destination), self._clock())
        except PixelPortraitWorkflowError:
            raise
        except AuthoringWorkspaceError as exc:
            raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
        except Exception as exc:
            raise self._unexpected_failure(exc) from exc

    def approve_panel(
        self,
        *,
        panel_id: str,
        candidate_id: str,
        reviewed_artifacts: tuple[str, ...],
        approver: str,
        notes: str,
        identity_lock: PortraitIdentityLock | None = None,
    ) -> PixelPanelApproval:
        """Approve one pending panel candidate and preserve its exact review scope."""
        return self._decide_panel(
            panel_id=panel_id,
            candidate_id=candidate_id,
            reviewed_artifacts=reviewed_artifacts,
            decision=ApprovalDecision.APPROVE,
            approver=approver,
            notes=notes,
            identity_lock=identity_lock,
        )

    def reject_panel(
        self,
        *,
        panel_id: str,
        candidate_id: str,
        reviewed_artifacts: tuple[str, ...],
        approver: str,
        notes: str,
    ) -> PixelPanelApproval:
        """Reject one pending panel candidate without erasing attempt history."""
        return self._decide_panel(
            panel_id=panel_id,
            candidate_id=candidate_id,
            reviewed_artifacts=reviewed_artifacts,
            decision=ApprovalDecision.REJECT,
            approver=approver,
            notes=notes,
            identity_lock=None,
        )

    def supersede_panel(
        self,
        *,
        panel_id: str,
        candidate_id: str,
        reviewed_artifacts: tuple[str, ...],
        approver: str,
        notes: str,
    ) -> PixelPanelApproval:
        """Supersede only the active approved candidate while retaining history."""
        normalized_approver, normalized_notes = self._reviewer_text(approver, notes)
        try:
            with self._workspace.exclusive():
                state = self._workspace.load_state()
                self._validate_state_plan(state)
                self._workspace.validate(state)
                panel = self._panel_for_decision(state, panel_id)
                candidate = self._candidate_for_decision(panel, candidate_id)
                if (
                    panel.progress is not PanelProgress.APPROVED
                    or panel.approved_candidate_id != candidate_id
                    or candidate.status is not CandidateStatus.APPROVED
                ):
                    raise PixelPortraitWorkflowError(
                        "candidate_not_approved",
                        f"Candidate {candidate_id} is not the active approval "
                        f"for panel {panel_id}.",
                    )
                self._require_review_scope(candidate, reviewed_artifacts)
                if panel_id == NEUTRAL_PANEL_ID:
                    changed_dependents = tuple(
                        definition.panel_id
                        for definition in self._plan.panels
                        if panel_id in definition.dependencies
                        and not self._is_pristine(state.panels[definition.panel_id])
                    )
                    if changed_dependents:
                        raise PixelPortraitWorkflowError(
                            "dependent_history_exists",
                            "The neutral identity lock cannot be superseded after dependent "
                            "panel history exists.",
                        )

                record = PixelPanelApproval(
                    approval_id=f"supersede-{candidate_id}",
                    candidate_id=candidate_id,
                    panel_id=panel_id,
                    decision=ApprovalDecision.SUPERSEDE,
                    approver=normalized_approver,
                    decided_at=self._clock(),
                    reviewed_artifacts=reviewed_artifacts,
                    notes=normalized_notes,
                )
                superseded = candidate.model_copy(update={"status": CandidateStatus.SUPERSEDED})
                candidates = tuple(
                    superseded if item.candidate_id == candidate_id else item
                    for item in panel.candidates
                )
                progress = (
                    PanelProgress.EXHAUSTED
                    if len(panel.attempts) >= _MAX_ATTEMPTS
                    else PanelProgress.RETRY_READY
                )
                updated_panel = PixelPanelState(
                    panel_id=panel.panel_id,
                    progress=progress,
                    attempts=panel.attempts,
                    candidates=candidates,
                    decisions=(*panel.decisions, record),
                )
                updated_state = self._state_after_supersede(
                    state,
                    updated_panel,
                    family_id=self._plan.panel(panel_id).family_id,
                    identity_lock=(None if panel_id == NEUTRAL_PANEL_ID else state.identity_lock),
                )
                self._workspace.save_state(updated_state)
                return record
        except PixelPortraitWorkflowError:
            raise
        except AuthoringWorkspaceError as exc:
            raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
        except Exception as exc:
            raise self._unexpected_failure(exc) from exc

    def approve_composite(
        self,
        *,
        composite_id: str,
        reviewed_artifacts: tuple[str, ...],
        approver: str,
        notes: str,
    ) -> CompositeApproval:
        """Approve one recorded current composite after reviewing its one artifact."""
        normalized_approver, normalized_notes = self._reviewer_text(approver, notes)
        try:
            with self._workspace.exclusive():
                state = self._workspace.load_state()
                self._validate_state_plan(state)
                self._workspace.validate(state)
                composite = next(
                    (item for item in state.composites if item.composite_id == composite_id),
                    None,
                )
                if composite is None:
                    raise PixelPortraitWorkflowError(
                        "unknown_composite",
                        f"Unknown pixel portrait composite: {composite_id}.",
                    )
                if composite.status is not CompositeStatus.PENDING_REVIEW or any(
                    approval.composite_id == composite_id for approval in state.composite_approvals
                ):
                    raise PixelPortraitWorkflowError(
                        "composite_not_pending",
                        f"Composite {composite_id} is not awaiting human review.",
                    )
                if reviewed_artifacts != (composite.artifact.path,):
                    raise PixelPortraitWorkflowError(
                        "review_scope_mismatch",
                        "Composite review must cover exactly its one sheet artifact.",
                    )
                if composite.scope is CompositeScope.FAMILY:
                    if not self._is_current_family_composite(state, composite):
                        raise PixelPortraitWorkflowError(
                            "composite_stale",
                            f"Composite {composite_id} does not match current panel approvals.",
                        )
                elif not self._is_current_package_master(state, composite):
                    raise PixelPortraitWorkflowError(
                        "composite_stale",
                        f"Composite {composite_id} does not match current family approvals.",
                    )

                record = CompositeApproval(
                    approval_id=f"approve-{composite_id}",
                    composite_id=composite_id,
                    approver=normalized_approver,
                    decided_at=self._clock(),
                    reviewed_artifacts=reviewed_artifacts,
                    notes=normalized_notes,
                )
                approved = composite.model_copy(update={"status": CompositeStatus.APPROVED})
                composites = tuple(
                    approved if item.composite_id == composite_id else item
                    for item in state.composites
                )
                payload = state.model_dump(mode="python")
                payload.update(
                    {
                        "composites": composites,
                        "composite_approvals": (*state.composite_approvals, record),
                    }
                )
                if composite.scope is CompositeScope.FAMILY:
                    existing_active_family_id = next(
                        (
                            active_id
                            for active_id in state.active_composite_ids
                            if (
                                active := next(
                                    item
                                    for item in state.composites
                                    if item.composite_id == active_id
                                )
                            ).scope
                            is CompositeScope.FAMILY
                            and active.family_id == composite.family_id
                        ),
                        None,
                    )
                    if (
                        existing_active_family_id is not None
                        and existing_active_family_id != composite_id
                    ):
                        composites = tuple(
                            item.model_copy(update={"status": CompositeStatus.STALE})
                            if item.scope is CompositeScope.PACKAGE_MASTER
                            and item.status
                            in {
                                CompositeStatus.PENDING_REVIEW,
                                CompositeStatus.APPROVED,
                            }
                            else item
                            for item in composites
                        )
                        payload["composites"] = composites
                        payload["revision"] = state.revision.model_copy(
                            update={"master_reference": None}
                        )
                    active_family_ids = self._ordered_active_family_ids(
                        state,
                        replacement=approved,
                    )
                    payload["active_composite_ids"] = active_family_ids
                    updated_state = PixelPortraitAuthoringState.model_validate(payload)
                    updated_state = self._compose_master_if_ready(updated_state)
                else:
                    active_family_ids = self._ordered_active_family_ids(state)
                    payload["active_composite_ids"] = (
                        *active_family_ids,
                        composite_id,
                    )
                    payload["revision"] = state.revision.model_copy(
                        update={
                            "master_reference": composite.artifact.model_copy(
                                update={"path": PACKAGE_MASTER_PATH}
                            )
                        }
                    )
                    updated_state = PixelPortraitAuthoringState.model_validate(payload)
                self._workspace.save_state(updated_state)
                return record
        except PixelPortraitWorkflowError:
            raise
        except AuthoringWorkspaceError as exc:
            raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
        except Exception as exc:
            raise self._unexpected_failure(exc) from exc

    def run(self) -> PixelPortraitRunResult:
        """Issue at most one provider request for the next fixed panel."""
        if self._generator is None:
            raise PixelPortraitWorkflowError(
                "generator_not_configured",
                "No reference image generator is configured.",
            )

        with self._workspace.exclusive():
            try:
                state = self._workspace.load_state()
            except AuthoringWorkspaceError as exc:
                raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
            except Exception as exc:
                raise self._unexpected_failure(exc) from exc
            self._validate_state_plan(state)
            try:
                self._workspace.validate(state)
            except AuthoringWorkspaceError as exc:
                raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
            except Exception as exc:
                raise self._unexpected_failure(exc) from exc
            state = self._recover_interrupted_attempts(state)
            panel_definition, panel_state = self._next_panel(state)
            input_artifacts = self._input_artifacts(state, panel_definition)
            attempt_number = len(panel_state.attempts) + 1
            if attempt_number > _MAX_ATTEMPTS:
                raise PixelPortraitWorkflowError(
                    "attempts_exhausted",
                    f"Panel {panel_definition.panel_id} exhausted its three attempts.",
                )

            started_at = self._clock()
            in_progress = GenerationAttempt(
                attempt_id=(f"{panel_definition.panel_id}-attempt-{attempt_number}"),
                task_id=panel_definition.panel_id,
                attempt=attempt_number,
                status=GenerationAttemptStatus.IN_PROGRESS,
                started_at=started_at,
            )
            generating_panel = PixelPanelState(
                panel_id=panel_state.panel_id,
                progress=PanelProgress.GENERATING,
                attempts=(*panel_state.attempts, in_progress),
                candidates=panel_state.candidates,
                decisions=panel_state.decisions,
            )
            state = self._with_panel(state, generating_panel)

            try:
                self._workspace.save_state(state)
                request = GenerationRequest(
                    task_id=panel_definition.panel_id,
                    prompt_id=panel_definition.prompt_id,
                    prompt_version=panel_definition.prompt_version,
                    prompt=(f"{self._plan.base_prompt} {panel_definition.prompt_instruction}"),
                    input_paths=tuple(
                        self._workspace.resolve_artifact(item.path) for item in input_artifacts
                    ),
                    width=panel_definition.request_width,
                    height=panel_definition.request_height,
                )
                generated = self._generator.generate(request)
                candidate = self._workspace.stage_candidate(
                    panel=panel_definition,
                    attempt=attempt_number,
                    generated=generated,
                    input_artifacts=input_artifacts,
                    created_at=self._clock(),
                )
            except (ImageGenerationError, AuthoringWorkspaceError) as exc:
                self._record_failure(
                    state,
                    generating_panel,
                    in_progress,
                    code=exc.code,
                    message=str(exc),
                )
                raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
            except Exception as exc:
                raise self._unexpected_failure(exc) from exc

            completed = GenerationAttempt(
                attempt_id=in_progress.attempt_id,
                task_id=in_progress.task_id,
                attempt=in_progress.attempt,
                status=GenerationAttemptStatus.CANDIDATE_READY,
                started_at=in_progress.started_at,
                completed_at=self._clock(),
                candidate_id=candidate.candidate_id,
            )
            candidate_ready = PixelPanelState(
                panel_id=generating_panel.panel_id,
                progress=PanelProgress.CANDIDATE_READY,
                attempts=(*generating_panel.attempts[:-1], completed),
                candidates=(*generating_panel.candidates, candidate),
                decisions=generating_panel.decisions,
            )
            completed_state = self._with_panel(state, candidate_ready)
            try:
                self._workspace.save_state(completed_state)
            except AuthoringWorkspaceError as exc:
                self._record_failure(
                    state,
                    generating_panel,
                    in_progress,
                    code=exc.code,
                    message=str(exc),
                )
                raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
            except Exception as exc:
                raise self._unexpected_failure(exc) from exc
            return PixelPortraitRunResult(
                panel_id=panel_definition.panel_id,
                attempt=attempt_number,
                candidate=candidate,
            )

    def _decide_panel(
        self,
        *,
        panel_id: str,
        candidate_id: str,
        reviewed_artifacts: tuple[str, ...],
        decision: ApprovalDecision,
        approver: str,
        notes: str,
        identity_lock: PortraitIdentityLock | None,
    ) -> PixelPanelApproval:
        normalized_approver, normalized_notes = self._reviewer_text(approver, notes)
        try:
            with self._workspace.exclusive():
                state = self._workspace.load_state()
                self._validate_state_plan(state)
                self._workspace.validate(state)
                panel = self._panel_for_decision(state, panel_id)
                candidate = self._candidate_for_decision(panel, candidate_id)
                if candidate.status is not CandidateStatus.PENDING or any(
                    item.candidate_id == candidate_id for item in panel.decisions
                ):
                    raise PixelPortraitWorkflowError(
                        "decision_conflict",
                        f"Candidate {candidate_id} already has a human decision.",
                    )
                if panel.progress is not PanelProgress.CANDIDATE_READY:
                    raise PixelPortraitWorkflowError(
                        "candidate_not_pending",
                        f"Panel {panel_id} has no candidate awaiting review.",
                    )
                self._require_review_scope(candidate, reviewed_artifacts)
                if decision is ApprovalDecision.APPROVE:
                    if panel_id == NEUTRAL_PANEL_ID and identity_lock is None:
                        raise PixelPortraitWorkflowError(
                            "identity_lock_required",
                            "Approving presence-neutral requires an identity lock.",
                        )
                    if panel_id != NEUTRAL_PANEL_ID and identity_lock is not None:
                        raise PixelPortraitWorkflowError(
                            "identity_lock_not_allowed",
                            "Only presence-neutral can establish the identity lock.",
                        )

                record = PixelPanelApproval(
                    approval_id=f"{decision.value}-{candidate_id}",
                    candidate_id=candidate_id,
                    panel_id=panel_id,
                    decision=decision,
                    approver=normalized_approver,
                    decided_at=self._clock(),
                    reviewed_artifacts=reviewed_artifacts,
                    notes=normalized_notes,
                    identity_lock=(
                        identity_lock
                        if decision is ApprovalDecision.APPROVE and panel_id == NEUTRAL_PANEL_ID
                        else None
                    ),
                )
                candidate_status = (
                    CandidateStatus.APPROVED
                    if decision is ApprovalDecision.APPROVE
                    else CandidateStatus.REJECTED
                )
                decided_candidate = candidate.model_copy(update={"status": candidate_status})
                candidates = tuple(
                    decided_candidate if item.candidate_id == candidate_id else item
                    for item in panel.candidates
                )
                progress = (
                    PanelProgress.APPROVED
                    if decision is ApprovalDecision.APPROVE
                    else PanelProgress.EXHAUSTED
                    if len(panel.attempts) >= _MAX_ATTEMPTS
                    else PanelProgress.RETRY_READY
                )
                updated_panel = PixelPanelState(
                    panel_id=panel.panel_id,
                    progress=progress,
                    attempts=panel.attempts,
                    candidates=candidates,
                    decisions=(*panel.decisions, record),
                    approved_candidate_id=(
                        candidate_id if decision is ApprovalDecision.APPROVE else None
                    ),
                )
                updated_state = self._state_with_decided_panel(
                    state,
                    updated_panel,
                    identity_lock=(
                        identity_lock
                        if decision is ApprovalDecision.APPROVE and panel_id == NEUTRAL_PANEL_ID
                        else state.identity_lock
                    ),
                )
                if decision is ApprovalDecision.APPROVE:
                    updated_state = self._compose_family_if_ready(
                        updated_state,
                        panel_id,
                    )
                self._workspace.save_state(updated_state)
                return record
        except PixelPortraitWorkflowError:
            raise
        except AuthoringWorkspaceError as exc:
            raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
        except Exception as exc:
            raise self._unexpected_failure(exc) from exc

    @staticmethod
    def _reviewer_text(approver: str, notes: str) -> tuple[str, str]:
        normalized_approver = approver.strip()
        normalized_notes = notes.strip()
        if not normalized_approver:
            raise PixelPortraitWorkflowError(
                "invalid_approver",
                "The human approver must not be blank.",
            )
        if not normalized_notes:
            raise PixelPortraitWorkflowError(
                "invalid_notes",
                "Human review notes must not be blank.",
            )
        return normalized_approver, normalized_notes

    @staticmethod
    def _is_pristine(panel: PixelPanelState) -> bool:
        return (
            panel.progress is PanelProgress.PENDING
            and not panel.attempts
            and not panel.candidates
            and not panel.decisions
            and panel.approved_candidate_id is None
        )

    @staticmethod
    def _candidate_for_decision(
        panel: PixelPanelState,
        candidate_id: str,
    ) -> PixelPanelCandidate:
        candidate = next(
            (item for item in panel.candidates if item.candidate_id == candidate_id),
            None,
        )
        if candidate is None:
            raise PixelPortraitWorkflowError(
                "unknown_candidate",
                f"Candidate {candidate_id} does not belong to panel {panel.panel_id}.",
            )
        return candidate

    @staticmethod
    def _require_review_scope(
        candidate: PixelPanelCandidate,
        reviewed_artifacts: tuple[str, ...],
    ) -> None:
        expected = (
            candidate.raw_artifact.path,
            candidate.normalized_panel.path,
            candidate.validation_report.path,
        )
        if reviewed_artifacts != expected:
            raise PixelPortraitWorkflowError(
                "review_scope_mismatch",
                "Panel review must cover exactly the raw, normalized, and validation artifacts.",
            )

    def _panel_for_decision(
        self,
        state: PixelPortraitAuthoringState,
        panel_id: str,
    ) -> PixelPanelState:
        try:
            self._plan.panel(panel_id)
        except KeyError as exc:
            raise PixelPortraitWorkflowError(
                "unknown_panel",
                f"Unknown pixel portrait panel: {panel_id}.",
            ) from exc
        panel = state.panels.get(panel_id)
        if panel is None:
            raise PixelPortraitWorkflowError(
                "plan_mismatch",
                "Persisted state does not match the fixed pixel portrait plan.",
            )
        return panel

    @staticmethod
    def _state_with_decided_panel(
        state: PixelPortraitAuthoringState,
        panel: PixelPanelState,
        *,
        identity_lock: PortraitIdentityLock | None,
    ) -> PixelPortraitAuthoringState:
        panels = dict(state.panels)
        panels[panel.panel_id] = panel
        payload = state.model_dump(mode="python")
        payload.update({"panels": panels, "identity_lock": identity_lock})
        return PixelPortraitAuthoringState.model_validate(payload)

    @staticmethod
    def _state_after_supersede(
        state: PixelPortraitAuthoringState,
        panel: PixelPanelState,
        *,
        family_id: str,
        identity_lock: PortraitIdentityLock | None,
    ) -> PixelPortraitAuthoringState:
        panels = dict(state.panels)
        panels[panel.panel_id] = panel
        invalidated_ids: set[str] = set()
        invalidated_master = False
        composites: list[CompositeReviewSheet] = []
        for composite in state.composites:
            should_invalidate = composite.status in {
                CompositeStatus.PENDING_REVIEW,
                CompositeStatus.APPROVED,
            } and (
                (composite.scope is CompositeScope.FAMILY and composite.family_id == family_id)
                or composite.scope is CompositeScope.PACKAGE_MASTER
            )
            if should_invalidate:
                invalidated_ids.add(composite.composite_id)
                invalidated_master = (
                    invalidated_master or composite.scope is CompositeScope.PACKAGE_MASTER
                )
                composite = composite.model_copy(update={"status": CompositeStatus.STALE})
            composites.append(composite)
        revision = state.revision
        if invalidated_master:
            revision = revision.model_copy(update={"master_reference": None})
        payload = state.model_dump(mode="python")
        payload.update(
            {
                "panels": panels,
                "identity_lock": identity_lock,
                "composites": tuple(composites),
                "active_composite_ids": tuple(
                    composite_id
                    for composite_id in state.active_composite_ids
                    if composite_id not in invalidated_ids
                ),
                "revision": revision,
            }
        )
        return PixelPortraitAuthoringState.model_validate(payload)

    def _compose_family_if_ready(
        self,
        state: PixelPortraitAuthoringState,
        panel_id: str,
    ) -> PixelPortraitAuthoringState:
        family = self._plan.family(self._plan.panel(panel_id).family_id)
        if any(
            state.panels[member_id].progress is not PanelProgress.APPROVED
            for member_id in family.panel_ids
        ):
            return state
        if any(
            composite.scope is CompositeScope.FAMILY
            and composite.family_id == family.family_id
            and composite.status in {CompositeStatus.PENDING_REVIEW, CompositeStatus.APPROVED}
            and self._is_current_family_composite(state, composite)
            for composite in state.composites
        ):
            return state
        composite = self._workspace.compose(
            state=state,
            scope=CompositeScope.FAMILY,
            family_id=family.family_id,
            created_at=self._clock(),
        )
        if (
            composite.composite_id in {item.composite_id for item in state.composites}
            or composite.status is not CompositeStatus.PENDING_REVIEW
            or composite.scope is not CompositeScope.FAMILY
            or composite.family_id != family.family_id
            or not self._is_current_family_composite(state, composite)
        ):
            raise PixelPortraitWorkflowError(
                "invalid_composite",
                "The workspace returned invalid family-composite evidence.",
            )
        payload = state.model_dump(mode="python")
        payload["composites"] = (*state.composites, composite)
        return PixelPortraitAuthoringState.model_validate(payload)

    def _compose_master_if_ready(
        self,
        state: PixelPortraitAuthoringState,
    ) -> PixelPortraitAuthoringState:
        active_families = self._active_family_composites(state)
        if len(active_families) != len(self._plan.families):
            return state
        if any(
            composite.scope is CompositeScope.PACKAGE_MASTER
            and composite.status in {CompositeStatus.PENDING_REVIEW, CompositeStatus.APPROVED}
            and self._is_current_package_master(state, composite)
            for composite in state.composites
        ):
            return state
        composite = self._workspace.compose(
            state=state,
            scope=CompositeScope.PACKAGE_MASTER,
            family_id=None,
            created_at=self._clock(),
        )
        if (
            composite.composite_id in {item.composite_id for item in state.composites}
            or composite.status is not CompositeStatus.PENDING_REVIEW
            or composite.scope is not CompositeScope.PACKAGE_MASTER
            or not self._is_current_package_master(state, composite)
        ):
            raise PixelPortraitWorkflowError(
                "invalid_composite",
                "The workspace returned invalid package-master evidence.",
            )
        payload = state.model_dump(mode="python")
        payload["composites"] = (*state.composites, composite)
        return PixelPortraitAuthoringState.model_validate(payload)

    def _ordered_active_family_ids(
        self,
        state: PixelPortraitAuthoringState,
        *,
        replacement: CompositeReviewSheet | None = None,
    ) -> tuple[str, ...]:
        composites = {item.composite_id: item for item in state.composites}
        active_by_family = {
            composite.family_id: composite.composite_id
            for composite_id in state.active_composite_ids
            if (composite := composites[composite_id]).scope is CompositeScope.FAMILY
        }
        if replacement is not None:
            if replacement.scope is not CompositeScope.FAMILY or replacement.family_id is None:
                raise PixelPortraitWorkflowError(
                    "invalid_composite",
                    "Only a family composite can replace an active family sheet.",
                )
            active_by_family[replacement.family_id] = replacement.composite_id
        return tuple(
            active_by_family[family.family_id]
            for family in self._plan.families
            if family.family_id in active_by_family
        )

    def _active_family_composites(
        self,
        state: PixelPortraitAuthoringState,
    ) -> tuple[CompositeReviewSheet, ...]:
        composites = {item.composite_id: item for item in state.composites}
        ordered_ids = self._ordered_active_family_ids(state)
        active = tuple(composites[composite_id] for composite_id in ordered_ids)
        if len(active) != len(self._plan.families):
            return ()
        if any(
            composite.status is not CompositeStatus.APPROVED
            or composite.family_id != family.family_id
            or not self._is_current_family_composite(state, composite)
            for family, composite in zip(self._plan.families, active, strict=True)
        ):
            return ()
        return active

    def _is_current_family_composite(
        self,
        state: PixelPortraitAuthoringState,
        composite: CompositeReviewSheet,
    ) -> bool:
        if composite.scope is not CompositeScope.FAMILY or composite.family_id is None:
            return False
        try:
            family = self._plan.family(composite.family_id)
        except KeyError:
            return False
        if composite.member_ids != family.panel_ids:
            return False
        hashes: list[str] = []
        for panel_id in family.panel_ids:
            panel = state.panels[panel_id]
            if panel.progress is not PanelProgress.APPROVED or panel.approved_candidate_id is None:
                return False
            candidate = next(
                (
                    item
                    for item in panel.candidates
                    if item.candidate_id == panel.approved_candidate_id
                ),
                None,
            )
            if candidate is None or candidate.status is not CandidateStatus.APPROVED:
                return False
            hashes.append(candidate.normalized_panel.sha256)
        return composite.member_hashes == tuple(hashes)

    def _is_current_package_master(
        self,
        state: PixelPortraitAuthoringState,
        composite: CompositeReviewSheet,
    ) -> bool:
        if composite.scope is not CompositeScope.PACKAGE_MASTER:
            return False
        families = self._active_family_composites(state)
        if len(families) != len(self._plan.families):
            return False
        return composite.member_ids == tuple(
            family.composite_id for family in families
        ) and composite.member_hashes == tuple(family.artifact.sha256 for family in families)

    def _recover_interrupted_attempts(
        self,
        state: PixelPortraitAuthoringState,
    ) -> PixelPortraitAuthoringState:
        changed = False
        for panel_definition in self._plan.panels:
            panel = state.panels[panel_definition.panel_id]
            if panel.progress is not PanelProgress.GENERATING:
                continue
            interrupted = panel.attempts[-1]
            failed = GenerationAttempt(
                attempt_id=interrupted.attempt_id,
                task_id=interrupted.task_id,
                attempt=interrupted.attempt,
                status=GenerationAttemptStatus.FAILED,
                started_at=interrupted.started_at,
                completed_at=self._clock(),
                error_code="interrupted_attempt",
                error_message=("A prior provider attempt ended before recording an outcome."),
            )
            progress = (
                PanelProgress.EXHAUSTED
                if len(panel.attempts) >= _MAX_ATTEMPTS
                else PanelProgress.RETRY_READY
            )
            recovered = PixelPanelState(
                panel_id=panel.panel_id,
                progress=progress,
                attempts=(*panel.attempts[:-1], failed),
                candidates=panel.candidates,
                decisions=panel.decisions,
            )
            state = self._with_panel(state, recovered)
            changed = True
        if changed:
            try:
                self._workspace.save_state(state)
            except AuthoringWorkspaceError as exc:
                raise PixelPortraitWorkflowError(exc.code, str(exc)) from exc
            except Exception as exc:
                raise self._unexpected_failure(exc) from exc
        return state

    def _next_panel(
        self,
        state: PixelPortraitAuthoringState,
    ) -> tuple[PixelPanelDefinition, PixelPanelState]:
        for panel_definition in self._plan.panels:
            panel = state.panels[panel_definition.panel_id]
            if panel.progress is PanelProgress.APPROVED:
                continue
            if panel.progress is PanelProgress.CANDIDATE_READY:
                raise PixelPortraitWorkflowError(
                    "pending_review",
                    f"Panel {panel.panel_id} has a candidate awaiting human review.",
                )
            if panel.progress is PanelProgress.EXHAUSTED:
                raise PixelPortraitWorkflowError(
                    "attempts_exhausted",
                    f"Panel {panel.panel_id} exhausted its three attempts.",
                )
            if any(
                state.panels[dependency].progress is not PanelProgress.APPROVED
                for dependency in panel_definition.dependencies
            ):
                raise PixelPortraitWorkflowError(
                    "dependency_not_approved",
                    f"Panel {panel.panel_id} requires approved predecessor panels.",
                )
            if panel.panel_id != NEUTRAL_PANEL_ID and state.identity_lock is None:
                raise PixelPortraitWorkflowError(
                    "identity_lock_required",
                    "Dependent panels require an approved neutral identity lock.",
                )
            return panel_definition, panel
        raise PixelPortraitWorkflowError(
            "authoring_complete",
            "All pixel portrait panels are approved.",
        )

    def _input_artifacts(
        self,
        state: PixelPortraitAuthoringState,
        panel: PixelPanelDefinition,
    ) -> tuple[ArtifactEvidence, ...]:
        if panel.panel_id == NEUTRAL_PANEL_ID:
            return (
                *self._ordered_base_sources(state),
                self._technical_artifact(state, panel),
            )

        character_sheet = self._base_source(
            state,
            "juana-avatar-character-sheet.png",
        )
        neutral = self._approved_neutral(state).normalized_panel
        if panel.family_id == "presence-states":
            if panel.base_source_role is None:
                raise PixelPortraitWorkflowError(
                    "source_evidence_missing",
                    f"Panel {panel.panel_id} has no matching base-state role.",
                )
            return (
                character_sheet,
                self._base_source(
                    state,
                    f"juana-avatar-{panel.base_source_role}.png",
                ),
                neutral,
            )
        return (
            character_sheet,
            neutral,
            self._technical_artifact(state, panel),
        )

    def _ordered_base_sources(
        self,
        state: PixelPortraitAuthoringState,
    ) -> tuple[ArtifactEvidence, ...]:
        return tuple(self._base_source(state, filename) for filename in BASE_SOURCE_FILENAMES)

    @staticmethod
    def _canonical_base_paths() -> tuple[str, ...]:
        return tuple(f"{_BASE_SOURCE_PREFIX}{filename}" for filename in BASE_SOURCE_FILENAMES)

    def _base_source(
        self,
        state: PixelPortraitAuthoringState,
        filename: str,
    ) -> ArtifactEvidence:
        expected_path = f"{_BASE_SOURCE_PREFIX}{filename}"
        matches = tuple(
            source for source in state.revision.base_sources if source.path == expected_path
        )
        if len(matches) != 1:
            raise PixelPortraitWorkflowError(
                "source_evidence_missing",
                f"Locked base source evidence is missing for {filename}.",
            )
        return matches[0]

    def _base_provenance_by_path(
        self,
        state: PixelPortraitAuthoringState,
    ) -> dict[str, ProvenanceRecord]:
        expected_artifacts = {source.path: source for source in self._ordered_base_sources(state)}
        records: dict[str, ProvenanceRecord] = {}
        for record in state.provenance:
            expected = expected_artifacts.get(record.artifact.path)
            if expected is None:
                continue
            if (
                record.source_class is not SourceClass.CREATIVE_CANON
                or record.artifact != expected
                or record.rights_basis_provenance_id is not None
                or record.artifact.path in records
            ):
                raise PixelPortraitWorkflowError(
                    "base_provenance_invalid",
                    "Every base-set source requires one matching direct provenance record.",
                )
            records[record.artifact.path] = record
        if set(records) != set(expected_artifacts):
            raise PixelPortraitWorkflowError(
                "base_provenance_missing",
                "Every base-set source requires one matching direct provenance record.",
            )
        return records

    def _technical_artifact(
        self,
        state: PixelPortraitAuthoringState,
        panel: PixelPanelDefinition,
    ) -> ArtifactEvidence:
        if panel.technical_source_path is None:
            raise PixelPortraitWorkflowError(
                "source_evidence_missing",
                f"Panel {panel.panel_id} has no technical source path.",
            )
        expected_path = f"{_TECHNICAL_SOURCE_PREFIX}{panel.technical_source_path}"
        matches = tuple(
            record.artifact
            for record in state.provenance
            if record.source_class is SourceClass.TECHNICAL_REFERENCE
            and record.artifact.path == expected_path
        )
        if len(matches) != 1:
            raise PixelPortraitWorkflowError(
                "source_evidence_missing",
                f"Locked technical evidence is missing for panel {panel.panel_id}.",
            )
        sealed_digest = state.revision.technical_source_seal.file_hashes.get(
            panel.technical_source_path
        )
        if sealed_digest is None or matches[0].sha256 != sealed_digest:
            raise PixelPortraitWorkflowError(
                "source_evidence_invalid",
                f"Locked technical evidence disagrees with the V1 seal for panel {panel.panel_id}.",
            )
        return matches[0]

    @staticmethod
    def _approved_neutral(
        state: PixelPortraitAuthoringState,
    ) -> PixelPanelCandidate:
        neutral = state.panels[NEUTRAL_PANEL_ID]
        if (
            state.identity_lock is None
            or neutral.progress is not PanelProgress.APPROVED
            or neutral.approved_candidate_id is None
        ):
            raise PixelPortraitWorkflowError(
                "identity_lock_required",
                "Dependent panels require an approved neutral identity lock.",
            )
        for candidate in neutral.candidates:
            if candidate.candidate_id == neutral.approved_candidate_id:
                return candidate
        raise PixelPortraitWorkflowError(
            "approved_neutral_missing",
            "The approved neutral candidate evidence is missing.",
        )

    def _record_failure(
        self,
        state: PixelPortraitAuthoringState,
        panel: PixelPanelState,
        attempt: GenerationAttempt,
        *,
        code: str,
        message: str,
    ) -> None:
        failed = GenerationAttempt(
            attempt_id=attempt.attempt_id,
            task_id=attempt.task_id,
            attempt=attempt.attempt,
            status=GenerationAttemptStatus.FAILED,
            started_at=attempt.started_at,
            completed_at=self._clock(),
            error_code=code,
            error_message=message,
        )
        progress = (
            PanelProgress.EXHAUSTED
            if len(panel.attempts) >= _MAX_ATTEMPTS
            else PanelProgress.RETRY_READY
        )
        failed_panel = PixelPanelState(
            panel_id=panel.panel_id,
            progress=progress,
            attempts=(*panel.attempts[:-1], failed),
            candidates=panel.candidates,
            decisions=panel.decisions,
        )
        self._workspace.save_state(self._with_panel(state, failed_panel))

    def _with_panel(
        self,
        state: PixelPortraitAuthoringState,
        panel: PixelPanelState,
    ) -> PixelPortraitAuthoringState:
        expected_panels = {definition.panel_id for definition in self._plan.panels}
        if panel.panel_id not in expected_panels or panel.panel_id not in state.panels:
            raise PixelPortraitWorkflowError(
                "plan_mismatch",
                "Panel mutation must target one canonical persisted panel key.",
            )
        panels = dict(state.panels)
        panels[panel.panel_id] = panel
        return state.model_copy(update={"panels": panels})

    def _validate_state_plan(self, state: PixelPortraitAuthoringState) -> None:
        expected_panels = {panel.panel_id for panel in self._plan.panels}
        if (
            state.plan_id != self._plan.plan_id
            or state.plan_version != self._plan.version
            or set(state.panels) != expected_panels
            or any(key != panel.panel_id for key, panel in state.panels.items())
        ):
            raise PixelPortraitWorkflowError(
                "plan_mismatch",
                "Persisted state does not match the fixed pixel portrait plan.",
            )

    @staticmethod
    def _unexpected_failure(_exc: Exception) -> PixelPortraitWorkflowError:
        # Keep the cause for local diagnostics without exposing its text to state or CLI.
        return PixelPortraitWorkflowError(
            "unexpected_failure",
            "An unexpected local failure interrupted the pixel portrait workflow.",
        )
