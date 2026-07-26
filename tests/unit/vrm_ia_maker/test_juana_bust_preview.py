"""Focused contract tests for the provisional GH-22 Juana bust pipeline."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo
from tools.juana_bust.build_preview import (
    IntegrityError,
    canonicalize_render,
    create_comparison_sheets,
    load_json_object,
    provisional_output_paths,
    sha256_tree,
    validate_render_manifest,
    verify_file,
    verify_source_inputs,
)

from vrm_ia_maker import load_base_model_adapter_manifest

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
TOOL_ROOT = REPOSITORY_ROOT / "tools" / "juana_bust"
ADAPTER_PATH = REPOSITORY_ROOT / "examples" / "juana-bust" / "base-adapter.json"


def test_toolchain_lock_pins_verified_human_base_inputs() -> None:
    lock = load_json_object(TOOL_ROOT / "toolchain-lock.json")
    artifacts = {item["id"]: item for item in lock["artifacts"]}

    assert lock["schema_version"] == "1.0"
    assert lock["status"] == "provisional"
    assert artifacts["blender-4.2.0-windows-x64-zip"]["sha256"] == (
        "b6e72874f8cb5c4ed77f9b03d7f1fde851b9455a7ff02a1e1119c876318ebc65"
    )
    assert artifacts["mpfb-2.0.16-extension"]["sha256"] == (
        "b5cdc8b08147e0c6463e4faa01147491b13a0b062f73415363f029debd11c934"
    )
    assert artifacts["mpfb-2.0.16-installed-tree"]["sha256"] == (
        "942acff6b097a4244a7c380c7a1afee4dbf3f6207d2cf61e90b441cadfb7c7cb"
    )
    assert artifacts["mpfb-2.0.16-installed-tree"]["file_count"] == 2316
    assert artifacts["makehuman-system-assets-cc0"]["license"] == "CC0-1.0"
    assert artifacts["makehuman-hm08-base"]["license"] == "CC0-1.0"
    assert lock["human_base"]["generator"] == "MPFB"
    assert lock["human_base"]["rig"] == "default"
    assert lock["human_base"]["macro_settings"]["gender"] == 0.0


def test_source_evidence_tracks_approved_juana_canon_without_metric_claims() -> None:
    evidence = load_json_object(TOOL_ROOT / "source-evidence.json")

    assert evidence["status"] == "provisional_visual_checkpoint"
    assert evidence["master_reference"]["sha256"] == (
        "63c3510c51545748ae7aa9d1d6b7d909067bcc1d22663f4bf1b91742f6c88a18"
    )
    assert evidence["master_reference"]["rights_holder"] == "Katherine E. Aguirre"
    assert evidence["hair"]["close_cut_side"] == "anatomical_left"
    assert evidence["hair"]["long_side"] == "anatomical_right"
    assert all(
        re.fullmatch(r"[a-f0-9]{64}", reference["sha256"])
        for reference in evidence["face_references"]
    )
    assert all(
        assumption["classification"] == "provisional_visual_assumption"
        for assumption in evidence["identity_assumptions"]
    )
    assert evidence["visual_review"]["decision"] == "changes_requested"
    assert evidence["visual_review"]["checkpoint"] == "gh-22-invalid-donor-overlay"
    assert evidence["visual_review"]["next_checkpoint"] == (
        "gh-22-clean-production-pass-1"
    )
    assert evidence["visual_review"]["visual_canon_approved"] is False


def test_hunyuan_reference_records_rights_and_safe_geometry_boundary() -> None:
    evidence = load_json_object(TOOL_ROOT / "source-evidence.json")
    reference = evidence["generated_geometry_reference"]
    proxy = reference["derived_visual_proxy"]

    assert reference["id"] == "juana-hunyuan-torso-bust-r1"
    assert reference["source_filename"] == "Torso - busto.glb"
    assert reference["sha256"] == (
        "ead2c523ff3c44a57cf79527c3f439443f6f077067735a90c7efbb7065525364"
    )
    assert reference["byte_length"] == 83723136
    assert reference["origin"] == "Tencent HY 3D Global"
    assert reference["terms"]["section"] == "6.3"
    assert reference["terms"]["output_rights_assigned_to_user"] is True
    assert reference["terms"]["ai_disclosure_required"] is True
    assert reference["usage_boundary"]["raw_source_export"] is False
    assert reference["usage_boundary"]["derived_geometry_transfer"] is True
    assert reference["usage_boundary"]["derived_texture_transfer"] is True
    assert (
        reference["usage_boundary"]["export_unmodified_source_geometry"] is False
    )
    assert proxy["path"] == (
        "tools/juana_bust/assets/juana-hunyuan-identity-proxy.glb"
    )
    assert re.fullmatch(r"[a-f0-9]{64}", proxy["sha256"])
    assert proxy["byte_length"] > 0
    assert proxy["source_sha256"] == reference["sha256"]
    assert proxy["ai_generated_disclosure"] is True
    assert proxy["status"] == "superseded_rejected_overlay_checkpoint"
    assert proxy["processing"]["target_triangle_count"] <= 400000
    assert proxy["processing"]["material_policy"] == (
        "embedded base color only with neutral physically based response"
    )
    assert proxy["processing"]["semantic_materials"] == [
        "source_neutral",
        "skin_warm_golden_brown",
        "hair_low_specular",
    ]
    assert proxy["integration"]["visible_checkpoint_only"] is True
    assert proxy["integration"]["production_topology"] is False
    assert proxy["integration"]["rig_source"] == "MakeHuman MPFB default rig"
    assert proxy["integration"]["functional_eye_overlay"] is True
    assert proxy["integration"]["functional_brow_overlay"] is True
    assert reference["usage_boundary"]["calibration_inputs"] == [
        "facial_landmark_proportions",
        "profile_projection",
        "hair_silhouette",
        "upper_torso_silhouette",
    ]


def test_meta_mhr_reference_records_rig_calibration_boundary() -> None:
    evidence = load_json_object(TOOL_ROOT / "source-evidence.json")
    reference = evidence["generated_body_calibration_reference"]
    derived = reference["derived_calibration_asset"]

    assert reference["id"] == "juana-meta-mhr-body-r1"
    assert reference["source_filename"] == "juana-grb to vrm.blend"
    assert reference["sha256"] == (
        "8c7afc60df553b66e1cc3143fc2c04878475e97433d9d6af190393f48eec9ccb"
    )
    assert reference["byte_length"] == 1648460
    assert reference["origin"] == "Meta AI Demos"
    assert reference["generator_family"] == "SAM 3D Body / MHR"
    assert reference["authorization"]["project_use_authorized"] is True
    assert reference["authorization"]["input_rights_confirmed"] is True
    assert reference["mhr_decoder"]["release"] == "v1.0.1"
    assert reference["mhr_decoder"]["license"] == "Apache-2.0"
    assert reference["mhr_decoder"]["asset_license_embedded"] is True
    assert reference["mesh_inspection"] == {
        "vertices": 18439,
        "triangles": 36874,
        "joint_markers": 88,
        "visual_bone_segments": 85,
        "armatures": 0,
        "weighted_vertices": 0,
        "shape_keys": 0,
        "topology_match": "MHR LOD1 exact vertex and ordered-face identity",
    }
    assert derived["path"] == (
        "tools/juana_bust/assets/juana-meta-mhr-calibration.glb"
    )
    assert re.fullmatch(r"[a-f0-9]{64}", derived["sha256"])
    assert derived["byte_length"] > 0
    assert derived["source_sha256"] == reference["sha256"]
    assert derived["vertices"] == 18439
    assert derived["triangles"] == 36874
    assert derived["bones"] == 88
    assert derived["weighted_vertices"] == 18439
    assert reference["usage_boundary"] == {
        "calibration_only": True,
        "production_base": False,
        "face_likeness_source": False,
        "allowed_inputs": [
            "upper_body_proportions",
            "joint_landmarks",
            "rig_alignment",
            "body_silhouette_comparison",
        ],
        "reason": (
            "The single-image MHR result is useful for body and joint calibration, "
            "but its face is not recognizable enough to replace the approved Juana "
            "identity references or the MPFB production base."
        ),
    }


def test_third_likeness_pass_records_landmark_calibrated_controls() -> None:
    evidence = load_json_object(TOOL_ROOT / "source-evidence.json")
    likeness = evidence["likeness_pass_3"]
    controls = {control["name"]: control for control in likeness["target_controls"]}

    assert likeness["classification"] == "provisional_visual_assumption"
    assert likeness["transfer_method"] == "manual_landmark_calibration"
    assert likeness["raw_mesh_transfer"] is False
    assert controls["identity_head_compact"]["target"] == ("head/head-scale-vert-decr.target.gz")
    assert controls["identity_head_width"]["target"] == ("head/head-scale-horiz-incr.target.gz")
    assert controls["identity_eye_left_out"]["target"] == ("eyes/l-eye-trans-out.target.gz")
    assert controls["identity_eye_right_out"]["target"] == ("eyes/r-eye-trans-out.target.gz")
    assert controls["identity_eye_left_narrow"]["target"] == ("eyes/l-eye-scale-decr.target.gz")
    assert controls["identity_eye_right_narrow"]["target"] == ("eyes/r-eye-scale-decr.target.gz")
    assert controls["identity_nose_width"]["target"] == ("nose/nose-scale-horiz-incr.target.gz")
    assert controls["identity_nostril_width"]["target"] == (
        "nose/nose-nostrils-width-incr.target.gz"
    )
    assert controls["identity_cupids_bow"]["target"] == ("mouth/mouth-cupidsbow-incr.target.gz")
    assert controls["identity_head_compact"]["weight"] >= 0.45
    assert controls["identity_cheekbone_left"]["weight"] >= 0.7
    assert controls["identity_cheekbone_right"]["weight"] >= 0.7
    assert controls["identity_chin_width"]["weight"] >= 0.4
    assert controls["identity_chin_height"]["weight"] >= 0.5
    assert controls["identity_lower_lip"]["weight"] > controls["identity_upper_lip"]["weight"]
    assert controls["identity_mouth_width"]["weight"] <= 0.1
    assert likeness["landmark_calibration"]["eye_to_chin_compression"] < 1.0
    assert likeness["landmark_calibration"]["eye_spacing_scale"] > 1.0
    assert likeness["eye_appearance"]["shape"] == "narrow_almond"
    assert likeness["eye_appearance"]["iris_color"] == "warm_amber_brown"
    assert likeness["eyebrows"]["shape"] == "thick_dark_strong_arch"
    assert likeness["skin"]["tone"] == "warm_golden_brown"
    assert likeness["hair"]["construction"] == "large_flowing_asymmetric_clumps"
    assert likeness["hair"]["minimum_clump_count"] >= 10


def test_fourth_likeness_pass_combines_identity_and_body_calibration() -> None:
    evidence = load_json_object(TOOL_ROOT / "source-evidence.json")
    likeness = evidence["likeness_pass_4"]

    assert likeness["classification"] == "provisional_visual_assumption"
    assert likeness["review_status"] == "rejected_invalid_donor_overlay"
    assert likeness["historical_only"] is True
    assert likeness["superseded_by"] == "gh-22-clean-production-pass-1"
    assert likeness["identity_source"] == "juana-hunyuan-identity-proxy"
    assert likeness["body_calibration_source"] == "juana-meta-mhr-calibration"
    assert likeness["production_base"] == "makehuman-hm08-juana-bust-r1"
    assert likeness["visible_surface_policy"] == {
        "identity_proxy": "full_bust_identity_surface",
        "meta_mhr": "hidden_body_and_rig_calibration_only",
        "mpfb": "hidden_editable_rig_and_morph_scaffold",
    }
    assert likeness["face_adjustments"] == {
        "lower_face_vertical_compression": 0.07,
        "cheekbone_width_scale": 1.045,
        "jaw_width_scale": 1.06,
        "eye_vertical_scale": 0.82,
        "iris_overlay_width_m": 0.0166,
        "nose_width_scale": 1.08,
        "nose_projection_m": 0.003,
        "lip_projection_m": 0.0015,
        "skin_tint_linear": [0.46, 0.34, 0.26],
    }
    assert likeness["body_adjustments"]["source_topology"] == "MHR LOD1"
    assert likeness["body_adjustments"]["joint_marker_count"] == 88
    assert likeness["body_adjustments"]["production_base_replaced"] is False
    assert likeness["body_adjustments"]["visible_in_checkpoint"] is False
    assert likeness["saved_blend_presentation"] == {
        "active_camera": "Camera_front",
        "visible_collection": "JUANA_REVIEW",
        "visible_objects": [
            "Juana_Hunyuan_Identity_Proxy",
            "Juana_Iris_Overlay_L",
            "Juana_Iris_Overlay_R",
        ],
        "hidden_collections": [
            "JUANA_TECHNICAL",
            "JUANA_CAMERAS",
            "JUANA_LIGHTING",
            "JUANA_GLTF_EXPORT",
        ],
        "identity_proxy_scope": "talking_bust_only",
        "identity_proxy_cutoff_world_z": 1.18,
        "construction_layers_preserved": True,
    }


def test_approved_source_images_match_recorded_evidence() -> None:
    verified = verify_source_inputs(REPOSITORY_ROOT)

    assert len(verified) == 15
    assert verified[0]["id"] == "juana-master-character-sheet-v3"
    assert {item["id"] for item in verified} >= {
        "face-front",
        "hair-right",
        "outfit-back",
        "juana-sam3d-humanmesh-normalized-reference",
    }


def test_existing_adapter_contract_maps_rig_eyes_jaw_and_initial_targets() -> None:
    adapter = load_base_model_adapter_manifest(ADAPTER_PATH)

    assert adapter.adapter_id == "juana-mpfb-default-bust"
    assert adapter.bones["leftEye"] == "eye.L"
    assert adapter.bones["rightEye"] == "eye.R"
    assert adapter.bones["jaw"] == "jaw"
    assert adapter.bones["head"] == "head"
    assert adapter.bones["upperChest"] == "spine01"
    assert {
        "blink",
        "blinkLeft",
        "blinkRight",
        "aa",
        "ih",
        "ou",
        "ee",
        "oh",
    } <= set(adapter.expression_map)


def test_render_manifest_has_fixed_required_views() -> None:
    manifest = load_json_object(TOOL_ROOT / "render-manifest.json")

    validate_render_manifest(manifest)
    assert manifest["render"]["engine"] == "BLENDER_EEVEE_NEXT"
    assert manifest["render"]["resolution"] == [1024, 1024]
    assert manifest["render"]["canonicalization"] == {
        "strip_metadata": True,
        "rgb_lsb_bits_cleared": 2,
    }
    assert [view["id"] for view in manifest["views"]] == [
        "front",
        "left-profile",
        "right-profile",
        "left-three-quarter",
        "right-three-quarter",
    ]
    assert {tuple(view["target"]) for view in manifest["views"]} == {(0.0, 0.0, 1.5)}
    assert {view["lens_mm"] for view in manifest["views"]} == {80.0}
    assert (
        max(
            sum(coordinate**2 for coordinate in view["camera_location"][:2]) ** 0.5
            for view in manifest["views"]
        )
        <= 1.05
    )
    presentation = manifest["review_presentation"]
    assert presentation["revision"] == "gh-22-clean-production-pass-2"
    assert presentation["crop"] == "head_neck_and_shoulder_hint"
    assert presentation["saved_blend"] == {
        "active_camera": "Camera_front",
        "visible_collections": [
            "_PRODUCTION_BODY",
            "_PRODUCTION_HEAD",
            "_PRODUCTION_HAIR",
            "_PRODUCTION_OUTFIT",
        ],
        "hidden_collections": [
            "_REFERENCE_SAM3D",
            "_REFERENCE_HIGHPOLY",
            "_DONOR_VRM",
            "_RIG",
            "_EXPORT",
        ],
    }
    assert presentation["landmark_overlay"]["enabled"] is True
    assert 0.1 <= presentation["landmark_overlay"]["opacity"] <= 0.4
    assert set(presentation["landmark_overlay"]["landmarks"]) == {
        "eyes",
        "brows",
        "nose_base",
        "mouth_corners",
        "chin",
        "cheekbones",
        "hairline",
    }
    assert all(
        set(panel_points) == {"reference", "render"}
        for panel_points in presentation["landmark_overlay"]["landmarks"].values()
    )


def test_integrity_failure_names_artifact_and_both_digests(tmp_path: Path) -> None:
    path = tmp_path / "asset.bin"
    path.write_bytes(b"wrong")
    actual = hashlib.sha256(b"wrong").hexdigest()
    expected = "a" * 64

    with pytest.raises(IntegrityError) as exc_info:
        verify_file(
            path,
            artifact_id="human-base",
            expected_sha256=expected,
            expected_byte_length=5,
        )

    message = str(exc_info.value)
    assert "human-base" in message
    assert expected in message
    assert actual in message


def test_tree_hash_ignores_runtime_bytecode_and_uses_relative_paths(
    tmp_path: Path,
) -> None:
    (tmp_path / "services").mkdir()
    (tmp_path / "services" / "target.py").write_bytes(b"target")
    (tmp_path / "manifest.toml").write_bytes(b"version = '2.0.16'\n")
    (tmp_path / "__pycache__").mkdir()
    (tmp_path / "__pycache__" / "target.pyc").write_bytes(b"volatile")

    expected = hashlib.sha256()
    for relative_path, contents in (
        ("manifest.toml", b"version = '2.0.16'\n"),
        ("services/target.py", b"target"),
    ):
        expected.update(relative_path.encode())
        expected.update(b"\0")
        expected.update(contents)
        expected.update(b"\0")

    actual, file_count = sha256_tree(tmp_path)

    assert actual == expected.hexdigest()
    assert file_count == 2


def test_provisional_outputs_never_target_final_distribution() -> None:
    paths = provisional_output_paths(REPOSITORY_ROOT)

    assert paths
    assert all("dist/juana" not in path.as_posix() for path in paths.values())
    assert paths["glb"].name == "juana-clean-production-provisional.glb"


def test_json_loader_rejects_non_object(tmp_path: Path) -> None:
    path = tmp_path / "array.json"
    path.write_text(json.dumps([]), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON object"):
        load_json_object(path)


def test_comparison_sheets_have_fixed_layout(tmp_path: Path) -> None:
    references_root = tmp_path / "package"
    renders_root = tmp_path / "renders"
    comparisons_root = tmp_path / "comparisons"
    views = []
    for index, view_id in enumerate(
        (
            "front",
            "left-profile",
            "right-profile",
            "left-three-quarter",
            "right-three-quarter",
        )
    ):
        reference = references_root / "references" / "face" / f"{view_id}.png"
        render = renders_root / f"{view_id}.png"
        reference.parent.mkdir(parents=True, exist_ok=True)
        renders_root.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (512, 512), (20 + index, 30, 40)).save(reference)
        Image.new("RGB", (1024, 1024), (60, 70 + index, 80)).save(render)
        views.append(
            {
                "id": view_id,
                "reference": f"references/face/{view_id}.png",
            }
        )

    outputs = create_comparison_sheets(
        {
            "views": views,
            "review_presentation": {
                "landmark_overlay": {
                    "enabled": True,
                    "opacity": 0.28,
                    "landmarks": {
                        "eyes": {
                            "reference": [[0.4, 0.43], [0.61, 0.43]],
                            "render": [[0.4, 0.35], [0.6, 0.35]],
                        },
                        "brows": {
                            "reference": [[0.4, 0.37], [0.62, 0.37]],
                            "render": [[0.39, 0.27], [0.61, 0.27]],
                        },
                        "nose_base": {
                            "reference": [[0.47, 0.55], [0.54, 0.55]],
                            "render": [[0.47, 0.45], [0.53, 0.45]],
                        },
                        "mouth_corners": {
                            "reference": [[0.43, 0.64], [0.59, 0.64]],
                            "render": [[0.42, 0.53], [0.58, 0.53]],
                        },
                        "chin": {
                            "reference": [[0.51, 0.76]],
                            "render": [[0.5, 0.625]],
                        },
                        "cheekbones": {
                            "reference": [[0.33, 0.5], [0.69, 0.5]],
                            "render": [[0.32, 0.47], [0.68, 0.47]],
                        },
                        "hairline": {
                            "reference": [[0.39, 0.27], [0.65, 0.27]],
                            "render": [[0.36, 0.15], [0.65, 0.15]],
                        },
                    },
                }
            },
        },
        references_root=references_root,
        renders_root=renders_root,
        comparisons_root=comparisons_root,
    )

    assert set(outputs) == {
        "front",
        "left-profile",
        "right-profile",
        "left-three-quarter",
        "right-three-quarter",
        "front-landmark-overlay",
        "review-board",
    }
    with Image.open(outputs["front"]) as comparison:
        assert comparison.size == (2048, 1072)
    with Image.open(outputs["review-board"]) as board:
        assert board.size == (1536, 1152)
    with Image.open(outputs["front-landmark-overlay"]) as overlay:
        assert overlay.size == (2048, 1072)


def test_render_canonicalization_removes_metadata_and_rounding_noise(
    tmp_path: Path,
) -> None:
    first = tmp_path / "first.png"
    second = tmp_path / "second.png"
    metadata = PngInfo()
    metadata.add_text("Date", "volatile")
    Image.new("RGBA", (2, 1), (103, 150, 201, 255)).save(
        first,
        pnginfo=metadata,
    )
    Image.new("RGBA", (2, 1), (101, 151, 200, 255)).save(second)

    canonicalize_render(first)
    canonicalize_render(second)

    assert first.read_bytes() == second.read_bytes()
    with Image.open(first) as canonical:
        assert canonical.info == {}
        assert canonical.getpixel((0, 0)) == (100, 148, 200, 255)
