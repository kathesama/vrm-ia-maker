"""Validate the editable Blender checkpoint and its provisional exports."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

import bpy

REQUIRED_OBJECTS = {
    "Juana_Armature": "ARMATURE",
    "Juana_Body": "MESH",
    "Juana_Eye_L": "MESH",
    "Juana_Eye_R": "MESH",
    "Juana_Eyebrows": "MESH",
    "Juana_Eyelashes": "MESH",
    "Juana_Hair_Close_Cut_Base": "MESH",
    "Juana_Hair_Long_Right": "MESH",
    "Juana_Outfit_Inner": "MESH",
    "Juana_Outfit_Jacket": "MESH",
}
REQUIRED_DECORATIVE_OBJECTS = {
    "Juana_Choker",
    "Juana_Choker_Gold_Closure",
    "Juana_Choker_Text",
    "Juana_Necklace",
    "Juana_Gold_Pendant",
    "Juana_Gold_Hoop_L",
    "Juana_Gold_Hoop_R",
}
REQUIRED_BONES = {
    "root",
    "spine05",
    "spine03",
    "spine01",
    "neck03",
    "head",
    "eye.L",
    "eye.R",
    "jaw",
}
REQUIRED_MORPHS = {
    "blink",
    "blinkLeft",
    "blinkRight",
    "aa",
    "ih",
    "ou",
    "ee",
    "oh",
}
REQUIRED_VIEWS = (
    "front",
    "left-profile",
    "right-profile",
    "left-three-quarter",
    "right-three-quarter",
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate the provisional GH-22 Juana Blender checkpoint."
    )
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--renders", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    arguments = bpy.app.driver_namespace.get("juana_validator_arguments")
    if arguments is None:
        import sys

        arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _require_object(name: str, expected_type: str | None = None) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise RuntimeError(f"Required Blender object is missing: {name}.")
    if expected_type is not None and obj.type != expected_type:
        raise RuntimeError(f"Blender object {name} must be {expected_type}; found {obj.type}.")
    return obj


def _validate_body_and_rig() -> dict[str, Any]:
    for name, expected_type in REQUIRED_OBJECTS.items():
        _require_object(name, expected_type)
    for name in REQUIRED_DECORATIVE_OBJECTS:
        _require_object(name)

    body = _require_object("Juana_Body", "MESH")
    armature = _require_object("Juana_Armature", "ARMATURE")
    bone_names = {bone.name for bone in armature.data.bones}
    missing_bones = sorted(REQUIRED_BONES - bone_names)
    if missing_bones:
        raise RuntimeError(f"Required armature bones are missing: {missing_bones}.")

    if body.data.shape_keys is None:
        raise RuntimeError("Juana_Body has no shape keys.")
    key_blocks = body.data.shape_keys.key_blocks
    shape_keys = {key.name for key in key_blocks}
    missing_morphs = sorted(REQUIRED_MORPHS - shape_keys)
    if missing_morphs:
        raise RuntimeError(f"Required Juana morph targets are missing: {missing_morphs}.")
    basis = key_blocks["Basis"]
    morph_max_deltas = {}
    for morph_name in sorted(REQUIRED_MORPHS):
        morph = key_blocks[morph_name]
        max_delta = max(
            (point.co - basis.data[index].co).length for index, point in enumerate(morph.data)
        )
        if max_delta <= 1e-6:
            raise RuntimeError(f"Required morph target has no geometry delta: {morph_name}.")
        morph_max_deltas[morph_name] = max_delta

    armature_modifiers = [
        modifier
        for modifier in body.modifiers
        if modifier.type == "ARMATURE" and modifier.object == armature
    ]
    if not armature_modifiers:
        raise RuntimeError("Juana_Body is not skinned to Juana_Armature.")
    jaw_group = body.vertex_groups.get("jaw")
    if jaw_group is None:
        raise RuntimeError("Juana_Body has no jaw vertex group.")
    jaw_weighted_vertices = sum(
        1
        for vertex in body.data.vertices
        for membership in vertex.groups
        if membership.group == jaw_group.index and membership.weight > 0.0
    )
    if jaw_weighted_vertices == 0:
        raise RuntimeError("Juana_Body jaw vertex group has no weighted vertices.")

    expected_eye_parents = {
        "Juana_Eye_L": "eye.L",
        "Juana_Eye_R": "eye.R",
    }
    for eye_name, bone_name in expected_eye_parents.items():
        eye = _require_object(eye_name, "MESH")
        if eye.parent != armature or eye.parent_type != "BONE" or eye.parent_bone != bone_name:
            raise RuntimeError(f"{eye_name} must be a distinct object parented to {bone_name}.")

    return {
        "body_vertices": len(body.data.vertices),
        "body_polygons": len(body.data.polygons),
        "armature_bones": len(armature.data.bones),
        "required_bones": sorted(REQUIRED_BONES),
        "required_morphs": sorted(REQUIRED_MORPHS),
        "morph_max_deltas": morph_max_deltas,
        "jaw_weighted_vertices": jaw_weighted_vertices,
        "separate_eyes": sorted(expected_eye_parents),
    }


def _validate_jaw_action() -> dict[str, Any]:
    armature = _require_object("Juana_Armature", "ARMATURE")
    action = bpy.data.actions.get("Juana_Jaw_Articulation")
    if action is None:
        raise RuntimeError("Juana_Jaw_Articulation action is missing.")
    if armature.animation_data is None:
        armature.animation_data_create()
    armature.animation_data.action = action

    scene = bpy.context.scene
    scene.frame_set(1)
    closed_angle = float(armature.pose.bones["jaw"].rotation_euler.x)
    scene.frame_set(12)
    open_angle = float(armature.pose.bones["jaw"].rotation_euler.x)
    scene.frame_set(24)
    restored_angle = float(armature.pose.bones["jaw"].rotation_euler.x)
    scene.frame_set(1)

    if abs(open_angle - closed_angle) < 0.1:
        raise RuntimeError("Jaw action does not visibly articulate at frame 12.")
    if abs(restored_angle - closed_angle) > 1e-4:
        raise RuntimeError("Jaw action does not return to its closed pose at frame 24.")

    keyframes = sorted(
        {int(point.co.x) for curve in action.fcurves for point in curve.keyframe_points}
    )
    if keyframes != [1, 12, 24]:
        raise RuntimeError(
            f"Jaw action must use deterministic keyframes [1, 12, 24]; got {keyframes}."
        )
    return {
        "action": action.name,
        "keyframes": keyframes,
        "closed_angle_radians": closed_angle,
        "open_angle_radians": open_angle,
        "restored_angle_radians": restored_angle,
    }


def _relative(path: Path, repository_root: Path) -> str:
    return path.resolve().relative_to(repository_root.resolve()).as_posix()


def _validate_adapter(path: Path, repository_root: Path) -> dict[str, Any]:
    adapter = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(adapter, dict):
        raise RuntimeError(f"Base adapter must be a JSON object: {path}.")
    armature = _require_object("Juana_Armature", "ARMATURE")
    body = _require_object("Juana_Body", "MESH")
    bone_names = {bone.name for bone in armature.data.bones}
    shape_keys = {key.name for key in body.data.shape_keys.key_blocks}

    adapter_bones = set(adapter["bones"].values())
    missing_bones = sorted(adapter_bones - bone_names)
    if missing_bones:
        raise RuntimeError(f"Base adapter references missing bones: {missing_bones}.")
    adapter_morphs = {
        binding["shape_key"]
        for bindings in adapter["expression_map"].values()
        for binding in bindings
    }
    missing_morphs = sorted(adapter_morphs - shape_keys)
    if missing_morphs:
        raise RuntimeError(f"Base adapter references missing morph targets: {missing_morphs}.")
    if body.get("base_asset_id") != adapter["base_asset_id"]:
        raise RuntimeError("Base adapter asset identifier does not match Juana_Body.")
    if armature.get("adapter_id") != adapter["adapter_id"]:
        raise RuntimeError("Base adapter identifier does not match Juana_Armature.")
    return {
        "path": _relative(path, repository_root),
        "adapter_id": adapter["adapter_id"],
        "base_asset_id": adapter["base_asset_id"],
        "mapped_bones": len(adapter["bones"]),
        "mapped_expressions": sorted(adapter["expression_map"]),
    }


def _validate_cameras_and_renders(
    renders_root: Path,
    repository_root: Path,
) -> list[dict[str, Any]]:
    results = []
    for view_id in REQUIRED_VIEWS:
        _require_object(f"Camera_{view_id}", "CAMERA")
        render_path = renders_root / f"{view_id}.png"
        if not render_path.is_file():
            raise RuntimeError(f"Required deterministic render is missing: {render_path}.")
        image = bpy.data.images.load(str(render_path), check_existing=False)
        try:
            dimensions = [int(image.size[0]), int(image.size[1])]
        finally:
            bpy.data.images.remove(image)
        if dimensions != [1024, 1024]:
            raise RuntimeError(f"Render {render_path} must be 1024x1024; got {dimensions}.")
        results.append(
            {
                "view": view_id,
                "path": _relative(render_path, repository_root),
                "dimensions": dimensions,
                "byte_length": render_path.stat().st_size,
            }
        )
    return results


def _validate_glb_container(path: Path, repository_root: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Provisional GLB is missing: {path}.")
    with path.open("rb") as source:
        header = source.read(12)
    if len(header) != 12:
        raise RuntimeError(f"GLB header is truncated: {path}.")
    magic, version, declared_length = struct.unpack("<4sII", header)
    actual_length = path.stat().st_size
    if magic != b"glTF" or version != 2 or declared_length != actual_length:
        raise RuntimeError(
            "Invalid GLB container header: "
            f"magic={magic!r}, version={version}, "
            f"declared_length={declared_length}, actual_length={actual_length}."
        )
    return {
        "path": _relative(path, repository_root),
        "version": version,
        "byte_length": actual_length,
    }


def main() -> None:
    args = _arguments()
    report = {
        "schema_version": "1.0",
        "status": "passed",
        "blender_version": bpy.app.version_string,
        "scene": _validate_body_and_rig(),
        "adapter": _validate_adapter(args.adapter, args.repo_root),
        "jaw": _validate_jaw_action(),
        "renders": _validate_cameras_and_renders(args.renders, args.repo_root),
        "glb_container": _validate_glb_container(args.glb, args.repo_root),
        "provisional_boundary": {
            "visual_canon_approved": False,
            "final_vrm": False,
            "next_gate": "Kathy visual review",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("GH22_BLENDER_VALIDATION_PASSED")


if __name__ == "__main__":
    main()
