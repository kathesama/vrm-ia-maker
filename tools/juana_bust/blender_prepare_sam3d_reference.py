"""Isolate and normalize the static SAM 3D HumanMesh donor."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Vector


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-byte-length", type=int, required=True)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in tuple(bpy.data.collections):
        bpy.data.collections.remove(collection)


def _triangle_count(obj: bpy.types.Object) -> int:
    return sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def _local_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    coordinates = [vertex.co for vertex in obj.data.vertices]
    return (
        Vector(tuple(min(coordinate[index] for coordinate in coordinates) for index in range(3))),
        Vector(tuple(max(coordinate[index] for coordinate in coordinates) for index in range(3))),
    )


def _matrix_is_identity(matrix: Matrix, tolerance: float = 1e-6) -> bool:
    return all(
        math.isclose(matrix[row][column], Matrix.Identity(4)[row][column], abs_tol=tolerance)
        for row in range(4)
        for column in range(4)
    )


def _matrix_rows(matrix: Matrix) -> list[list[float]]:
    return [[float(matrix[row][column]) for column in range(4)] for row in range(4)]


def _write_report(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = _arguments()
    if not args.source.is_file():
        raise RuntimeError(f"SAM 3D source is missing: {args.source}.")
    actual_sha256 = _sha256(args.source)
    actual_byte_length = args.source.stat().st_size
    if actual_sha256 != args.expected_sha256 or actual_byte_length != args.expected_byte_length:
        raise RuntimeError(
            "SAM 3D source integrity mismatch: "
            f"expected sha256={args.expected_sha256}, bytes={args.expected_byte_length}; "
            f"actual sha256={actual_sha256}, bytes={actual_byte_length}."
        )

    _clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(args.source))
    imported_meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    human_candidates = [obj for obj in imported_meshes if obj.name == "HumanMesh"]
    if len(human_candidates) != 1:
        summary = sorted(obj.name for obj in imported_meshes)
        raise RuntimeError(
            "Expected exactly one SAM 3D HumanMesh; "
            f"found {len(human_candidates)} in {summary[:20]}."
        )

    human = human_candidates[0]
    source_mesh_names = sorted(obj.name for obj in imported_meshes)
    source_matrix = human.matrix_world.copy()
    source_vertices = len(human.data.vertices)
    source_triangles = _triangle_count(human)
    if (source_vertices, source_triangles) != (18439, 36874):
        raise RuntimeError(
            "Unexpected SAM 3D HumanMesh topology: "
            f"vertices={source_vertices}, triangles={source_triangles}."
        )
    if human.data.shape_keys is not None:
        raise RuntimeError("SAM 3D HumanMesh unexpectedly contains shape keys.")
    if any(modifier.type == "ARMATURE" for modifier in human.modifiers):
        raise RuntimeError("SAM 3D HumanMesh unexpectedly contains an armature modifier.")

    human.data.transform(source_matrix)
    human.parent = None
    human.matrix_world = Matrix.Identity(4)
    source_minimum, source_maximum = _local_bounds(human)
    horizontal_center = Vector(
        (
            (source_minimum.x + source_maximum.x) * 0.5,
            (source_minimum.y + source_maximum.y) * 0.5,
            0.0,
        )
    )
    normalization = Matrix.Translation(
        (-horizontal_center.x, -horizontal_center.y, -source_minimum.z)
    )
    human.data.transform(normalization)
    human.matrix_world = Matrix.Identity(4)
    human.data.update()

    for obj in tuple(bpy.context.scene.objects):
        if obj != human:
            bpy.data.objects.remove(obj, do_unlink=True)
    for collection in tuple(human.users_collection):
        collection.objects.unlink(human)
    reference_collection = bpy.data.collections.new("_REFERENCE_SAM3D")
    bpy.context.scene.collection.children.link(reference_collection)
    reference_collection.objects.link(human)

    human.name = "SAM3D_HumanMesh_Reference"
    human.data.name = "SAM3D_HumanMesh_Reference_Mesh"
    human.hide_render = True
    human["source_role"] = "reference_sam3d"
    human["source_sha256"] = actual_sha256
    human["production_geometry"] = False
    human["exportable"] = False
    human["root_transform_applied"] = True
    human["normalization"] = "baked_world_matrix_centered_xy_feet_z0"

    normalized_minimum, normalized_maximum = _local_bounds(human)
    if not _matrix_is_identity(human.matrix_world):
        raise RuntimeError("Normalized SAM 3D HumanMesh root transform is not identity.")
    if abs(normalized_minimum.z) > 1e-6:
        raise RuntimeError(
            f"Normalized SAM 3D HumanMesh feet are not on Z=0: {normalized_minimum.z}."
        )
    normalized_center = Vector(
        (
            (normalized_minimum.x + normalized_maximum.x) * 0.5,
            (normalized_minimum.y + normalized_maximum.y) * 0.5,
            0.0,
        )
    )
    if normalized_center.length > 1e-6:
        raise RuntimeError(
            f"Normalized SAM 3D HumanMesh is not horizontally centered: {tuple(normalized_center)}."
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    human.hide_set(False)
    human.select_set(True)
    bpy.context.view_layer.objects.active = human
    bpy.ops.export_scene.gltf(
        filepath=str(args.output),
        export_format="GLB",
        use_selection=True,
        export_extras=True,
        export_yup=True,
        export_apply=True,
    )

    output_sha256 = _sha256(args.output)
    output_byte_length = args.output.stat().st_size
    report = {
        "schema_version": "1.0",
        "status": "passed",
        "source": {
            "path": str(args.source),
            "sha256": actual_sha256,
            "byte_length": actual_byte_length,
            "imported_mesh_object_count": len(imported_meshes),
            "selected_mesh": "HumanMesh",
            "auxiliary_mesh_objects_excluded": len(imported_meshes) - 1,
            "sample_auxiliary_mesh_names": [
                name for name in source_mesh_names if name != "HumanMesh"
            ][:12],
            "matrix_world": _matrix_rows(source_matrix),
            "bounds_min": list(source_minimum),
            "bounds_max": list(source_maximum),
        },
        "normalization": {
            "translation": [
                -horizontal_center.x,
                -horizontal_center.y,
                -source_minimum.z,
            ],
            "root_transform_applied": True,
            "horizontal_centered": True,
            "feet_on_ground": True,
            "bounds_min": list(normalized_minimum),
            "bounds_max": list(normalized_maximum),
        },
        "derived_reference": {
            "path": str(args.output),
            "sha256": output_sha256,
            "byte_length": output_byte_length,
            "mesh_count": 1,
            "mesh_name": human.name,
            "vertices": source_vertices,
            "triangles": source_triangles,
            "armatures": 0,
            "shape_keys": 0,
            "production_geometry": False,
            "direct_final_export_allowed": False,
        },
    }
    _write_report(args.report, report)
    print("GH22_SAM3D_REFERENCE_PREPARED")


if __name__ == "__main__":
    main()
