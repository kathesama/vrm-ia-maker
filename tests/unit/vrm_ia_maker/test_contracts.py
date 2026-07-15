"""Unit tests for production modular assembly contracts."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from vrm_ia_maker.contracts import (
    AssemblyManifest,
    AssetPackManifest,
    BaseModelAdapterManifest,
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


def base_adapter_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "adapter_id": "procedural-base-adapter",
        "adapter_version": "1.0.0",
        "base_asset_id": "base-v1",
        "bones": {"hips": "hips", "head": "head"},
        "expression_map": {
            "blink": [{"shape_key": "blink", "weight": 1.0}],
            "aa": [{"shape_key": "aa", "weight": 1.0}],
        },
        "look_at": {
            "horizontal_inner_degrees": 15.0,
            "horizontal_outer_degrees": 15.0,
            "vertical_down_degrees": 10.0,
            "vertical_up_degrees": 10.0,
        },
    }


def test_base_model_adapter_manifest_accepts_versioned_vrm_mappings() -> None:
    adapter = BaseModelAdapterManifest.model_validate(base_adapter_payload())

    assert adapter.adapter_id == "procedural-base-adapter"
    assert adapter.bones["head"] == "head"
    assert adapter.expression_map["blink"][0].shape_key == "blink"
    assert adapter.look_at.vertical_up_degrees == 10.0


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("adapter_version", ""),
        ("bones", {}),
        ("expression_map", {}),
    ],
)
def test_base_model_adapter_manifest_rejects_incomplete_mappings(
    field_name: str,
    invalid_value: object,
) -> None:
    payload = base_adapter_payload()
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        BaseModelAdapterManifest.model_validate(payload)


def test_base_model_adapter_manifest_rejects_invalid_expression_weight() -> None:
    payload = base_adapter_payload()
    payload["expression_map"]["blink"][0]["weight"] = 1.1  # type: ignore[index]

    with pytest.raises(ValidationError, match="less than or equal to 1"):
        BaseModelAdapterManifest.model_validate(payload)


def test_base_model_adapter_manifest_requires_complete_look_at_limits() -> None:
    payload = base_adapter_payload()
    del payload["look_at"]["vertical_up_degrees"]  # type: ignore[index]

    with pytest.raises(ValidationError, match="vertical_up_degrees"):
        BaseModelAdapterManifest.model_validate(payload)


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


def compiled_payload_1_1() -> dict[str, object]:
    payload = compiled_payload()
    payload.update(
        {
            "schema_version": "1.1",
            "base_adapter_id": "procedural-base-adapter",
            "base_adapter_version": "1.0.0",
        }
    )
    payload["vrm_spec"]["look_at"] = base_adapter_payload()["look_at"]  # type: ignore[index]
    return payload


def test_compiled_spec_preserves_provenance() -> None:
    spec = CompiledAssemblySpec.model_validate(compiled_payload())

    assert spec.provenance.license == "CC0-1.0"
    assert spec.components[0].slot.value == "hair"


def test_compiled_spec_1_0_preserves_retained_spike_vrm_fields() -> None:
    payload = compiled_payload()
    legacy_fields = {
        "body": {"height_scale": 1.0},
        "face": {"skin_color": {"r": 0.72, "g": 0.42, "b": 0.30}},
        "hair": {"color": {"r": 0.17, "g": 0.11, "b": 0.15}},
        "tint_blend": {"hair": 1.0, "skin": 0.0, "eye": 0.0},
        "subsurface_scattering": {"enabled": False},
        "assembly_manifest": {
            "schema_version": "1.0",
            "selected_assets": ["hair-v1"],
            "disabled_assets": ["brooch-v1"],
        },
    }
    payload["vrm_spec"].update(legacy_fields)  # type: ignore[union-attr]
    payload["components"][0]["bone_names"] = ["head"]  # type: ignore[index]

    spec = CompiledAssemblySpec.model_validate(payload)

    assert spec.vrm_spec.model_extra == legacy_fields
    assert spec.components[0].model_extra == {"bone_names": ["head"]}


def test_compiled_spec_1_1_requires_adapter_traceability() -> None:
    payload = compiled_payload_1_1()

    spec = CompiledAssemblySpec.model_validate(payload)

    assert spec.base_adapter_id == "procedural-base-adapter"
    assert spec.base_adapter_version == "1.0.0"
    assert spec.vrm_spec.look_at.vertical_up_degrees == 10.0

    del payload["base_adapter_version"]
    with pytest.raises(ValidationError, match="base_adapter_id and base_adapter_version"):
        CompiledAssemblySpec.model_validate(payload)


@pytest.mark.parametrize(
    "malformed_mapping",
    ["bones", "expression_map", "look_at", "binding", "weight"],
)
def test_compiled_spec_1_1_rejects_malformed_adapter_derived_mappings(
    malformed_mapping: str,
) -> None:
    payload = compiled_payload_1_1()
    if malformed_mapping == "bones":
        payload["vrm_spec"]["bones"] = {}  # type: ignore[index]
    elif malformed_mapping == "expression_map":
        payload["vrm_spec"]["expression_map"] = {}  # type: ignore[index]
    elif malformed_mapping == "look_at":
        del payload["vrm_spec"]["look_at"]["vertical_up_degrees"]  # type: ignore[index]
    elif malformed_mapping == "binding":
        payload["vrm_spec"]["expression_map"]["blink"] = [{}]  # type: ignore[index]
    else:
        payload["vrm_spec"]["expression_map"]["blink"][0]["weight"] = 1.1  # type: ignore[index]

    with pytest.raises(ValidationError):
        CompiledAssemblySpec.model_validate(payload)


def test_compiled_spec_1_1_rejects_legacy_component_inspection_fields() -> None:
    payload = compiled_payload_1_1()
    payload["components"][0]["bone_names"] = ["head"]  # type: ignore[index]

    with pytest.raises(ValidationError, match="legacy component inspection fields"):
        CompiledAssemblySpec.model_validate(payload)


def test_compiled_spec_1_0_rejects_adapter_traceability_fields() -> None:
    payload = compiled_payload()
    payload.update(
        {
            "base_adapter_id": "procedural-base-adapter",
            "base_adapter_version": "1.0.0",
        }
    )

    with pytest.raises(ValidationError, match="schema 1.1"):
        CompiledAssemblySpec.model_validate(payload)


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
