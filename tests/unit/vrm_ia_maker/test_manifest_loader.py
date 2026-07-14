"""Unit tests for production manifest JSON loading."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

import vrm_ia_maker
from vrm_ia_maker import (
    AssemblyManifest,
    AssetPackManifest,
    CompiledAssemblySpec,
    ManifestIOError,
    ManifestValidationError,
    load_assembly_manifest,
    load_asset_pack_manifest,
    load_compiled_assembly_spec,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _provenance() -> dict[str, object]:
    return {
        "author": "Katherine E. Aguirre / Juana IA",
        "source": "repository-owned procedural fixture",
        "license": "CC0-1.0",
        "commercial_use": True,
        "modification_allowed": True,
        "redistribution_allowed": True,
    }


def _metadata() -> dict[str, object]:
    return {
        "author": "Katherine E. Aguirre / Juana IA",
        "license": "CC0-1.0",
        "commercial_use": True,
        "redistribution": True,
    }


def _asset_pack_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "pack_id": "juana-test-pack",
        "provenance": _provenance(),
        "base_asset": {
            "asset_id": "base-v1",
            "path": "assets/base.glb",
            "object_name": "Armature",
            "sha256": DIGEST_A,
            "byte_length": 1024,
            "required_objects": ["Armature", "Body", "Head"],
            "required_bones": ["hips", "spine", "head"],
            "required_expressions": ["blink", "aa"],
        },
        "components": [
            {
                "asset_id": "hair-v1",
                "slot": "hair",
                "kind": "rigid_attachment",
                "path": "assets/hair.glb",
                "object_name": "Hair",
                "sha256": DIGEST_B,
                "byte_length": 512,
                "required": True,
                "attachment_bone": "head",
                "material_names": ["Hair_Primary"],
            }
        ],
    }


def _assembly_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "character_id": "juana",
        "display_name": "Juana",
        "asset_pack_id": "juana-test-pack",
        "selections": {"hair": {"asset_id": "hair-v1", "enabled": True}},
        "material_overrides": {"Hair_Primary": "#271C24"},
        "metadata": _metadata(),
    }


def _compiled_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "character_id": "juana",
        "display_name": "Juana",
        "asset_pack_id": "juana-test-pack",
        "provenance": _provenance(),
        "base_asset": {
            "asset_id": "base-v1",
            "path": "assets/base.glb",
            "object_name": "Armature",
            "sha256": DIGEST_A,
        },
        "components": [
            {
                "asset_id": "hair-v1",
                "slot": "hair",
                "kind": "rigid_attachment",
                "path": "assets/hair.glb",
                "object_name": "Hair",
                "sha256": DIGEST_B,
                "attachment_bone": "head",
                "material_names": ["Hair_Primary"],
            }
        ],
        "disabled_components": [
            {
                "asset_id": "brooch-v1",
                "slot": "accessory",
                "object_name": "Brooch",
            }
        ],
        "material_overrides": {"Hair_Primary": "#271C24"},
        "vrm_spec": {
            "spec_version": "1.0",
            "avatar_id": "juana",
            "display_name": "Juana",
            "base_asset_id": "base-v1",
            "bones": {"hips": "hips", "head": "head"},
            "expression_map": {"blink": [{"shape_key": "blink", "weight": 1.0}]},
            "look_at": {"horizontal_inner_degrees": 15.0},
            "metadata": _metadata(),
        },
    }


def test_loads_all_manifest_contracts_from_json_files(tmp_path: Path) -> None:
    asset_pack_path = _write_json(tmp_path / "asset-pack.json", _asset_pack_payload())
    assembly_path = _write_json(tmp_path / "assembly.json", _assembly_payload())
    compiled_path = _write_json(tmp_path / "compiled.json", _compiled_payload())

    assert isinstance(load_asset_pack_manifest(asset_pack_path), AssetPackManifest)
    assert isinstance(load_assembly_manifest(assembly_path), AssemblyManifest)
    assert isinstance(load_compiled_assembly_spec(compiled_path), CompiledAssemblySpec)


@pytest.mark.parametrize(
    ("path_name", "content"),
    [
        ("manifest.yaml", "{}"),
        ("manifest.json", "{"),
        ("manifest.json", "[]"),
    ],
)
def test_loader_rejects_invalid_file_inputs(
    tmp_path: Path,
    path_name: str,
    content: str,
) -> None:
    path = tmp_path / path_name
    path.write_text(content, encoding="utf-8")

    with pytest.raises(ManifestIOError):
        load_asset_pack_manifest(path)


def test_loader_rejects_missing_file(tmp_path: Path) -> None:
    with pytest.raises(ManifestIOError, match="not found"):
        load_asset_pack_manifest(tmp_path / "missing.json")


def test_loader_rejects_invalid_utf8_json(tmp_path: Path) -> None:
    path = tmp_path / "manifest.json"
    path.write_bytes(b'{"schema_version":"\xff"}')

    with pytest.raises(ManifestIOError):
        load_asset_pack_manifest(path)


def test_loader_wraps_contract_validation_errors(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "asset-pack.json", {"schema_version": "1.0"})

    with pytest.raises(ManifestValidationError) as exc_info:
        load_asset_pack_manifest(path)

    assert isinstance(exc_info.value.__cause__, ValidationError)
    assert str(path) in str(exc_info.value)


def test_loader_api_is_exported_from_package_namespace() -> None:
    assert vrm_ia_maker.load_asset_pack_manifest is load_asset_pack_manifest
    assert vrm_ia_maker.load_assembly_manifest is load_assembly_manifest
    assert vrm_ia_maker.load_compiled_assembly_spec is load_compiled_assembly_spec
    assert vrm_ia_maker.ManifestIOError is ManifestIOError
    assert vrm_ia_maker.ManifestValidationError is ManifestValidationError
