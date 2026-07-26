"""Reopen and validate the clean GH-22 Juana production checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix

REQUIRED_STANDARD_RENDERS = (
    "front",
    "left-profile",
    "right-profile",
    "left-three-quarter",
    "right-three-quarter",
)
REQUIRED_DIAGNOSTIC_RENDERS = (
    "wireframe",
    "sam3d-reference-body",
    "production-body",
    "highpoly-reference-head",
    "production-head",
)
REQUIRED_RIG_BONES = {
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


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--glb", type=Path, required=True)
    parser.add_argument("--renders", type=Path, required=True)
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--repo-root", type=Path, required=True)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _triangle_count(obj: bpy.types.Object) -> int:
    if obj.type != "MESH":
        return 0
    return sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def _matrix_is_identity(matrix: Matrix, tolerance: float = 1e-6) -> bool:
    identity = Matrix.Identity(4)
    return all(
        math.isclose(matrix[row][column], identity[row][column], abs_tol=tolerance)
        for row in range(4)
        for column in range(4)
    )


def _inventory_object(obj: bpy.types.Object) -> dict[str, Any]:
    armature_modifier = next(
        (modifier for modifier in obj.modifiers if modifier.type == "ARMATURE"),
        None,
    )
    value: dict[str, Any] = {
        "name": obj.name,
        "type": obj.type,
        "role": obj.get("source_role", "unclassified"),
        "collections": sorted(collection.name for collection in obj.users_collection),
        "exportable": bool(obj.get("exportable", False)),
        "renderable": bool(obj.get("renderable", False)),
        "root_transform_applied": bool(obj.get("root_transform_applied", False)),
    }
    if obj.type == "MESH":
        value["vertices"] = len(obj.data.vertices)
        value["triangles"] = _triangle_count(obj)
    if armature_modifier is not None and armature_modifier.object is not None:
        value["skinned_to"] = armature_modifier.object.name
    return value


def _validate_scene_inventory(repository_root: Path) -> dict[str, Any]:
    sys.path.insert(0, str(repository_root))
    from tools.juana_bust.production_gate import validate_scene_inventory

    inventory = {
        "collections": sorted(collection.name for collection in bpy.data.collections),
        "objects": [_inventory_object(obj) for obj in bpy.context.scene.objects],
    }
    gate_result = validate_scene_inventory(inventory)

    for name in ("Juana_Production_Body", "Juana_Production_Head", "Juana_Production_Rig"):
        obj = bpy.data.objects.get(name)
        if obj is None or not _matrix_is_identity(obj.matrix_world):
            raise RuntimeError(f"Production root transform is not identity: {name}.")

    armature = bpy.data.objects["Juana_Production_Rig"]
    bone_names = {bone.name for bone in armature.data.bones}
    missing_bones = sorted(REQUIRED_RIG_BONES - bone_names)
    if missing_bones:
        raise RuntimeError(f"Production rig is missing required bones: {missing_bones}.")
    if armature.animation_data is None or armature.animation_data.action is None:
        raise RuntimeError("Production rig is missing the functional jaw action.")

    eyes = [
        obj
        for obj in bpy.context.scene.objects
        if obj.get("source_role") == "production_eye"
    ]
    if len(eyes) != 2:
        raise RuntimeError(f"Expected two separate production eyes; found {len(eyes)}.")
    if not all(obj.parent == armature and obj.parent_type == "BONE" for obj in eyes):
        raise RuntimeError("Production eyes must be parented to rig eye bones.")

    sam = bpy.data.objects.get("SAM3D_HumanMesh_Reference")
    highpoly = bpy.data.objects.get("Juana_Highpoly_Bust_Reference")
    if sam is None or (len(sam.data.vertices), _triangle_count(sam)) != (18439, 36874):
        raise RuntimeError("Normalized SAM 3D reference topology is invalid.")
    if highpoly is None or (len(highpoly.data.vertices), _triangle_count(highpoly)) != (
        924342,
        1363714,
    ):
        raise RuntimeError("High-poly bust reference topology is invalid.")
    if not bool(highpoly.get("immutable_reference")):
        raise RuntimeError("High-poly bust reference is not marked immutable.")

    for collection_name in ("_REFERENCE_SAM3D", "_REFERENCE_HIGHPOLY", "_DONOR_VRM"):
        collection = bpy.data.collections[collection_name]
        if not collection.hide_viewport:
            raise RuntimeError(f"Saved donor collection must be hidden: {collection_name}.")
        for obj in collection.objects:
            if bool(obj.get("exportable")) or bool(obj.get("renderable")):
                raise RuntimeError(f"Donor object is active in production: {obj.name}.")

    return {
        "gate_result": gate_result,
        "required_bones": sorted(REQUIRED_RIG_BONES),
        "bone_count": len(bone_names),
        "eye_objects": sorted(obj.name for obj in eyes),
        "sam3d_reference": {
            "vertices": len(sam.data.vertices),
            "triangles": _triangle_count(sam),
        },
        "highpoly_reference": {
            "vertices": len(highpoly.data.vertices),
            "triangles": _triangle_count(highpoly),
            "immutable": True,
        },
    }


def _validate_fit_report(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Production fit report is missing: {path}.")
    report = json.loads(path.read_text(encoding="utf-8"))
    from tools.juana_bust.production_gate import validate_visual_profile

    visual_profile = validate_visual_profile(report)
    required_methods = {
        report["body_fit"]["method"],
        report["highpoly_alignment"]["method"],
        report["face_cage"]["method"],
        report["masked_shrinkwrap"]["method"],
        report["texture_bake"]["method"],
    }
    expected_methods = {
        "sam3d_normalized_approved_profile_cage_fit",
        "explicit_eye_landmark_similarity_transform",
        "landmark_driven_masked_cage_deformation",
        "controlled_masked_shrinkwrap",
        "nearest_face_uv_transfer_then_selected_to_active_diffuse_bake",
    }
    if required_methods != expected_methods:
        raise RuntimeError(f"Production fit methods are incomplete: {required_methods}.")
    shrinkwrap = report["masked_shrinkwrap"]
    if shrinkwrap["vertex_group"] != "Juana_Highpoly_Face_Mask":
        raise RuntimeError("Masked shrinkwrap did not use the dedicated face mask.")
    face_filter = report["highpoly_alignment"].get("face_surface_filter", {})
    if (
        face_filter.get("method") != "front_surface_and_base_color_skin_filter"
        or int(face_filter.get("retained_faces", 0)) < 1000
    ):
        raise RuntimeError("High-poly face surface filtering evidence is incomplete.")
    texture_path = Path(report["texture_bake"]["output"])
    if not texture_path.is_file() or _sha256(texture_path) != report["texture_bake"]["sha256"]:
        raise RuntimeError("High-poly texture-bake evidence is missing or modified.")
    return {
        "path": str(path),
        "methods": sorted(required_methods),
        "texture_bake_sha256": report["texture_bake"]["sha256"],
        "texture_bake_direct_application": report["texture_bake"][
            "baked_image_directly_applied"
        ],
        "visual_profile": visual_profile,
    }


def _validate_render(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Required render is missing: {path}.")
    image = bpy.data.images.load(str(path), check_existing=False)
    dimensions = tuple(image.size)
    if dimensions != (1024, 1024):
        raise RuntimeError(f"Render {path} must be 1024x1024; got {dimensions}.")
    width, height = dimensions
    sampled = []
    for y in range(32, height, 64):
        for x in range(32, width, 64):
            pixel_index = (y * width + x) * 4
            sampled.append(
                sum(float(image.pixels[pixel_index + channel]) for channel in range(3))
                / 3.0
            )
    dynamic_range = max(sampled) - min(sampled)
    bpy.data.images.remove(image)
    if dynamic_range < 0.03:
        raise RuntimeError(f"Render appears blank or uniform: {path}.")
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "byte_length": path.stat().st_size,
        "dimensions": list(dimensions),
        "sampled_dynamic_range": dynamic_range,
    }


def _validate_renders(root: Path) -> list[dict[str, Any]]:
    return [
        _validate_render(root / f"{name}.png")
        for name in (*REQUIRED_STANDARD_RENDERS, *REQUIRED_DIAGNOSTIC_RENDERS)
    ]


def _validate_glb(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"Provisional GLB is missing: {path}.")
    with path.open("rb") as handle:
        header = handle.read(12)
    if len(header) != 12:
        raise RuntimeError(f"GLB header is truncated: {path}.")
    magic, version, declared_length = struct.unpack("<4sII", header)
    if magic != b"glTF" or version != 2 or declared_length != path.stat().st_size:
        raise RuntimeError(
            f"Invalid GLB header: magic={magic}, version={version}, "
            f"declared={declared_length}, actual={path.stat().st_size}."
        )
    return {
        "path": str(path),
        "sha256": _sha256(path),
        "byte_length": path.stat().st_size,
        "version": version,
    }


def main() -> None:
    args = _arguments()
    fit_report_path = args.report.parent / "production-fit-report.json"
    report = {
        "schema_version": "1.0",
        "status": "passed",
        "scene": _validate_scene_inventory(args.repo_root),
        "fit": _validate_fit_report(fit_report_path),
        "renders": _validate_renders(args.renders),
        "glb": _validate_glb(args.glb),
        "provisional_boundary": {
            "visual_canon_approved": False,
            "final_vrm": False,
            "next_gate": "Kathy visual and topology review",
        },
    }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print("GH22_CLEAN_PRODUCTION_VALIDATION_PASSED")


if __name__ == "__main__":
    main()
