"""Production Forge application boundary for Blender finalization."""

from vrm_ia_maker.forge.finalize import (
    ForgeFinalizationResult,
    finalize_compiled_assembly,
)
from vrm_ia_maker.forge.ports import (
    BlenderExecutionConfig,
    BlenderExecutionPort,
    BlenderExecutionResult,
)

__all__ = [
    "BlenderExecutionConfig",
    "BlenderExecutionPort",
    "BlenderExecutionResult",
    "ForgeFinalizationResult",
    "finalize_compiled_assembly",
]
