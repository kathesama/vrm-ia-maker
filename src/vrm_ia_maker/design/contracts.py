"""Strict contracts for bounded character-reference authoring."""

from __future__ import annotations

import re
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    model_validator,
)

NonEmptyString = Annotated[str, Field(min_length=1)]
SHA256 = Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
PositiveAttempt = Annotated[int, Field(ge=1, le=3)]
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def _validate_package_relative_path(value: str) -> str:
    parts = value.split("/")
    if (
        not value
        or "\x00" in value
        or "\\" in value
        or _WINDOWS_DRIVE_PREFIX.match(value)
        or PurePosixPath(value).is_absolute()
        or any(part in {"", ".", ".."} for part in parts)
        or str(PurePosixPath(value)) != value
    ):
        raise ValueError("Value must be a normalized POSIX package-relative path.")
    return value


PackageRelativePath = Annotated[str, AfterValidator(_validate_package_relative_path)]


class StrictDesignModel(BaseModel):
    """Base contract that rejects drift and validates assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class SourceClass(StrEnum):
    """Evidence class assigned to a CharacterDesignPackage source."""

    CREATIVE_CANON = "creative_canon"
    TECHNICAL_REFERENCE = "technical_reference"
    PRODUCTION_ASSET = "production_asset"


class CandidateStatus(StrEnum):
    """Human-review state of a successful generation candidate."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class GenerationAttemptStatus(StrEnum):
    """Persisted result of one explicit provider request."""

    IN_PROGRESS = "in_progress"
    CANDIDATE_READY = "candidate_ready"
    FAILED = "failed"


class ApprovalDecision(StrEnum):
    """Explicit human decision for a generated candidate."""

    APPROVE = "approve"
    REJECT = "reject"
    SUPERSEDE = "supersede"


class TaskProgress(StrEnum):
    """Derived progress for one fixed authoring task."""

    PENDING = "pending"
    GENERATING = "generating"
    CANDIDATE_READY = "candidate_ready"
    RETRY_READY = "retry_ready"
    APPROVED = "approved"
    EXHAUSTED = "exhausted"


class ArtifactEvidence(StrictDesignModel):
    """Integrity and raster metadata for one workspace or package artifact."""

    path: PackageRelativePath
    sha256: SHA256
    byte_length: Annotated[int, Field(gt=0)]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class CharacterDesignPackageRevision(StrictDesignModel):
    """Identity and immutable master reference for one visual package revision."""

    schema_version: Literal["1.0"] = "1.0"
    package_id: NonEmptyString
    character_id: NonEmptyString
    display_name: NonEmptyString
    revision: NonEmptyString
    master_reference: ArtifactEvidence
    height_meters: Annotated[float, Field(gt=0.0)] | None = None


class RightsMetadata(StrictDesignModel):
    """Source rights data that may remain incomplete until sealing."""

    author: NonEmptyString | None = None
    rights_holder: NonEmptyString | None = None
    license: NonEmptyString | None = None
    commercial_use: StrictBool | None = None
    modification_allowed: StrictBool | None = None
    redistribution_allowed: StrictBool | None = None
    attribution: NonEmptyString | None = None

    @property
    def is_complete(self) -> bool:
        """Return whether every legal field needed for sealing is present."""
        return all(
            value is not None
            for value in (
                self.author,
                self.rights_holder,
                self.license,
                self.commercial_use,
                self.modification_allowed,
                self.redistribution_allowed,
                self.attribution,
            )
        )


class ProvenanceRecord(StrictDesignModel):
    """Trace one source or generated artifact to its declared origin."""

    schema_version: Literal["1.0"] = "1.0"
    provenance_id: NonEmptyString
    source_class: SourceClass
    artifact: ArtifactEvidence
    authoritative_source: NonEmptyString
    rights: RightsMetadata | None = None
    rights_basis_provenance_id: NonEmptyString | None = None
    derived_from_sha256: tuple[SHA256, ...] = ()
    provider: NonEmptyString | None = None
    model: NonEmptyString | None = None
    prompt_id: NonEmptyString | None = None
    prompt_version: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_generation_trace(self) -> ProvenanceRecord:
        """Require complete provider trace fields when any one is supplied."""
        trace = (self.provider, self.model, self.prompt_id, self.prompt_version)
        if any(value is not None for value in trace) and not all(
            value is not None for value in trace
        ):
            raise ValueError("Generated provenance requires complete provider trace fields.")
        if self.rights is not None and self.rights_basis_provenance_id is not None:
            raise ValueError("Provenance must declare direct rights or one rights basis.")
        if self.provider is not None and not self.derived_from_sha256:
            raise ValueError("Generated provenance requires at least one source digest.")
        return self


