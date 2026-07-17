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


def test_approved_source_images_match_recorded_evidence() -> None:
    verified = verify_source_inputs(REPOSITORY_ROOT)

    assert len(verified) == 14
    assert verified[0]["id"] == "juana-master-character-sheet-v3"
    assert {item["id"] for item in verified} >= {
        "face-front",
        "hair-right",
        "outfit-back",
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
    assert paths["glb"].name == "juana-bust-provisional.glb"


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
        {"views": views},
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
        "review-board",
    }
    with Image.open(outputs["front"]) as comparison:
        assert comparison.size == (2048, 1072)
    with Image.open(outputs["review-board"]) as board:
        assert board.size == (1536, 1152)


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
