"""Unit tests for production Forge evidence and report contracts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

import vrm_ia_maker
import vrm_ia_maker.contracts as contracts
import vrm_ia_maker.manifest_loader as manifest_loader

DIGEST = "a" * 64


def _contract(name: str) -> Any:
    assert hasattr(contracts, name), f"Missing production contract: {name}"
    return getattr(contracts, name)


def _evidence_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "character_id": "procedural-avatar",
        "base_adapter_id": "procedural-base-adapter",
        "base_adapter_version": "1.0.0",
        "armature_objects": ["Armature"],
        "selected_components": [
            {
                "asset_id": "hair-v1",
                "slot": "hair",
                "kind": "rigid_attachment",
                "object_name": "Hair",
            }
        ],
        "disabled_components": [
            {
                "asset_id": "brooch-v1",
                "slot": "accessory",
                "object_name": "Brooch",
            }
        ],
        "scene_objects_before_export": ["Armature", "Body", "Hair"],
        "humanoid_bones": ["hips", "head"],
        "expressions": ["blink", "aa"],
        "look_at": {
            "horizontal_inner_degrees": 15.0,
            "horizontal_outer_degrees": 30.0,
            "vertical_down_degrees": 10.0,
            "vertical_up_degrees": 10.0,
        },
        "metadata": {
            "author": "Katherine E. Aguirre / Juana IA",
            "license": "CC0-1.0",
            "commercial_use": True,
            "redistribution": True,
        },
    }


def _report_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "character_id": "procedural-avatar",
        "display_name": "Procedural Avatar",
        "asset_pack_id": "procedural-pack",
        "base_adapter_id": "procedural-base-adapter",
        "base_adapter_version": "1.0.0",
        "vrm_path": "build/procedural-avatar.vrm",
        "vrm_sha256": DIGEST,
        "vrm_byte_length": 4096,
        "blender_exit_code": 0,
        "blender_duration_seconds": 2.5,
        "evidence": _evidence_payload(),
    }


def test_blender_evidence_requires_one_authoritative_armature() -> None:
    evidence_type = _contract("BlenderBuildEvidence")
    evidence = evidence_type.model_validate(_evidence_payload())

    assert evidence.armature_objects == ("Armature",)
    assert evidence.selected_components[0].kind.value == "rigid_attachment"

    payload = _evidence_payload()
    payload["armature_objects"] = ["Armature", "AccessoryRig"]
    with pytest.raises(ValidationError, match="at most 1 item"):
        evidence_type.model_validate(payload)


def test_forge_build_report_preserves_verified_output_identity() -> None:
    report_type = _contract("ForgeBuildReport")
    report = report_type.model_validate(_report_payload())

    assert report.vrm_path == Path("build/procedural-avatar.vrm")
    assert report.vrm_sha256 == DIGEST
    assert report.vrm_byte_length == 4096
    assert report.blender_exit_code == 0


@pytest.mark.parametrize(
    ("field_name", "invalid_value"),
    [
        ("vrm_sha256", "not-a-digest"),
        ("vrm_byte_length", 0),
        ("blender_exit_code", 1),
        ("blender_duration_seconds", -0.1),
    ],
)
def test_forge_build_report_rejects_unverified_success_fields(
    field_name: str,
    invalid_value: object,
) -> None:
    report_type = _contract("ForgeBuildReport")
    payload = _report_payload()
    payload[field_name] = invalid_value

    with pytest.raises(ValidationError):
        report_type.model_validate(payload)


def test_loads_forge_build_report_from_public_package_api(tmp_path: Path) -> None:
    assert hasattr(manifest_loader, "load_forge_build_report")
    assert hasattr(vrm_ia_maker, "load_forge_build_report")
    report_path = tmp_path / "forge-build-report.json"
    report_path.write_text(json.dumps(_report_payload()), encoding="utf-8")

    report = manifest_loader.load_forge_build_report(report_path)

    assert isinstance(report, _contract("ForgeBuildReport"))
    assert vrm_ia_maker.load_forge_build_report is manifest_loader.load_forge_build_report