class CandidateRecord(StrictDesignModel):
    """One successful image-generation result awaiting or carrying review."""

    candidate_id: NonEmptyString
    task_id: NonEmptyString
    attempt: PositiveAttempt
    status: CandidateStatus = CandidateStatus.PENDING
    provider: NonEmptyString
    model: NonEmptyString
    prompt_id: NonEmptyString
    prompt_version: NonEmptyString
    input_artifacts: Annotated[tuple[ArtifactEvidence, ...], Field(min_length=1)]
    sheet: ArtifactEvidence
    previews: Annotated[tuple[ArtifactEvidence, ...], Field(min_length=1)]
    created_at: AwareDatetime

    @model_validator(mode="after")
    def validate_artifact_paths(self) -> CandidateRecord:
        """Reject duplicate sheet or preview paths within a candidate."""
        paths = [self.sheet.path, *(preview.path for preview in self.previews)]
        if len(paths) != len(set(paths)):
            raise ValueError("Candidate sheet and preview paths must be unique.")
        return self


class GenerationAttempt(StrictDesignModel):
    """Auditable outcome of one explicit provider request."""

    attempt_id: NonEmptyString
    task_id: NonEmptyString
    attempt: PositiveAttempt
    status: GenerationAttemptStatus
    started_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    candidate_id: NonEmptyString | None = None
    error_code: NonEmptyString | None = None
    error_message: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> GenerationAttempt:
        """Keep successful and failed attempt evidence mutually exclusive."""
        if self.status is GenerationAttemptStatus.IN_PROGRESS:
            if any(
                value is not None
                for value in (
                    self.completed_at,
                    self.candidate_id,
                    self.error_code,
                    self.error_message,
                )
            ):
                raise ValueError("In-progress attempts cannot contain outcome fields.")
            return self
        if self.completed_at is None:
            raise ValueError("Completed attempts require completed_at.")
        if self.status is GenerationAttemptStatus.FAILED:
            if self.error_code is None or self.error_message is None:
                raise ValueError("Failed attempts require error_code and error_message.")
            if self.candidate_id is not None:
                raise ValueError("Failed attempts cannot reference a candidate.")
        elif self.candidate_id is None:
            raise ValueError("Successful attempts require candidate_id.")
        elif self.error_code is not None or self.error_message is not None:
            raise ValueError("Successful attempts cannot contain error details.")
        if self.completed_at < self.started_at:
            raise ValueError("Attempt completion cannot precede its start time.")
        return self


class ApprovalRecord(StrictDesignModel):
    """Human decision covering a candidate sheet and deterministic previews."""

    approval_id: NonEmptyString
    task_id: NonEmptyString
    candidate_id: NonEmptyString
    decision: ApprovalDecision
    approver: NonEmptyString
    decided_at: AwareDatetime
    reviewed_artifacts: Annotated[tuple[PackageRelativePath, ...], Field(min_length=1)]
    notes: NonEmptyString


