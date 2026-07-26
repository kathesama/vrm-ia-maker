"""Contracts for the clean GH-22 Juana production checkpoint."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest
from PIL import Image
from tools.juana_bust.build_preview import (
    create_donor_transfer_comparisons,
    provisional_output_paths,
    verify_donor_inputs,
)
from tools.juana_bust.production_gate import (
    REQUIRED_PRODUCTION_COLLECTIONS,
    REQUIRED_REFERENCE_COLLECTIONS,
    ExportGateError,
    validate_scene_inventory,
    validate_visual_profile,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = REPOSITORY_ROOT / "tools" / "juana_bust"


def _valid_inventory() -> dict[str, object]:
    return {
        "collections": [
            *REQUIRED_REFERENCE_COLLECTIONS,
            *REQUIRED_PRODUCTION_COLLECTIONS,
        ],
        "objects": [
            {
                "name": "SAM3D_HumanMesh_Reference",
                "type": "MESH",
                "role": "reference_sam3d",
                "collections": ["_REFERENCE_SAM3D"],
                "exportable": False,
                "renderable": False,
                "vertices": 18439,
                "triangles": 36874,
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Highpoly_Bust_Reference",
                "type": "MESH",
                "role": "reference_highpoly",
                "collections": ["_REFERENCE_HIGHPOLY"],
                "exportable": False,
                "renderable": False,
                "vertices": 924342,
                "triangles": 1363714,
                "root_transform_applied": True,
            },
            {
                "name": "DonorVRM_Armature",
                "type": "ARMATURE",
                "role": "donor_vrm_rig",
                "collections": ["_DONOR_VRM"],
                "exportable": False,
                "renderable": False,
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Production_Body",
                "type": "MESH",
                "role": "production_body",
                "collections": ["_PRODUCTION_BODY", "_EXPORT"],
                "exportable": True,
                "renderable": True,
                "skinned_to": "Juana_Production_Rig",
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Production_Head",
                "type": "MESH",
                "role": "production_head",
                "collections": ["_PRODUCTION_HEAD", "_EXPORT"],
                "exportable": True,
                "renderable": True,
                "skinned_to": "Juana_Production_Rig",
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Production_Eye_L",
                "type": "MESH",
                "role": "production_eye",
                "collections": ["_PRODUCTION_HEAD", "_EXPORT"],
                "exportable": True,
                "renderable": True,
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Production_Eye_R",
                "type": "MESH",
                "role": "production_eye",
                "collections": ["_PRODUCTION_HEAD", "_EXPORT"],
                "exportable": True,
                "renderable": True,
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Production_Hair",
                "type": "MESH",
                "role": "production_hair",
                "collections": ["_PRODUCTION_HAIR", "_EXPORT"],
                "exportable": True,
                "renderable": True,
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Production_Outfit",
                "type": "MESH",
                "role": "production_outfit",
                "collections": ["_PRODUCTION_OUTFIT", "_EXPORT"],
                "exportable": True,
                "renderable": True,
                "root_transform_applied": True,
            },
            {
                "name": "Juana_Production_Rig",
                "type": "ARMATURE",
                "role": "production_rig",
                "collections": ["_RIG", "_EXPORT"],
                "exportable": True,
                "renderable": False,
                "root_transform_applied": True,
            },
        ],
    }


def _valid_visual_profile() -> dict[str, object]:
    return {
        "body_fit": {
            "profile": "approved_athletic_hourglass",
            "bands": {
                "hips": {
                    "production_width_after": 0.42,
                    "production_depth_after": 0.30,
                },
                "waist": {
                    "production_width_after": 0.28,
                    "production_depth_after": 0.22,
                },
            },
        },
        "skin_material": {
            "application": "approved_master_reference_skin_tone",
            "base_color_linear": [0.30, 0.14, 0.075],
        },
    }


def test_clean_output_root_cannot_reuse_invalid_overlay_build() -> None:
    paths = provisional_output_paths(REPOSITORY_ROOT)

    assert paths["root"] == REPOSITORY_ROOT / "build" / "juana-clean-production-preview"
    assert paths["blend"].name == "juana-clean-production-provisional.blend"
    assert paths["glb"].name == "juana-clean-production-provisional.glb"
    assert paths["inventory"].name == "exported-mesh-inventory.json"
    assert paths["fit_report"].name == "production-fit-report.json"
    assert paths["sam_body_comparison"].name == "sam3d-vs-production-body.png"
    assert paths["highpoly_head_comparison"].name == (
        "highpoly-vs-production-head.png"
    )


def test_build_entrypoint_uses_only_the_clean_scene_author() -> None:
    source = (TOOL_ROOT / "build_preview.py").read_text(encoding="utf-8")

    assert "blender_author_clean_production.py" in source
    assert "blender_validate_clean_production.py" in source
    assert "blender_author_preview.py" not in source
    assert "blender_validate_preview.py" not in source


def test_render_manifest_declares_topology_and_donor_comparisons() -> None:
    manifest = json.loads(
        (TOOL_ROOT / "render-manifest.json").read_text(encoding="utf-8")
    )

    assert manifest["review_presentation"]["revision"] == (
        "gh-22-clean-production-pass-2"
    )
    assert manifest["diagnostics"] == {
        "wireframe": "wireframe.png",
        "sam3d_reference_body": "sam3d-reference-body.png",
        "production_body": "production-body.png",
        "highpoly_reference_head": "highpoly-reference-head.png",
        "production_head": "production-head.png",
    }


def test_source_evidence_pins_mutually_exclusive_donor_roles() -> None:
    evidence = json.loads(
        (TOOL_ROOT / "source-evidence.json").read_text(encoding="utf-8")
    )
    donors = {item["id"]: item for item in evidence["donors"]}

    assert donors["juana-provisional-vrm-donor"]["sha256"] == (
        "7533c198f84db73e02be921f7f6d33dfae693f2cefdc7a6cf724b4597beefc0c"
    )
    assert donors["juana-provisional-vrm-donor"]["role"] == (
        "humanoid_contract_and_exporter_donor_only"
    )
    assert donors["juana-sam3d-humanmesh-donor"]["sha256"] == (
        "d1f41ceee19ecfd493945cc9895c068563237e385858e66aa545e0d9f09721de"
    )
    assert donors["juana-sam3d-humanmesh-donor"]["role"] == (
        "body_shape_and_proportion_donor_only"
    )
    assert donors["juana-highpoly-bust-donor"]["sha256"] == (
        "ead2c523ff3c44a57cf79527c3f439443f6f077067735a90c7efbb7065525364"
    )
    assert donors["juana-highpoly-bust-donor"]["role"] == (
        "likeness_hair_outfit_and_texture_bake_donor_only"
    )
    assert {item["production_geometry"] for item in donors.values()} == {False}
    assert {item["direct_export_allowed"] for item in donors.values()} == {False}
    assert all(not Path(item["local_path"]).is_absolute() for item in donors.values())


def test_sam3d_donor_declares_one_normalized_derived_reference() -> None:
    evidence = json.loads(
        (TOOL_ROOT / "source-evidence.json").read_text(encoding="utf-8")
    )
    donor = next(
        item
        for item in evidence["donors"]
        if item["id"] == "juana-sam3d-humanmesh-donor"
    )
    derived = donor["derived_reference"]

    assert derived["path"] == (
        "tools/juana_bust/assets/juana-sam3d-humanmesh-reference.glb"
    )
    assert len(derived["sha256"]) == 64
    assert derived["source_sha256"] == donor["sha256"]
    assert derived["mesh_count"] == 1
    assert derived["mesh_name"] == "SAM3D_HumanMesh_Reference"
    assert derived["vertices"] == 18439
    assert derived["triangles"] == 36874
    assert derived["root_transform_applied"] is True
    assert derived["feet_on_ground"] is True
    assert derived["horizontal_centered"] is True
    assert derived["production_geometry"] is False


def test_visual_correction_declares_reproducible_body_and_skin_profile() -> None:
    evidence = json.loads(
        (TOOL_ROOT / "source-evidence.json").read_text(encoding="utf-8")
    )
    correction = evidence["visual_correction_pass_2"]

    assert correction["review_status"] == "changes_requested"
    assert correction["full_character_sheet_sha256"] == (
        "eeb2f11aa0a426a56b594dfdf0a406c6caa3d7db11df10178aa2c228bda2eb8f"
    )
    assert correction["body_profile"]["name"] == "approved_athletic_hourglass"
    assert correction["body_profile"]["macro_overrides"]["weight"] == 0.28
    assert correction["body_profile"]["macro_overrides"]["muscle"] >= 0.50
    assert correction["body_profile"]["bands"]["hips"]["width_scale_range"][1] <= 1.02
    assert correction["skin"]["reference_sha256"] == (
        "8000236316b8fea12e1bbc0b7a2349fce7bd70ac7d9efe74cc1ff4ee5ee26224"
    )
    assert correction["skin"]["base_color_linear"] == [0.30, 0.14, 0.075]


def test_visual_profile_gate_accepts_approved_silhouette_and_skin() -> None:
    result = validate_visual_profile(_valid_visual_profile())

    assert result["waist_to_hip_width"] == pytest.approx(2 / 3)
    assert result["waist_to_hip_depth"] == pytest.approx(0.7333333333)
    assert result["skin_base_color_linear"] == [0.30, 0.14, 0.075]


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda report: report["body_fit"]["bands"]["waist"].update(
                {"production_depth_after": 0.27}
            ),
            "waist-to-hip depth ratio",
        ),
        (
            lambda report: report["skin_material"].update(
                {"base_color_linear": [0.176, 0.116, 0.077]}
            ),
            "skin base color",
        ),
    ],
)
def test_visual_profile_gate_rejects_previous_body_or_skin(
    mutation,
    message: str,
) -> None:
    report = _valid_visual_profile()
    mutation(report)

    with pytest.raises(ExportGateError, match=message):
        validate_visual_profile(report)


def test_export_gate_accepts_one_clean_character() -> None:
    result = validate_scene_inventory(_valid_inventory())

    assert result["production_body"] == "Juana_Production_Body"
    assert result["production_head"] == "Juana_Production_Head"
    assert result["production_rig"] == "Juana_Production_Rig"
    assert result["exportable_object_count"] == 7


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (
            lambda inventory: inventory["objects"][0].update(
                {"exportable": True, "collections": ["_REFERENCE_SAM3D", "_EXPORT"]}
            ),
            "donor or reference object is exportable",
        ),
        (
            lambda inventory: inventory["objects"].append(
                {
                    **copy.deepcopy(inventory["objects"][3]),
                    "name": "Juana_Production_Body_Copy",
                }
            ),
            "exactly one renderable production_body",
        ),
        (
            lambda inventory: inventory["objects"].append(
                {
                    "name": "Torso_busto_donor",
                    "type": "MESH",
                    "role": "reference_highpoly",
                    "collections": ["_EXPORT"],
                    "exportable": True,
                    "renderable": True,
                    "vertices": 924342,
                    "triangles": 1363714,
                    "root_transform_applied": True,
                }
            ),
            "donor or reference object is exportable",
        ),
        (
            lambda inventory: inventory["objects"].append(
                {
                    "name": "Body",
                    "type": "MESH",
                    "role": "production_auxiliary",
                    "collections": ["_EXPORT"],
                    "exportable": True,
                    "renderable": True,
                    "vertices": 1104,
                    "triangles": 528,
                    "root_transform_applied": True,
                }
            ),
            "procedural spike mannequin signature",
        ),
    ],
)
def test_export_gate_rejects_invalid_compositions(mutation, message: str) -> None:
    inventory = _valid_inventory()
    mutation(inventory)

    with pytest.raises(ExportGateError, match=message):
        validate_scene_inventory(inventory)


def test_export_gate_rejects_unapplied_production_root_transform() -> None:
    inventory = _valid_inventory()
    inventory["objects"][4]["root_transform_applied"] = False

    with pytest.raises(ExportGateError, match="unapplied root transform"):
        validate_scene_inventory(inventory)


def test_donor_transfer_comparisons_have_fixed_layout(tmp_path: Path) -> None:
    renders_root = tmp_path / "renders"
    comparisons_root = tmp_path / "comparisons"
    renders_root.mkdir()
    for filename, color in (
        ("sam3d-reference-body.png", (30, 40, 50)),
        ("production-body.png", (60, 70, 80)),
        ("highpoly-reference-head.png", (90, 100, 110)),
        ("production-head.png", (120, 130, 140)),
    ):
        Image.new("RGB", (1024, 1024), color).save(renders_root / filename)

    outputs = create_donor_transfer_comparisons(
        renders_root=renders_root,
        comparisons_root=comparisons_root,
    )

    assert outputs == {
        "sam3d-vs-production-body": comparisons_root
        / "sam3d-vs-production-body.png",
        "highpoly-vs-production-head": comparisons_root
        / "highpoly-vs-production-head.png",
    }
    for output in outputs.values():
        with Image.open(output) as comparison:
            assert comparison.size == (2048, 1072)


def test_raw_donor_verification_resolves_relative_and_absolute_paths(
    tmp_path: Path,
) -> None:
    repository_root = tmp_path / "repository"
    repository_root.mkdir()
    relative_donor = repository_root / "donor.vrm"
    absolute_donor = tmp_path / "person.glb"
    relative_donor.write_bytes(b"vrm")
    absolute_donor.write_bytes(b"sam3d")
    evidence_path = repository_root / "evidence.json"
    evidence_path.write_text(
        json.dumps(
            {
                "donors": [
                    {
                        "id": "vrm-donor",
                        "local_path": "donor.vrm",
                        "sha256": hashlib.sha256(b"vrm").hexdigest(),
                        "byte_length": 3,
                    },
                    {
                        "id": "sam-donor",
                        "local_path": str(absolute_donor),
                        "sha256": hashlib.sha256(b"sam3d").hexdigest(),
                        "byte_length": 5,
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    verified = verify_donor_inputs(
        repository_root=repository_root,
        evidence_path=evidence_path,
    )

    assert [item["id"] for item in verified] == ["vrm-donor", "sam-donor"]
    assert Path(verified[0]["path"]) == relative_donor
    assert Path(verified[1]["path"]) == absolute_donor
