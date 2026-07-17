"""Application use case for the fixed, human-gated authoring workflow."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from vrm_ia_maker.design.contracts import (
    ApprovalDecision,
    ApprovalRecord,
    ArtifactEvidence,
    AuthoringState,
    CandidateRecord,
    CandidateStatus,
    GenerationAttempt,
    GenerationAttemptStatus,
    ProvenanceRecord,
    RightsMetadata,
    SealEvidence,
    SourceClass,
    StrictDesignModel,
    TaskProgress,
    TaskState,
)
from vrm_ia_maker.design.plan import (
    TALKING_BUST_PLAN,
    AuthoringPlanDefinition,
    AuthoringTaskDefinition,
)
from vrm_ia_maker.design.ports import (
    AuthoringWorkspaceError,
    AuthoringWorkspacePort,
    GenerationRequest,
    ImageGenerationError,
    ReferenceImageGeneratorPort,
    WorkspaceInitialization,
)


class AuthoringWorkflowError(RuntimeError):
    """Stable deterministic application failure suitable for CLI translation."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class AuthoringRunResult(StrictDesignModel):
    """Successful outcome of exactly one explicit generation invocation."""

    task_id: str
    attempt: int
    candidate: CandidateRecord


class AuthoringValidationResult(StrictDesignModel):
    """Offline integrity and seal-readiness result for one workspace."""

    valid: bool
    sealable: bool
    incomplete_tasks: tuple[str, ...]
    blocking_gaps: tuple[str, ...]
    task_progress: dict[str, TaskProgress]


