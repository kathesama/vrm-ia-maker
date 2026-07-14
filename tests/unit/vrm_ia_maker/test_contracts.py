"""Unit tests for production modular assembly contracts."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from vrm_ia_maker.contracts import (
    AssemblyManifest,
    AssetPackManifest,
    CompiledAssemblySpec,
)

DIGEST_A = "a" * 64
DIGEST_B = "b" * 64
DIGEST_C = "c" * 64


def provenance() -> dict[str, object]:
    return {
        "author": "Katherine E. Aguirre / Juana IA",
        "source": "repository-owned procedural fixture",
        "license": "CC0-1.0",
        "commercial_use": True,
        "modification_allowed": True,
        "redistribution_allowed": True,
    }


def asset_pack_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "pack_id": "juana-test-pack",
        "provenance": provenance(),
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
            },
            {
                "asset_id": "outfit-v1",
                "slot": "outfit",
                "kind": "skinned_mesh",
                "path": "assets/outfit.glb",
                "object_name": "Outfit",
                "sha256": DIGEST_C,
                "byte_length": 768,
                "required": True,
                "required_bones": ["hips", "spine"],
                "material_names": ["Outfit_Primary"],
            },
        ],
    }


def metadata() -> dict[str, object]:
    return {
        "author": "Katherine E. Aguirre / Juana IA",
        "license": "CC0-1.0",
        "commercial_use": True,
        "redistribution": True,
    }


def test_asset_pack_accepts_traceable_modular_assets() -> None:
    manifest = AssetPackManifest.model_validate(asset_pack_payload())

    assert manifest.pack_id == "juana-test-pack"
    assert manifest.components[0].attachment_bone == "head"
    assert manifest.components[1].required_bones == ("hips", "spine")


def test_rigid_attachment_requires_attachment_bone() -> None:
    payload = asset_pack_payload()
    del payload["components"][0]["attachment_bone"]  # type: ignore[index]

    with pytest.raises(ValidationError, match="attachment_bone"):
        AssetPackManifest.model_validate(payload)


def test_skinned_component_requires_bones() -> None:
    payload = asset_pack_payload()
    payload["components"][1]["required_bones"] = []  # type: ignore[index]

    with pytest.raises(ValidationError, match="required_bone"):
        AssetPackManifest.model_validate(payload)


def test_asset_pack_rejects_duplicate_asset_identifiers() -> None:
    payload = asset_pack_payload()
    payload["components"][0]["asset_id"] = "base-v1"  # type: ignore[index]

    with pytest.raises(ValidationError, match="unique"):
        AssetPackManifest.model_validate(payload)


def test_assembly_manifest_rejects_unknown_fields() -> None:
    payload = {
        "schema_version": "1.0",
        "character_id": "juana",
        "display_name": "Juana",
        "asset_pack_id": "juana-test-pack",
        "selections": {
            "hair": {"asset_id": "hair-v1", "enabled": True},
            "outfit": {"asset_id": "outfit-v1", "enabled": True},
        },
        "material_overrides": {"Hair_Primary": "#271C24"},
        "metadata": metadata(),
        "unexpected": True,
    }

    with pytest.raises(ValidationError, match="unexpected"):
        AssemblyManifest.model_validate(payload)


def test_assembly_manifest_rejects_invalid_material_override_color() -> None:
    payload = {
        "schema_version": "1.0",
        "character_id": "juana",
        "display_name": "Juana",
        "asset_pack_id": "juana-test-pack",
        "selections": {
            "hair": {"asset_id": "hair-v1", "enabled": True},
            "outfit": {"asset_id": "outfit-v1", "enabled": True},
        },
        "material_overrides": {"Hair_Primary": "blue"},
        "metadata": metadata(),
    }

    with pytest.raises(ValidationError, match="#RRGGBB"):
        AssemblyManifest.model_validate(payload)


def compiled_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "character_id": "juana",
        "display_name": "Juana",
        "asset_pack_id": "juana-test-pack",
        "provenance": provenance(),
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
            "metadata": metadata(),
        },
    }


def test_compiled_spec_preserves_provenance() -> None:
    spec = CompiledAssemblySpec.model_validate(compiled_payload())

    assert spec.provenance.license == "CC0-1.0"
    assert spec.components[0].slot.value == "hair"


def test_compiled_spec_rejects_enabled_and_disabled_overlap() -> None:
    payload = deepcopy(compiled_payload())
    payload["disabled_components"][0] = {  # type: ignore[index]
        "asset_id": "hair-v1",
        "slot": "hair",
        "object_name": "Hair",
    }

    with pytest.raises(ValidationError, match="both enabled and disabled"):
        CompiledAssemblySpec.model_validate(payload)


def test_compiled_spec_rejects_rigid_attachment_without_attachment_bone() -> None:
    payload = deepcopy(compiled_payload())
    del payload["components"][0]["attachment_bone"]  # type: ignore[index]

    with pytest.raises(ValidationError, match="attachment_bone"):
        CompiledAssemblySpec.model_validate(payload)


def test_compiled_spec_rejects_skinned_component_without_required_bones() -> None:
    payload = deepcopy(compiled_payload())
    payload["components"][0] = {  # type: ignore[index]
        "asset_id": "outfit-v1",
        "slot": "outfit",
        "kind": "skinned_mesh",
        "path": "assets/outfit.glb",
        "object_name": "Outfit",
        "sha256": DIGEST_C,
        "material_names": ["Outfit_Primary"],
    }

    with pytest.raises(ValidationError, match="required_bone"):
        CompiledAssemblySpec.model_validate(payload)
