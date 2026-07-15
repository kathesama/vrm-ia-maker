"""Production package for deterministic VRM avatar builds."""

from vrm_ia_maker.contracts import (
    AssemblyManifest,
    AssetPackManifest,
    BaseModelAdapterManifest,
    CompiledAssemblySpec,
)
from vrm_ia_maker.manifest_loader import (
    ManifestIOError,
    ManifestValidationError,
    load_assembly_manifest,
    load_asset_pack_manifest,
    load_base_model_adapter_manifest,
    load_compiled_assembly_spec,
)

__all__ = [
    "AssemblyManifest",
    "AssetPackManifest",
    "BaseModelAdapterManifest",
    "CompiledAssemblySpec",
    "ManifestIOError",
    "ManifestValidationError",
    "load_assembly_manifest",
    "load_asset_pack_manifest",
    "load_base_model_adapter_manifest",
    "load_compiled_assembly_spec",
]
