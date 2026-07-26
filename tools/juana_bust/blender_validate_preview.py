"""Validate the editable Blender checkpoint and its provisional exports."""

from __future__ import annotations

import argparse
import json
import struct
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

REQUIRED_OBJECTS = {
    "Juana_Armature": "ARMATURE",
    "Juana_Body": "MESH",
    "Juana_Eye_L": "MESH",
    "Juana_Eye_R": "MESH",
    "Juana_Iris_Overlay_L": "MESH",
    "Juana_Iris_Overlay_R": "MESH",
    "Juana_Eyebrows": "MESH",
    "Juana_Eyelashes": "MESH",
    "Juana_Hair_Close_Cut_Base": "MESH",
    "Juana_Hair_Long_Right": "MESH",
    "Juana_Outfit_Inner": "MESH",
    "Juana_Outfit_Jacket": "MESH",
    "Juana_Hunyuan_Identity_Proxy": "MESH",
    "Juana_Meta_MHR_Body_Calibration_Surface": "MESH",
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
REVIEW_COLLECTION = "JUANA_REVIEW"
TECHNICAL_COLLECTION = "JUANA_TECHNICAL"
CAMERA_COLLECTION = "JUANA_CAMERAS"
LIGHTING_COLLECTION = "JUANA_LIGHTING"
EXPORT_COLLECTION = "JUANA_GLTF_EXPORT"
REVIEW_VISIBLE_OBJECTS = {
    "Juana_Hunyuan_Identity_Proxy",
    "Juana_Iris_Overlay_L",
    "Juana_Iris_Overlay_R",
}
PROXY_BUST_CUTOFF_WORLD_Z = 1.18


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


def _world_bbox_dimensions(obj: bpy.types.Object) -> Vector:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return Vector(
        (
            max(corner.x for corner in corners) - min(corner.x for corner in corners),
            max(corner.y for corner in corners) - min(corner.y for corner in corners),
            max(corner.z for corner in corners) - min(corner.z for corner in corners),
        )
    )


def _large_mesh_component_count(mesh: bpy.types.Mesh) -> int:
    adjacency = [set() for _ in mesh.vertices]
    for edge in mesh.edges:
        start, end = edge.vertices
        adjacency[start].add(end)
        adjacency[end].add(start)
    visited: set[int] = set()
    large_components = 0
    for start in range(len(mesh.vertices)):
        if start in visited:
            continue
        pending = [start]
        visited.add(start)
        size = 0
        while pending:
            index = pending.pop()
            size += 1
            for neighbor in adjacency[index]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if size >= 20:
            large_components += 1
    return large_components


def _require_collection(name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.get(name)
    if collection is None:
        raise RuntimeError(f"Required Blender collection is missing: {name}.")
    return collection


def _validate_saved_viewport_presentation() -> dict[str, Any]:
    review_collection = _require_collection(REVIEW_COLLECTION)
    technical_collection = _require_collection(TECHNICAL_COLLECTION)
    camera_collection = _require_collection(CAMERA_COLLECTION)
    lighting_collection = _require_collection(LIGHTING_COLLECTION)
    export_collection = _require_collection(EXPORT_COLLECTION)

    review_names = {obj.name for obj in review_collection.objects}
    if review_names != REVIEW_VISIBLE_OBJECTS:
        raise RuntimeError(
            "The saved review collection must contain only the visible identity "
            f"surface and iris overlays; found {sorted(review_names)}."
        )
    visible_review_objects = [
        obj.name for obj in review_collection.objects if not obj.hide_get()
    ]
    if set(visible_review_objects) != REVIEW_VISIBLE_OBJECTS:
        raise RuntimeError(
            "Every saved review object must be visible in the viewport; found "
            f"{sorted(visible_review_objects)}."
        )

    visible_technical_objects = [
        obj.name for obj in technical_collection.objects if not obj.hide_get()
    ]
    if visible_technical_objects:
        raise RuntimeError(
            "Technical Juana layers must be hidden in the saved viewport; found "
            f"{sorted(visible_technical_objects)}."
        )
    visible_cameras = [obj.name for obj in camera_collection.objects if not obj.hide_get()]
    if visible_cameras:
        raise RuntimeError(
            f"Review cameras must be hidden in the saved viewport: {sorted(visible_cameras)}."
        )
    visible_lights = [obj.name for obj in lighting_collection.objects if not obj.hide_get()]
    if visible_lights:
        raise RuntimeError(
            f"Review lights must be hidden in the saved viewport: {sorted(visible_lights)}."
        )
    visible_export_helpers = [
        obj.name for obj in export_collection.objects if not obj.hide_get()
    ]
    if visible_export_helpers:
        raise RuntimeError(
            "GLB export helpers must be hidden in the saved viewport: "
            f"{sorted(visible_export_helpers)}."
        )

    selected_objects = [obj.name for obj in bpy.context.scene.objects if obj.select_get()]
    if selected_objects:
        raise RuntimeError(
            f"The saved review scene must not contain selected objects: {selected_objects}."
        )
    if bpy.context.scene.camera is None or bpy.context.scene.camera.name != "Camera_front":
        raise RuntimeError("The saved review scene must use Camera_front as its active camera.")

    viewport_states = [
        area.spaces.active.region_3d.view_perspective
        for screen in bpy.data.screens
        for area in screen.areas
        if area.type == "VIEW_3D"
    ]
    if viewport_states and any(state != "CAMERA" for state in viewport_states):
        raise RuntimeError(
            "Every saved 3D viewport must open in the active front camera; found "
            f"{viewport_states}."
        )

    identity_proxy = _require_object("Juana_Hunyuan_Identity_Proxy", "MESH")
    minimum_world_z = min(
        (identity_proxy.matrix_world @ vertex.co).z
        for vertex in identity_proxy.data.vertices
    )
    if minimum_world_z < PROXY_BUST_CUTOFF_WORLD_Z - 1e-6:
        raise RuntimeError(
            "The visible identity proxy still contains out-of-scope lower-body "
            f"geometry: minimum world Z is {minimum_world_z:.6f}."
        )
    if identity_proxy.get("presentation_scope") != "talking_bust_only":
        raise RuntimeError("The visible identity proxy is not marked as a talking-bust surface.")

    return {
        "active_camera": bpy.context.scene.camera.name,
        "viewport_states": viewport_states,
        "visible_review_objects": sorted(visible_review_objects),
        "hidden_technical_object_count": len(technical_collection.objects),
        "hidden_camera_count": len(camera_collection.objects),
        "hidden_light_count": len(lighting_collection.objects),
        "hidden_export_helper_count": len(export_collection.objects),
        "identity_proxy_minimum_world_z": minimum_world_z,
        "selected_objects": selected_objects,
    }


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
    if "identity_likeness_pass_3" not in shape_keys:
        raise RuntimeError("Juana_Body is missing the third likeness-pass shape key.")
    if body.get("likeness_revision") != "gh-22-likeness-pass-3":
        raise RuntimeError("Juana_Body is not marked as the third likeness revision.")
    if body.get("likeness_transfer_method") != "manual_landmark_calibration":
        raise RuntimeError("Juana_Body is missing its landmark-calibration boundary.")
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
    eye_width_height_ratios = {}
    for eye_name, bone_name in expected_eye_parents.items():
        eye = _require_object(eye_name, "MESH")
        if eye.parent != armature or eye.parent_type != "BONE" or eye.parent_bone != bone_name:
            raise RuntimeError(f"{eye_name} must be a distinct object parented to {bone_name}.")
        dimensions = _world_bbox_dimensions(eye)
        ratio = dimensions.x / dimensions.z
        if ratio < 1.35:
            raise RuntimeError(
                f"{eye_name} must use a narrow almond proportion; width/height is {ratio:.3f}."
            )
        if eye.get("appearance") != "narrow_almond_amber":
            raise RuntimeError(f"{eye_name} is missing its approved provisional appearance.")
        eye_width_height_ratios[eye_name] = ratio

    expected_iris_parents = {
        "Juana_Iris_Overlay_L": "eye.L",
        "Juana_Iris_Overlay_R": "eye.R",
    }
    for overlay_name, bone_name in expected_iris_parents.items():
        overlay = _require_object(overlay_name, "MESH")
        if (
            overlay.parent != armature
            or overlay.parent_type != "BONE"
            or overlay.parent_bone != bone_name
        ):
            raise RuntimeError(f"{overlay_name} must be parented to {bone_name}.")
        if overlay.get("appearance") != "warm_amber_brown":
            raise RuntimeError(f"{overlay_name} must use the warm amber-brown appearance.")

    brows = _require_object("Juana_Eyebrows", "MESH")
    if brows.get("appearance") != "thick_dark_strong_arch":
        raise RuntimeError("Juana_Eyebrows must use the third-pass thick shaped brow.")
    long_hair = _require_object("Juana_Hair_Long_Right", "MESH")
    flowing_hair_clump_count = _large_mesh_component_count(long_hair.data)
    if (
        flowing_hair_clump_count < 12
        or long_hair.get("flowing_clump_count") != flowing_hair_clump_count
    ):
        raise RuntimeError("Juana long hair must include at least twelve connected mesh clumps.")
    undercut = _require_object("Juana_Hair_Close_Cut_Base", "MESH")
    if undercut.get("construction") != "anatomical-left close-cut undercut patch":
        raise RuntimeError("Juana undercut must remain on the anatomical-left side.")
    if body.active_material is None or body.active_material.get("approved_tone") != (
        "warm_golden_brown"
    ):
        raise RuntimeError("Juana skin must use the provisional warm golden-brown tone.")
    if armature.show_in_front or not armature.hide_render:
        raise RuntimeError("Rig controls must be hidden from visual-review renders.")

    identity_proxy = _require_object("Juana_Hunyuan_Identity_Proxy", "MESH")
    if (
        identity_proxy.parent != armature
        or identity_proxy.parent_type != "BONE"
        or identity_proxy.parent_bone != "spine01"
    ):
        raise RuntimeError("Juana identity proxy must be attached to spine01.")
    if identity_proxy.get("status") != "provisional_visual_proxy":
        raise RuntimeError("Juana identity proxy is missing its provisional boundary.")
    if identity_proxy.get("production_topology") is not False:
        raise RuntimeError("Juana identity proxy must not be classified as production topology.")
    if identity_proxy.get("ai_generated") is not True:
        raise RuntimeError("Juana identity proxy must retain its AI-generated disclosure.")
    if len(identity_proxy.data.loop_triangles) > 400_000:
        raise RuntimeError("Juana identity proxy exceeds the provisional triangle budget.")
    if identity_proxy.get("source_sha256") != (
        "ead2c523ff3c44a57cf79527c3f439443f6f077067735a90c7efbb7065525364"
    ):
        raise RuntimeError("Juana identity proxy source digest does not match its evidence.")
    if identity_proxy.get("likeness_revision") != "gh-22-likeness-pass-4":
        raise RuntimeError("Juana identity proxy is not marked as the fourth likeness pass.")
    if identity_proxy.get("visible_surface") != "full_bust_identity_surface":
        raise RuntimeError("Juana identity proxy must retain its clean full-bust review surface.")

    body_calibration = _require_object(
        "Juana_Meta_MHR_Body_Calibration_Surface",
        "MESH",
    )
    if body_calibration.get("source_sha256") != (
        "8c7afc60df553b66e1cc3143fc2c04878475e97433d9d6af190393f48eec9ccb"
    ):
        raise RuntimeError("Meta MHR body calibration digest does not match its evidence.")
    if body_calibration.get("production_base") is not False:
        raise RuntimeError("Meta MHR body calibration must not replace the MPFB production base.")
    if body_calibration.get("face_likeness_source") is not False:
        raise RuntimeError(
            "Meta MHR body calibration must not be used as the face identity source."
        )
    if not body_calibration.hide_render:
        raise RuntimeError("Meta MHR calibration body must remain hidden in review renders.")
    if body_calibration.get("visible_use") != "hidden_body_and_rig_calibration_only":
        raise RuntimeError("Meta MHR calibration must remain a hidden technical reference.")

    choker = _require_object("Juana_Choker")
    if choker.get("construction") != "surface-fitted black JUANA IA choker":
        raise RuntimeError("Juana choker must use the surface-fitted construction.")
    for accessory_name in ("Juana_Necklace", "Juana_Gold_Pendant"):
        accessory = _require_object(accessory_name)
        if (
            accessory.parent != armature
            or accessory.parent_type != "BONE"
            or accessory.parent_bone != "spine01"
        ):
            raise RuntimeError(f"{accessory_name} must be attached to spine01.")

    return {
        "body_vertices": len(body.data.vertices),
        "body_polygons": len(body.data.polygons),
        "armature_bones": len(armature.data.bones),
        "required_bones": sorted(REQUIRED_BONES),
        "required_morphs": sorted(REQUIRED_MORPHS),
        "morph_max_deltas": morph_max_deltas,
        "jaw_weighted_vertices": jaw_weighted_vertices,
        "separate_eyes": sorted(expected_eye_parents),
        "functional_iris_overlays": sorted(expected_iris_parents),
        "base_likeness_revision": body.get("likeness_revision"),
        "checkpoint_likeness_revision": identity_proxy.get("likeness_revision"),
        "eye_width_height_ratios": eye_width_height_ratios,
        "eyebrow_appearance": brows.get("appearance"),
        "skin_tone": body.active_material.get("approved_tone"),
        "flowing_hair_clump_count": flowing_hair_clump_count,
        "rig_controls_hidden": True,
        "identity_proxy": {
            "object": identity_proxy.name,
            "vertices": len(identity_proxy.data.vertices),
            "triangles": len(identity_proxy.data.loop_triangles),
            "parent_bone": identity_proxy.parent_bone,
            "ai_generated": True,
            "production_topology": False,
            "likeness_revision": identity_proxy.get("likeness_revision"),
            "visible_surface": identity_proxy.get("visible_surface"),
        },
        "body_calibration": {
            "object": body_calibration.name,
            "vertices": len(body_calibration.data.vertices),
            "source_sha256": body_calibration.get("source_sha256"),
            "production_base": False,
            "hidden_from_review": True,
        },
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
        camera = _require_object(f"Camera_{view_id}", "CAMERA")
        horizontal_distance = (camera.location.x**2 + camera.location.y**2) ** 0.5
        if horizontal_distance > 1.05 + 1e-6 or abs(camera.location.z - 1.5) > 1e-6:
            raise RuntimeError(f"Camera_{view_id} does not use the fixed head crop.")
        if (
            camera.get("review_crop") != "head_neck_and_shoulder_hint"
            or abs(float(camera.get("target_height", 0.0)) - 1.5) > 1e-6
        ):
            raise RuntimeError(f"Camera_{view_id} is missing its review framing contract.")
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
        "saved_viewport_presentation": _validate_saved_viewport_presentation(),
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