class AuthoringService:
    """Coordinate one persisted task transition per explicit invocation."""

    def __init__(
        self,
        *,
        workspace: AuthoringWorkspacePort,
        generator: ReferenceImageGeneratorPort | None = None,
        plan: AuthoringPlanDefinition = TALKING_BUST_PLAN,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._workspace = workspace
        self._generator = generator
        self._plan = plan
        self._clock = clock or (lambda: datetime.now(UTC))

    def initialize(self, command: WorkspaceInitialization) -> AuthoringState:
        """Create a new bounded authoring workspace."""
        return self._workspace.initialize(command)

    def status(self) -> AuthoringState:
        """Return validated persisted workflow state without side effects."""
        state = self._workspace.load_state()
        self._validate_state_plan(state)
        return state

    def set_rights(
        self,
        rights: RightsMetadata,
        *,
        authoritative_source: str,
    ) -> ProvenanceRecord:
        """Complete immutable master-source rights for an existing workspace."""
        normalized_source = authoritative_source.strip()
        if not normalized_source:
            raise AuthoringWorkflowError(
                "invalid_authoritative_source",
                "Master-source provenance must not be empty.",
            )
        if not rights.is_complete:
            raise AuthoringWorkflowError(
                "incomplete_rights",
                "Every master-source rights field is required.",
            )
        with self._workspace.exclusive():
            state = self._workspace.load_state()
            self._validate_state_plan(state)
            master = next(
                (
                    record
                    for record in state.provenance
                    if record.provenance_id == "master-reference"
                ),
                None,
            )
            if master is None:
                raise AuthoringWorkflowError(
                    "master_provenance_missing",
                    "The authoring workspace has no master provenance record.",
                )
            if master.rights is not None and master.rights.is_complete:
                raise AuthoringWorkflowError(
                    "rights_already_complete",
                    "Complete master-source rights are immutable for this revision.",
                )
            updated_master = master.model_copy(
                update={
                    "authoritative_source": normalized_source,
                    "rights": rights,
                }
            )
            provenance = tuple(
                updated_master if record.provenance_id == "master-reference" else record
                for record in state.provenance
            )
            gaps = tuple(
                gap for gap in state.gaps if gap.gap_id != "source-rights-incomplete"
            )
            updated_state = state.model_copy(
                update={"provenance": provenance, "gaps": gaps}
            )
            self._workspace.save_state(updated_state)
            return updated_master

    def validate(self) -> AuthoringValidationResult:
        """Validate state and artifact integrity without invoking a provider."""
        with self._workspace.exclusive():
            state = self._workspace.load_state()
            self._validate_state_plan(state)
            try:
                self._workspace.validate_artifacts(state)
            except AuthoringWorkspaceError as exc:
                raise AuthoringWorkflowError(exc.code, str(exc)) from exc
            incomplete = tuple(
                task_definition.task_id
                for task_definition in self._plan.tasks
                if state.tasks[task_definition.task_id].progress is not TaskProgress.APPROVED
            )
            blocking = tuple(
                gap.gap_id for gap in state.gaps if gap.blocks_visual_seal
            )
            return AuthoringValidationResult(
                valid=True,
                sealable=not incomplete and not blocking,
                incomplete_tasks=incomplete,
                blocking_gaps=blocking,
                task_progress={
                    task_id: task.progress for task_id, task in state.tasks.items()
                },
            )

    def approve(
        self,
        *,
        task_id: str,
        candidate_id: str,
        approver: str,
        notes: str,
    ) -> ApprovalRecord:
        """Approve one pending candidate after reviewing its sheet and previews."""
        return self._decide(
            task_id=task_id,
            candidate_id=candidate_id,
            decision=ApprovalDecision.APPROVE,
            approver=approver,
            notes=notes,
        )

    def reject(
        self,
        *,
        task_id: str,
        candidate_id: str,
        approver: str,
        notes: str,
    ) -> ApprovalRecord:
        """Reject one pending candidate while preserving all attempt evidence."""
        return self._decide(
            task_id=task_id,
            candidate_id=candidate_id,
            decision=ApprovalDecision.REJECT,
            approver=approver,
            notes=notes,
        )

    def supersede(
        self,
        *,
        task_id: str,
        candidate_id: str,
        approver: str,
        notes: str,
    ) -> ApprovalRecord:
        """Reopen an approved task while preserving its review history."""
        with self._workspace.exclusive():
            state = self._workspace.load_state()
            self._validate_state_plan(state)
            task = state.tasks.get(task_id)
            if task is None:
                raise AuthoringWorkflowError("unknown_task", f"Unknown authoring task: {task_id}")
            candidate = next(
                (
                    item
                    for item in task.candidates
                    if item.candidate_id == candidate_id
                ),
                None,
            )
            if candidate is None:
                raise AuthoringWorkflowError(
                    "unknown_candidate",
                    f"Candidate {candidate_id} does not belong to task {task_id}.",
                )
            if (
                task.progress is not TaskProgress.APPROVED
                or task.approved_candidate_id != candidate_id
                or candidate.status is not CandidateStatus.APPROVED
            ):
                raise AuthoringWorkflowError(
                    "candidate_not_approved",
                    f"Candidate {candidate_id} is not the active approval for task {task_id}.",
                )

            unresolved_dependents = tuple(
                dependent_id
                for dependent_id in self._dependent_task_ids(task_id)
                if state.tasks[dependent_id].progress
                not in {TaskProgress.PENDING, TaskProgress.RETRY_READY}
            )
            if unresolved_dependents:
                raise AuthoringWorkflowError(
                    "dependent_review_required",
                    "Resolve dependent task candidates before superseding "
                    f"{task_id}: {', '.join(unresolved_dependents)}",
                )

            reviewed = (
                candidate.sheet.path,
                *(preview.path for preview in candidate.previews),
            )
            record = ApprovalRecord(
                approval_id=f"supersede-{candidate_id}",
                task_id=task_id,
                candidate_id=candidate_id,
                decision=ApprovalDecision.SUPERSEDE,
                approver=approver,
                decided_at=self._clock(),
                reviewed_artifacts=reviewed,
                notes=notes,
            )
            superseded_candidate = candidate.model_copy(
                update={"status": CandidateStatus.SUPERSEDED}
            )
            candidates = tuple(
                superseded_candidate if item.candidate_id == candidate_id else item
                for item in task.candidates
            )
            progress = (
                TaskProgress.EXHAUSTED
                if len(task.attempts) >= 3
                else TaskProgress.RETRY_READY
            )
            superseded_task = TaskState(
                task_id=task.task_id,
                progress=progress,
                attempts=task.attempts,
                candidates=candidates,
                decisions=(*task.decisions, record),
            )
            self._workspace.save_state(self._with_task(state, superseded_task))
            return record

    def seal(self, destination: Path) -> SealEvidence:
        """Seal all approved visual references into a new validated package."""
        with self._workspace.exclusive():
            state = self._workspace.load_state()
            self._validate_state_plan(state)
            incomplete = [
                task.task_id
                for task in state.tasks.values()
                if task.progress is not TaskProgress.APPROVED
            ]
            if incomplete:
                raise AuthoringWorkflowError(
                    "incomplete_authoring",
                    "All visual authoring tasks must be approved before sealing: "
                    + ", ".join(incomplete),
                )
            blocking = [gap.gap_id for gap in state.gaps if gap.blocks_visual_seal]
            if blocking:
                raise AuthoringWorkflowError(
                    "blocking_gap",
                    "Visual package sealing is blocked by: " + ", ".join(blocking),
                )
            try:
                return self._workspace.seal(state, Path(destination), self._clock())
            except AuthoringWorkspaceError as exc:
                raise AuthoringWorkflowError(exc.code, str(exc)) from exc

    def run(self) -> AuthoringRunResult:
        """Issue at most one provider request for the next deterministic task."""
        if self._generator is None:
            raise AuthoringWorkflowError(
                "generator_not_configured",
                "No reference image generator is configured.",
            )
        with self._workspace.exclusive():
            state = self._workspace.load_state()
            self._validate_state_plan(state)
            state = self._recover_interrupted_attempt(state=state)
            task_definition, task_state = self._next_task(state)
            attempt_number = len(task_state.attempts) + 1
            if attempt_number > task_definition.max_attempts:
                raise AuthoringWorkflowError(
                    "attempts_exhausted",
                    f"Task {task_definition.task_id} exhausted its three attempts.",
                )

            started_at = self._clock()
            in_progress = GenerationAttempt(
                attempt_id=f"{task_definition.task_id}-attempt-{attempt_number}",
                task_id=task_definition.task_id,
                attempt=attempt_number,
                status=GenerationAttemptStatus.IN_PROGRESS,
                started_at=started_at,
            )
            generating_task = TaskState(
                task_id=task_state.task_id,
                progress=TaskProgress.GENERATING,
                attempts=(*task_state.attempts, in_progress),
                candidates=task_state.candidates,
                decisions=task_state.decisions,
            )
            state = self._with_task(state, generating_task)
            self._workspace.save_state(state)

            input_artifacts = self._approved_inputs(state, task_definition.dependencies)
            request = GenerationRequest(
                task_id=task_definition.task_id,
                prompt_id=task_definition.prompt_id,
                prompt_version=task_definition.prompt_version,
                prompt=task_definition.prompt,
                input_paths=tuple(
                    self._workspace.resolve_artifact(artifact.path)
                    for artifact in input_artifacts
                ),
                width=task_definition.width,
                height=task_definition.height,
            )
            try:
                generated = self._generator.generate(request)
            except ImageGenerationError as exc:
                self._record_failure(
                    state,
                    generating_task,
                    in_progress,
                    code=exc.code,
                    message=str(exc),
                )
                raise AuthoringWorkflowError(exc.code, str(exc)) from exc

            try:
                candidate = self._workspace.stage_candidate(
                    task=task_definition,
                    attempt=attempt_number,
                    generated=generated,
                    input_artifacts=input_artifacts,
                    created_at=self._clock(),
                )
            except AuthoringWorkspaceError as exc:
                self._record_failure(
                    state,
                    generating_task,
                    in_progress,
                    code=exc.code,
                    message=str(exc),
                )
                raise AuthoringWorkflowError(exc.code, str(exc)) from exc

            completed = GenerationAttempt(
                attempt_id=in_progress.attempt_id,
                task_id=in_progress.task_id,
                attempt=in_progress.attempt,
                status=GenerationAttemptStatus.CANDIDATE_READY,
                started_at=in_progress.started_at,
                completed_at=self._clock(),
                candidate_id=candidate.candidate_id,
            )
            candidate_ready = TaskState(
                task_id=generating_task.task_id,
                progress=TaskProgress.CANDIDATE_READY,
                attempts=(*generating_task.attempts[:-1], completed),
                candidates=(*generating_task.candidates, candidate),
                decisions=generating_task.decisions,
            )
            self._workspace.save_state(self._with_task(state, candidate_ready))
            return AuthoringRunResult(
                task_id=task_definition.task_id,
                attempt=attempt_number,
                candidate=candidate,
            )

    def _recover_interrupted_attempt(self, state: AuthoringState) -> AuthoringState:
        changed = False
        for task_definition in self._plan.tasks:
            task = state.tasks[task_definition.task_id]
            if task.progress is not TaskProgress.GENERATING:
                continue
            interrupted = task.attempts[-1]
            failed = GenerationAttempt(
                attempt_id=interrupted.attempt_id,
                task_id=interrupted.task_id,
                attempt=interrupted.attempt,
                status=GenerationAttemptStatus.FAILED,
                started_at=interrupted.started_at,
                completed_at=self._clock(),
                error_code="interrupted_attempt",
                error_message="A prior provider attempt ended before recording an outcome.",
            )
            progress = (
                TaskProgress.EXHAUSTED
                if len(task.attempts) >= task_definition.max_attempts
                else TaskProgress.RETRY_READY
            )
            recovered = TaskState(
                task_id=task.task_id,
                progress=progress,
                attempts=(*task.attempts[:-1], failed),
                candidates=task.candidates,
                decisions=task.decisions,
            )
            state = self._with_task(state, recovered)
            changed = True
        if changed:
            self._workspace.save_state(state)
        return state

    def _decide(
        self,
        *,
        task_id: str,
        candidate_id: str,
        decision: ApprovalDecision,
        approver: str,
        notes: str,
    ) -> ApprovalRecord:
        with self._workspace.exclusive():
            state = self._workspace.load_state()
            self._validate_state_plan(state)
            task = state.tasks.get(task_id)
            if task is None:
                raise AuthoringWorkflowError("unknown_task", f"Unknown authoring task: {task_id}")
            candidate = next(
                (
                    item
                    for item in task.candidates
                    if item.candidate_id == candidate_id
                ),
                None,
            )
            if candidate is None:
                raise AuthoringWorkflowError(
                    "unknown_candidate",
                    f"Candidate {candidate_id} does not belong to task {task_id}.",
                )
            if candidate.status is not CandidateStatus.PENDING or any(
                item.candidate_id == candidate_id for item in task.decisions
            ):
                raise AuthoringWorkflowError(
                    "decision_conflict",
                    f"Candidate {candidate_id} already has a human decision.",
                )
            if task.progress is not TaskProgress.CANDIDATE_READY:
                raise AuthoringWorkflowError(
                    "candidate_not_pending",
                    f"Task {task_id} has no candidate awaiting review.",
                )
            reviewed = (
                candidate.sheet.path,
                *(preview.path for preview in candidate.previews),
            )
            record = ApprovalRecord(
                approval_id=f"{decision.value}-{candidate_id}",
                task_id=task_id,
                candidate_id=candidate_id,
                decision=decision,
                approver=approver,
                decided_at=self._clock(),
                reviewed_artifacts=reviewed,
                notes=notes,
            )
            status = (
                CandidateStatus.APPROVED
                if decision is ApprovalDecision.APPROVE
                else CandidateStatus.REJECTED
            )
            decided_candidate = candidate.model_copy(update={"status": status})
            candidates = tuple(
                decided_candidate if item.candidate_id == candidate_id else item
                for item in task.candidates
            )
            progress = (
                TaskProgress.APPROVED
                if decision is ApprovalDecision.APPROVE
                else TaskProgress.EXHAUSTED
                if len(task.attempts) >= 3
                else TaskProgress.RETRY_READY
            )
            decided_task = TaskState(
                task_id=task.task_id,
                progress=progress,
                attempts=task.attempts,
                candidates=candidates,
                decisions=(*task.decisions, record),
                approved_candidate_id=(
                    candidate_id if decision is ApprovalDecision.APPROVE else None
                ),
            )
            state = self._with_task(state, decided_task)
            if decision is ApprovalDecision.APPROVE:
                provenance = ProvenanceRecord(
                    provenance_id=f"candidate-{candidate_id}",
                    source_class=SourceClass.TECHNICAL_REFERENCE,
                    artifact=decided_candidate.sheet,
                    authoritative_source=(
                        "Human-approved generated technical reference candidate."
                    ),
                    rights_basis_provenance_id="master-reference",
                    derived_from_sha256=tuple(
                        artifact.sha256 for artifact in decided_candidate.input_artifacts
                    ),
                    provider=decided_candidate.provider,
                    model=decided_candidate.model,
                    prompt_id=decided_candidate.prompt_id,
                    prompt_version=decided_candidate.prompt_version,
                )
                state = state.model_copy(
                    update={"provenance": (*state.provenance, provenance)}
                )
            self._workspace.save_state(state)
            return record

    def _next_task(
        self,
        state: AuthoringState,
    ) -> tuple[AuthoringTaskDefinition, TaskState]:
        for task_definition in self._plan.tasks:
            task = state.tasks[task_definition.task_id]
            if task.progress is TaskProgress.APPROVED:
                continue
            if task.progress is TaskProgress.CANDIDATE_READY:
                raise AuthoringWorkflowError(
                    "pending_review",
                    f"Task {task.task_id} has a candidate awaiting human review.",
                )
            if task.progress is TaskProgress.EXHAUSTED:
                raise AuthoringWorkflowError(
                    "attempts_exhausted",
                    f"Task {task.task_id} exhausted its three attempts.",
                )
            if any(
                state.tasks[dependency].progress is not TaskProgress.APPROVED
                for dependency in task_definition.dependencies
            ):
                raise AuthoringWorkflowError(
                    "dependency_not_approved",
                    f"Task {task.task_id} requires approved predecessor tasks.",
                )
            return task_definition, task
        raise AuthoringWorkflowError(
            "authoring_complete",
            "All talking-bust reference tasks are approved.",
        )

    def _dependent_task_ids(self, task_id: str) -> tuple[str, ...]:
        dependent_ids: set[str] = set()
        for task_definition in self._plan.tasks:
            if any(
                dependency == task_id or dependency in dependent_ids
                for dependency in task_definition.dependencies
            ):
                dependent_ids.add(task_definition.task_id)
        return tuple(
            task_definition.task_id
            for task_definition in self._plan.tasks
            if task_definition.task_id in dependent_ids
        )

    def _approved_inputs(
        self,
        state: AuthoringState,
        dependencies: tuple[str, ...],
    ) -> tuple[ArtifactEvidence, ...]:
        inputs = [state.revision.master_reference]
        for dependency in dependencies:
            task = state.tasks[dependency]
            candidate = next(
                candidate
                for candidate in task.candidates
                if candidate.candidate_id == task.approved_candidate_id
            )
            inputs.append(candidate.sheet)
        return tuple(inputs)

    def _record_failure(
        self,
        state: AuthoringState,
        task: TaskState,
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
        progress = TaskProgress.EXHAUSTED if len(task.attempts) >= 3 else TaskProgress.RETRY_READY
        failed_task = TaskState(
            task_id=task.task_id,
            progress=progress,
            attempts=(*task.attempts[:-1], failed),
            candidates=task.candidates,
            decisions=task.decisions,
        )
        self._workspace.save_state(self._with_task(state, failed_task))

    @staticmethod
    def _with_task(state: AuthoringState, task: TaskState) -> AuthoringState:
        tasks = dict(state.tasks)
        tasks[task.task_id] = task
        return state.model_copy(update={"tasks": tasks})

    def _validate_state_plan(self, state: AuthoringState) -> None:
        expected_tasks = {task.task_id for task in self._plan.tasks}
        if (
            state.plan_id != self._plan.plan_id
            or state.plan_version != self._plan.plan_version
            or set(state.tasks) != expected_tasks
        ):
            raise AuthoringWorkflowError(
                "plan_mismatch",
                "Persisted authoring state does not match the fixed talking-bust plan.",
            )
