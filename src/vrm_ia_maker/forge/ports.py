"""Application-facing port for bounded Blender subprocess execution."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class BlenderExecutionConfig:
    """Typed Blender execution settings accepted by the production Forge."""

    executable: Path | None = None
    timeout_seconds: float = 300.0
    platform_hints: Mapping[str, tuple[Path, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("Blender timeout_seconds must be positive.")


@dataclass(frozen=True)
class BlenderExecutionResult:
    """Infrastructure-neutral result from one Blender invocation."""

    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False


class BlenderExecutionPort(Protocol):
    """Execute one Blender script without exposing runner implementation types."""

    def execute(
        self,
        *,
        script_path: Path,
        arguments: Sequence[str],
        config: BlenderExecutionConfig,
    ) -> BlenderExecutionResult:
        """Run Blender with an argument list and bounded execution."""
        ...
