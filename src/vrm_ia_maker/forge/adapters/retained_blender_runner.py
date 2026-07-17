"""Temporary production adapter over the characterized retained Blender runner."""

from __future__ import annotations

from collections.abc import Sequence
from importlib import import_module
from pathlib import Path
from typing import Any, Protocol, cast

from vrm_ia_maker.forge.ports import (
    BlenderExecutionConfig,
    BlenderExecutionResult,
)


class _RetainedRunnerResult(Protocol):
    returncode: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool


class _RetainedRunner(Protocol):
    def __call__(
        self,
        *,
        script_path: Path,
        args: list[str],
        config: dict[str, Any],
    ) -> _RetainedRunnerResult: ...


run_blender = cast(
    _RetainedRunner,
    import_module("seidr_smidja._internal.blender_runner").run_blender,
)


class RetainedBlenderRunnerAdapter:
    """Translate the production execution port to retained subprocess mechanics."""

    def execute(
        self,
        *,
        script_path: Path,
        arguments: Sequence[str],
        config: BlenderExecutionConfig,
    ) -> BlenderExecutionResult:
        """Run one Blender script through the retained single source of policy."""
        # sdd-simplification: runner move - upgrade path: relocate after preview adopts this port.
        runner_config: dict[str, Any] = {
            "blender": {
                "timeout_seconds": config.timeout_seconds,
            }
        }
        blender_config = runner_config["blender"]
        if config.executable is not None:
            blender_config["executable"] = str(config.executable)
        if config.platform_hints:
            blender_config["platform_hints"] = {
                platform: [str(path) for path in paths]
                for platform, paths in config.platform_hints.items()
            }

        result = run_blender(
            script_path=script_path,
            args=list(arguments),
            config=runner_config,
        )
        return BlenderExecutionResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
            duration_seconds=result.duration_seconds,
            timed_out=result.timed_out,
        )