class TaskState(StrictDesignModel):
    """Resumable state and audit history for one fixed authoring task."""

    task_id: NonEmptyString
    progress: TaskProgress = TaskProgress.PENDING
    attempts: tuple[GenerationAttempt, ...] = ()
    candidates: tuple[CandidateRecord, ...] = ()
    decisions: tuple[ApprovalRecord, ...] = ()
    approved_candidate_id: NonEmptyString | None = None

    @model_validator(mode="after")
    def validate_history(self) -> TaskState:
        """Validate bounded attempts, references, decisions, and approval scope."""
        if len(self.attempts) > 3:
            raise ValueError("Authoring tasks allow no more than three attempts.")
        attempt_numbers = [attempt.attempt for attempt in self.attempts]
        if attempt_numbers != list(range(1, len(self.attempts) + 1)):
            raise ValueError("Task attempt numbers must be contiguous and ordered.")
        if any(attempt.task_id != self.task_id for attempt in self.attempts):
            raise ValueError("Every attempt must belong to its task state.")
        in_progress = [
            attempt
            for attempt in self.attempts
            if attempt.status is GenerationAttemptStatus.IN_PROGRESS
        ]
        if len(in_progress) > 1 or (in_progress and in_progress[0] is not self.attempts[-1]):
            raise ValueError("Only the latest task attempt can remain in progress.")

        candidates = {candidate.candidate_id: candidate for candidate in self.candidates}
        if len(candidates) != len(self.candidates):
            raise ValueError("Candidate identifiers must be unique within a task.")
        if any(candidate.task_id != self.task_id for candidate in self.candidates):
            raise ValueError("Every candidate must belong to its task state.")
        for attempt in self.attempts:
            if (
                attempt.status is GenerationAttemptStatus.CANDIDATE_READY
                and attempt.candidate_id not in candidates
            ):
                raise ValueError("Successful attempts must reference a recorded candidate.")

        decisions_by_candidate: dict[str, list[ApprovalRecord]] = {}
        for decision in self.decisions:
            if decision.task_id != self.task_id or decision.candidate_id not in candidates:
                raise ValueError("Every decision must reference a candidate in its task state.")
            candidate = candidates[decision.candidate_id]
            expected_scope = {
                candidate.sheet.path,
                *(preview.path for preview in candidate.previews),
            }
            if set(decision.reviewed_artifacts) != expected_scope:
                raise ValueError("A decision must review the sheet and every preview.")
            decisions_by_candidate.setdefault(decision.candidate_id, []).append(decision)

        for candidate in self.candidates:
            decisions = tuple(
                decision.decision
                for decision in decisions_by_candidate.get(candidate.candidate_id, [])
            )
            expected_status_by_decisions = {
                (): CandidateStatus.PENDING,
                (ApprovalDecision.APPROVE,): CandidateStatus.APPROVED,
                (ApprovalDecision.REJECT,): CandidateStatus.REJECTED,
                (
                    ApprovalDecision.APPROVE,
                    ApprovalDecision.SUPERSEDE,
                ): CandidateStatus.SUPERSEDED,
            }
            expected_status = expected_status_by_decisions.get(decisions)
            if expected_status is None:
                raise ValueError("Candidate decisions must form a valid review history.")
            if candidate.status is not expected_status:
                raise ValueError("Candidate status must match its human decision.")

        if self.progress is TaskProgress.APPROVED:
            if self.approved_candidate_id is None:
                raise ValueError("Approved tasks require approved_candidate_id.")
            approved_candidate = candidates.get(self.approved_candidate_id)
            if (
                approved_candidate is None
                or approved_candidate.status is not CandidateStatus.APPROVED
            ):
                raise ValueError("Approved tasks require a matching approved candidate.")
        elif self.approved_candidate_id is not None:
            raise ValueError("Only approved tasks can reference approved_candidate_id.")

        if self.progress is TaskProgress.EXHAUSTED and len(self.attempts) != 3:
            raise ValueError("Exhausted tasks require exactly three attempts.")
        if self.progress is TaskProgress.PENDING and self.attempts:
            raise ValueError("Pending tasks cannot contain attempts.")
        if self.progress is TaskProgress.GENERATING and not in_progress:
            raise ValueError("Generating tasks require an in-progress attempt.")
        if self.progress is not TaskProgress.GENERATING and in_progress:
            raise ValueError("In-progress attempts require generating task progress.")
        if self.progress is TaskProgress.CANDIDATE_READY and not any(
            candidate.status is CandidateStatus.PENDING for candidate in self.candidates
        ):
            raise ValueError("Candidate-ready tasks require a pending candidate.")
        if self.progress is TaskProgress.RETRY_READY:
            if not self.attempts or len(self.attempts) >= 3:
                raise ValueError("Retry-ready tasks require one or two completed attempts.")
            if any(candidate.status is CandidateStatus.PENDING for candidate in self.candidates):
                raise ValueError("Retry-ready tasks cannot contain a pending candidate.")
        return self


class GapRecord(StrictDesignModel):
    """Explicit missing information without invented production facts."""

    gap_id: NonEmptyString
    area: NonEmptyString
    description: NonEmptyString
    blocks_visual_seal: StrictBool


class AuthoringState(StrictDesignModel):
    """Complete persisted state for one bounded authoring workspace."""

    schema_version: Literal["1.0"] = "1.0"
    revision: CharacterDesignPackageRevision
    plan_id: NonEmptyString
    plan_version: NonEmptyString
    tasks: dict[NonEmptyString, TaskState]
    provenance: tuple[ProvenanceRecord, ...] = ()
    gaps: tuple[GapRecord, ...] = ()

    @model_validator(mode="after")
    def validate_task_keys(self) -> AuthoringState:
        """Keep serialized dictionary keys aligned with embedded task IDs."""
        if any(key != task.task_id for key, task in self.tasks.items()):
            raise ValueError("Task dictionary keys must match embedded task identifiers.")
        if len({record.provenance_id for record in self.provenance}) != len(self.provenance):
            raise ValueError("Provenance identifiers must be unique.")
        if len({gap.gap_id for gap in self.gaps}) != len(self.gaps):
            raise ValueError("Gap identifiers must be unique.")
        return self


class SealEvidence(StrictDesignModel):
    """Integrity and approval summary written into a sealed package."""

    schema_version: Literal["1.0"] = "1.0"
    package_id: NonEmptyString
    revision: NonEmptyString
    sealed_at: AwareDatetime
    file_hashes: Annotated[dict[PackageRelativePath, SHA256], Field(min_length=1)]
    approval_ids: Annotated[tuple[NonEmptyString, ...], Field(min_length=1)]
    provenance_ids: Annotated[tuple[NonEmptyString, ...], Field(min_length=1)]
    unresolved_gap_ids: tuple[NonEmptyString, ...] = ()
