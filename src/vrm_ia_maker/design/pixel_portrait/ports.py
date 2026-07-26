"""Ports for the independent panel-first pixel portrait workflow."""

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import datetime
from pathlib import Path
from typing import Literal, Protocol

from pydantic import ConfigDict, model_validator

from ..contracts import (
    ArtifactEvidence,
    NonEmptyString,
    RightsMetadata,
    SealEvidence,
    StrictDesignModel,
)
from ..ports import GeneratedImage
from .contracts import (
    CompositeReviewSheet,
    CompositeScope,
    PixelPanelCandidate,
    PixelPortraitAuthoringState,
)
from .plan import PixelPanelDefinition

BASE_SOURCE_FILENAMES = (
    "juana-avatar-character-sheet.png",
    "juana-avatar-neutral.png",
    "juana-avatar-thinking.png",
    "juana-avatar-explaining.png",
    "juana-avatar-approval.png",
    "juana-avatar-doubt.png",
    "juana-avatar-error.png",
)


class PixelWorkspaceInitialization(StrictDesignModel):
    """Inputs required to lock a new pixel portrait authoring workspace."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    base_sources: tuple[Path, ...]
    technical_package: Path
    package_id: Literal["juana-talking-bust-v2-pixel"]
    identity: NonEmptyString
    revision: NonEmptyString
    authoritative_source: NonEmptyString
    base_rights: RightsMetadata | None = None

    @model_validator(mode="after")
    def validate_base_source_names(self) -> PixelWorkspaceInitialization:
        """Require each canonical base-set input exactly once."""
        names = tuple(path.name for path in self.base_sources)
        if (
            len(self.base_sources) != len(BASE_SOURCE_FILENAMES)
            or len(set(self.base_sources)) != len(self.base_sources)
            or set(names) != set(BASE_SOURCE_FILENAMES)
        ):
            raise ValueError("Initialization requires exactly the seven named base-set paths.")
        return self


class PixelPortraitWorkspacePort(Protocol):
    """Persist pixel portrait authoring without exposing filesystem details."""

    def initialize(
        self,
        command: PixelWorkspaceInitialization,
    ) -> PixelPortraitAuthoringState:
        """Create a new no-clobber workspace from validated source locks."""
        ...

    def load_state(self) -> PixelPortraitAuthoringState:
        """Load the current strict authoring state."""
        ...

    def save_state(self, state: PixelPortraitAuthoringState) -> None:
        """Atomically replace the current strict authoring state."""
        ...

    def resolve_artifact(self, relative_path: str) -> Path:
        """Resolve one contained workspace artifact path."""
        ...

    def stage_candidate(
        self,
        *,
        panel: PixelPanelDefinition,
        attempt: int,
        generated: GeneratedImage,
        input_artifacts: tuple[ArtifactEvidence, ...],
        created_at: datetime,
    ) -> PixelPanelCandidate:
        """Preserve and deterministically normalize one generated panel."""
        ...

    def compose(
        self,
        *,
        state: PixelPortraitAuthoringState,
        scope: CompositeScope,
        family_id: str | None,
        created_at: datetime,
    ) -> CompositeReviewSheet:
        """Compose one deterministic review sheet in a later workflow slice."""
        ...

    def seal(
        self,
        state: PixelPortraitAuthoringState,
        destination: Path,
        sealed_at: datetime,
    ) -> SealEvidence:
        """Publish a validated package in a later workflow slice."""
        ...

    def validate(self, state: PixelPortraitAuthoringState) -> None:
        """Verify every persisted artifact and source lock against evidence."""
        ...

    def exclusive(self) -> AbstractContextManager[None]:
        """Hold the exclusive workspace writer lock across one mutation."""
        ...
