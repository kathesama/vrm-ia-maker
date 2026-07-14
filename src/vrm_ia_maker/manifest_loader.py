"""JSON file loaders for production modular assembly manifests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, TypeVar

from pydantic import ValidationError

from vrm_ia_maker.contracts import AssemblyManifest, AssetPackManifest, CompiledAssemblySpec

ManifestT = TypeVar("ManifestT", AssetPackManifest, AssemblyManifest, CompiledAssemblySpec)


class ManifestIOError(OSError):
    """Raised when a manifest JSON file cannot be read or parsed."""


class ManifestValidationError(ValueError):
    """Raised when manifest JSON does not satisfy its production contract."""

    def __init__(self, source: Path, contract_name: str, cause: ValidationError) -> None:
        super().__init__(
            f"{contract_name} validation failed for {source} with {len(cause.errors())} error(s)."
        )
        self.source = source
        self.contract_name = contract_name


def load_asset_pack_manifest(path: Path) -> AssetPackManifest:
    """Load and validate an asset-pack manifest from a JSON file."""
    return _load_manifest(path, AssetPackManifest)


def load_assembly_manifest(path: Path) -> AssemblyManifest:
    """Load and validate an assembly manifest from a JSON file."""
    return _load_manifest(path, AssemblyManifest)


def load_compiled_assembly_spec(path: Path) -> CompiledAssemblySpec:
    """Load and validate a compiled assembly specification from a JSON file."""
    return _load_manifest(path, CompiledAssemblySpec)


def _load_manifest(path: Path, contract_type: type[ManifestT]) -> ManifestT:
    raw = _load_json_object(path)
    try:
        return contract_type.model_validate(raw)
    except ValidationError as exc:
        raise ManifestValidationError(path, contract_type.__name__, exc) from exc


def _load_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ManifestIOError(f"Manifest file not found: {path}")
    if not path.is_file():
        raise ManifestIOError(f"Manifest path is not a file: {path}")
    if path.suffix.lower() != ".json":
        raise ManifestIOError(
            f"Unsupported manifest file extension '{path.suffix}'. Use .json."
        )

    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise ManifestIOError(f"Cannot read manifest file {path}: {exc}") from exc

    try:
        data = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ManifestIOError(f"Failed to parse manifest JSON {path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ManifestIOError(
            f"Manifest file {path} did not parse to a JSON object "
            f"(got {type(data).__name__})."
        )
    return data
