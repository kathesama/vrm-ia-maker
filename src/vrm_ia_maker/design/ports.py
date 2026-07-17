"""Vendor-neutral ports for bounded character-reference authoring."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Annotated, Protocol

from pydantic import Field

from vrm_ia_maker.design.contracts import (
    ArtifactEvidence,
    AuthoringState,
    CandidateRecord,
    NonEmptyString,
    RightsMetadata,
    SealEvidence,
    StrictDesignModel,
)
from vrm_ia_maker.design.plan import AuthoringTaskDefinition


class GenerationRequest(StrictDesignModel):
    """Plain request passed from the application service to an image adapter."""

    task_id: NonEmptyString
    prompt_id: NonEmptyString
    prompt_version: NonEmptyString
    prompt: NonEmptyString
    input_paths: Annotated[tuple[Path, ...], Field(min_length=1)]
    width: Annotated[int, Field(gt=0)]
    height: Annotated[int, Field(gt=0)]


class GeneratedImage(StrictDesignModel):
    """Provider-neutral image bytes returned by an image adapter."""

    data: Annotated[bytes, Field(min_length=1)]
    provider: NonEmptyString
    model: NonEmptyString


class WorkspaceInitialization(StrictDesignModel):
    """Plain inputs required to create one new authoring workspace."""

    master_source: Path
    package_id: NonEmptyString
    character_id: NonEmptyString
    display_name: NonEmptyString
    revision: NonEmptyString
    height_meters: Annotated[float, Field(gt=0.0)] | None = None
    authoritative_source: NonEmptyString
    rights: RightsMetadata | None = None


class ImageGenerationError(RuntimeError):
    """Sanitized image-generation failure safe for persistence and CLI output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ImageGenerationConfigurationError(ImageGenerationError):
    """Deterministic local configuration failure for an image adapter."""


class AuthoringWorkspaceError(RuntimeError):
    """Sanitized workspace failure exposed through the application port."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


class ReferenceImageGeneratorPort(Protocol):
    """Generate exactly one image for one explicit application invocation."""

    def generate(self, request: GenerationRequest) -> GeneratedImage:
        """Return one generated image or raise a sanitized generation error."""
        ...


class AuthoringWorkspacePort(Protocol):
    """Persist and recover authoring state without exposing storage details."""

    def initialize(self, command: WorkspaceInitialization) -> AuthoringState:
        """Create a new no-clobber workspace."""
        ...

    def load_state(self) -> AuthoringState:
        """Load the current valid authoring state."""
        ...

    def save_state(self, state: AuthoringState) -> None:
        """Atomically replace the current valid authoring state."""
        ...

    def resolve_artifact(self, relative_path: str) -> Path:
        """Resolve a contained workspace artifact path."""
        ...

    def stage_candidate(
        self,
        *,
        task: AuthoringTaskDefinition,
        attempt: int,
        generated: GeneratedImage,
        input_artifacts: tuple[ArtifactEvidence, ...],
        created_at: datetime,
    ) -> CandidateRecord:
        """Validate and stage one generated sheet and its previews."""
        ...

    def exclusive(self) -> AbstractContextManager[None]:
        """Hold the workspace writer lock across one mutation."""
        ...

    def seal(
        self,
        state: AuthoringState,
        destination: Path,
        sealed_at: datetime,
    ) -> SealEvidence:
        """Publish a validated package to a new destination."""
        ...

    def validate_artifacts(self, state: AuthoringState) -> None:
        """Verify persisted artifact bytes against state evidence."""
        ...
