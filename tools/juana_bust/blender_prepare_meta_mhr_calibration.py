"""Convert the traceable Meta MHR result into a rigged calibration asset."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

import bpy
from mathutils import Matrix, Vector

SOURCE_SHA256 = "8c7afc60df553b66e1cc3143fc2c04878475e97433d9d6af190393f48eec9ccb"
SOURCE_BYTE_LENGTH = 1_648_460
MHR_LOD1_SHA256 = "d66fbca815bcde6532f728f1f63071003c5d43ff44f56e263a0807baec1ae055"
MHR_LOD1_BYTE_LENGTH = 7_884_560
MHR_RELEASE = "v1.0.1"
EXPECTED_VERTICES = 18_439
EXPECTED_TRIANGLES = 36_874
EXPECTED_JOINTS = 88
EXPECTED_SEGMENTS = 85
_MESH_NAME = "HumanMesh"
_MARKER_PARENT = "Node_175"
_SEGMENT_PARENT = "Node_86"
_PROCEDURAL_TWIST = re.compile(r"^(?P<base>.+)_twist\d+_proc$")


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--mhr-lod1", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_file(
    path: Path,
    *,
    label: str,
    expected_sha256: str,
    expected_byte_length: int,
) -> None:
    if not path.is_file():
        raise RuntimeError(f"Required {label} is missing: {path}.")
    actual_sha256 = _sha256_file(path)
    actual_byte_length = path.stat().st_size
    if actual_sha256 != expected_sha256 or actual_byte_length != expected_byte_length:
        raise RuntimeError(
            f"{label} integrity mismatch: expected sha256={expected_sha256}, "
            f"bytes={expected_byte_length}; actual sha256={actual_sha256}, "
            f"bytes={actual_byte_length}."
        )


def _numeric_suffix(name: str) -> int:
    return int(name.rsplit("_", 1)[1])


def _upright(vector: Vector) -> Vector:
    return Vector((vector.x, -vector.y, -vector.z))


def _canonical_face(polygon: bpy.types.MeshPolygon) -> tuple[int, ...]:
    return tuple(polygon.vertices)


def _source_structure() -> tuple[
    bpy.types.Object,
    list[bpy.types.Object],
    list[bpy.types.Object],
]:
    body = bpy.data.objects.get(_MESH_NAME)
    if body is None or body.type != "MESH":
        raise RuntimeError(f"Meta source does not contain {_MESH_NAME}.")
    markers = sorted(
        (
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH"
            and obj.parent is not None
            and obj.parent.name == _MARKER_PARENT
            and obj.name.startswith("Mesh_")
        ),
        key=lambda obj: _numeric_suffix(obj.name),
    )
    segments = sorted(
        (
            obj
            for obj in bpy.data.objects
            if obj.type == "MESH"
            and obj.parent is not None
            and obj.parent.name == _SEGMENT_PARENT
            and obj.name.startswith("Mesh_")
        ),
        key=lambda obj: _numeric_suffix(obj.name),
    )
    body.data.calc_loop_triangles()
    if len(body.data.vertices) != EXPECTED_VERTICES:
        raise RuntimeError(
            f"Meta source vertex count changed: {len(body.data.vertices)}."
        )
    if len(body.data.loop_triangles) != EXPECTED_TRIANGLES:
        raise RuntimeError(
            f"Meta source triangle count changed: {len(body.data.loop_triangles)}."
        )
    if len(markers) != EXPECTED_JOINTS or len(segments) != EXPECTED_SEGMENTS:
        raise RuntimeError(
            "Meta source skeleton visualization changed: "
            f"markers={len(markers)}, segments={len(segments)}."
        )
    return body, markers, segments


def _import_mhr_lod1(
    path: Path,
) -> tuple[bpy.types.Object, bpy.types.Object, list[bpy.types.Object]]:
    existing = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=str(path), use_anim=False)
    imported = [obj for obj in bpy.data.objects if obj not in existing]
    armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if len(armatures) != 1 or len(meshes) != 1:
        summary = [(obj.name, obj.type) for obj in imported]
        raise RuntimeError(f"Unexpected MHR LOD1 import: {summary}.")
    return armatures[0], meshes[0], imported


def _validate_topology(
    source: bpy.types.Object,
    rigged: bpy.types.Object,
) -> None:
    source_faces = [_canonical_face(polygon) for polygon in source.data.polygons]
    rigged_faces = [_canonical_face(polygon) for polygon in rigged.data.polygons]
    if len(source.data.vertices) != len(rigged.data.vertices):
        raise RuntimeError("Meta source does not match MHR LOD1 vertex topology.")
    if source_faces != rigged_faces:
        raise RuntimeError("Meta source does not match MHR LOD1 ordered faces.")


def _collapsed_group(name: str) -> str:
    match = _PROCEDURAL_TWIST.fullmatch(name)
    return match.group("base") if match else name


def _transfer_weights(
    source: bpy.types.Object,
    rigged: bpy.types.Object,
    valid_bones: set[str],
) -> tuple[list[str], int]:
    for group in tuple(source.vertex_groups):
        source.vertex_groups.remove(group)
    source_group_names = {
        group.index: _collapsed_group(group.name) for group in rigged.vertex_groups
    }
    target_groups: dict[str, bpy.types.VertexGroup] = {}
    for target_name in sorted(set(source_group_names.values())):
        if target_name not in valid_bones:
            raise RuntimeError(f"MHR weight group has no calibration bone: {target_name}.")
        target_groups[target_name] = source.vertex_groups.new(name=target_name)

    weighted_vertices = 0
    for vertex in rigged.data.vertices:
        accumulated: dict[str, float] = {}
        for membership in vertex.groups:
            target_name = source_group_names[membership.group]
            accumulated[target_name] = accumulated.get(target_name, 0.0) + membership.weight
        total = sum(accumulated.values())
        if total <= 0.0:
            continue
        weighted_vertices += 1
        for target_name, weight in accumulated.items():
            target_groups[target_name].add([vertex.index], weight / total, "REPLACE")
    return sorted(target_groups), weighted_vertices


def _create_calibration_armature(
    markers: list[bpy.types.Object],
    mhr_armature: bpy.types.Object,
) -> tuple[bpy.types.Object, list[str]]:
    official_bones = list(mhr_armature.data.bones)
    exported_bones = [bone for bone in official_bones if not bone.name.endswith("_proc")]
    if len(exported_bones) != len(markers):
        raise RuntimeError(
            f"MHR marker mapping changed: {len(exported_bones)} bones, "
            f"{len(markers)} markers."
        )

    marker_positions = {
        bone.name: _upright(marker.location.copy())
        for bone, marker in zip(exported_bones, markers, strict=True)
    }
    official_by_name = {bone.name: bone for bone in exported_bones}
    children: dict[str, list[str]] = {bone.name: [] for bone in exported_bones}
    for bone in exported_bones:
        if bone.parent is not None and bone.parent.name in children:
            children[bone.parent.name].append(bone.name)

    armature_data = bpy.data.armatures.new("Juana_Meta_MHR_Calibration_Data")
    armature = bpy.data.objects.new("Juana_Meta_MHR_Calibration_Armature", armature_data)
    bpy.context.scene.collection.objects.link(armature)
    armature.show_in_front = False
    armature.hide_render = True
    armature["status"] = "provisional_body_and_rig_calibration"
    armature["source_sha256"] = SOURCE_SHA256
    armature["mhr_release"] = MHR_RELEASE
    armature["production_base"] = False

    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")
    edit_bones: dict[str, bpy.types.EditBone] = {}
    for bone in exported_bones:
        edit_bone = armature_data.edit_bones.new(bone.name)
        edit_bone.head = marker_positions[bone.name]
        child_names = children[bone.name]
        distinct_children = [
            child_name
            for child_name in child_names
            if (marker_positions[child_name] - edit_bone.head).length > 0.004
        ]
        if distinct_children:
            child_name = min(
                distinct_children,
                key=lambda candidate: (
                    official_by_name[candidate].head_local - bone.tail_local
                ).length,
            )
            edit_bone.tail = marker_positions[child_name]
        else:
            direction = bone.tail_local - bone.head_local
            if direction.length <= 0.001:
                direction = Vector((0.0, 0.0, 1.0))
            edit_bone.tail = edit_bone.head + direction.normalized() * max(
                0.012,
                min(0.08, float(direction.length)),
            )
        edit_bone.use_deform = True
        edit_bones[bone.name] = edit_bone

    for bone in exported_bones:
        if bone.parent is not None:
            edit_bones[bone.name].parent = edit_bones[bone.parent.name]
    bpy.ops.object.mode_set(mode="OBJECT")
    armature.select_set(False)
    return armature, list(armature.data.bones.keys())


def _prepare_body(
    body: bpy.types.Object,
    armature: bpy.types.Object,
) -> None:
    body.parent = None
    body.matrix_world = Matrix.Identity(4)
    for vertex in body.data.vertices:
        vertex.co = _upright(vertex.co)
    body.name = "Juana_Meta_MHR_Body_Calibration"
    body.data.name = "Juana_Meta_MHR_Body_Calibration_Mesh"
    body["status"] = "provisional_body_and_rig_calibration"
    body["source_sha256"] = SOURCE_SHA256
    body["mhr_release"] = MHR_RELEASE
    body["production_base"] = False
    body["face_likeness_source"] = False

    body.data.materials.clear()
    material = bpy.data.materials.new("Juana_Meta_MHR_Calibration_Material")
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (0.34, 0.18, 0.11, 1.0)
    principled.inputs["Roughness"].default_value = 0.72
    body.data.materials.append(material)
    for polygon in body.data.polygons:
        polygon.use_smooth = True

    modifier = body.modifiers.new("Juana Meta MHR calibration armature", "ARMATURE")
    modifier.object = armature
    body.parent = armature
    body.matrix_parent_inverse = armature.matrix_world.inverted()
    body.data.update()


def _remove_objects(objects: list[bpy.types.Object]) -> None:
    for obj in objects:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)


def _write_report(
    path: Path,
    *,
    output: Path,
    body: bpy.types.Object,
    bone_names: list[str],
    group_names: list[str],
    weighted_vertices: int,
) -> None:
    body.data.calc_loop_triangles()
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "provisional_body_and_rig_calibration",
        "source": {
            "sha256": SOURCE_SHA256,
            "byte_length": SOURCE_BYTE_LENGTH,
            "origin": "Meta AI Demos",
            "generator_family": "SAM 3D Body / MHR",
        },
        "mhr_decoder": {
            "release": MHR_RELEASE,
            "lod": 1,
            "sha256": MHR_LOD1_SHA256,
            "byte_length": MHR_LOD1_BYTE_LENGTH,
            "license": "Apache-2.0",
        },
        "processing": {
            "topology_match": "exact_vertex_and_ordered_face_identity",
            "marker_count": EXPECTED_JOINTS,
            "visual_segment_count": EXPECTED_SEGMENTS,
            "bone_count": len(bone_names),
            "weight_group_count": len(group_names),
            "weighted_vertices": weighted_vertices,
            "coordinate_conversion": "x,-y,-z",
            "procedural_twist_policy": "weights collapsed to named parent limb bones",
            "production_base": False,
        },
        "output": {
            "path": str(output),
            "sha256": _sha256_file(output),
            "byte_length": output.stat().st_size,
            "vertices": len(body.data.vertices),
            "triangles": len(body.data.loop_triangles),
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = _arguments()
    args.source = args.source.resolve()
    args.mhr_lod1 = args.mhr_lod1.resolve()
    args.output = args.output.resolve()
    args.report = args.report.resolve()
    _verify_file(
        args.source,
        label="Meta MHR source",
        expected_sha256=SOURCE_SHA256,
        expected_byte_length=SOURCE_BYTE_LENGTH,
    )
    _verify_file(
        args.mhr_lod1,
        label="MHR LOD1 rig",
        expected_sha256=MHR_LOD1_SHA256,
        expected_byte_length=MHR_LOD1_BYTE_LENGTH,
    )

    bpy.ops.wm.open_mainfile(filepath=str(args.source))
    body, markers, segments = _source_structure()
    source_scene_objects = [obj for obj in bpy.data.objects if obj != body]
    mhr_armature, rigged_mesh, imported = _import_mhr_lod1(args.mhr_lod1)
    _validate_topology(body, rigged_mesh)
    armature, bone_names = _create_calibration_armature(markers, mhr_armature)
    group_names, weighted_vertices = _transfer_weights(
        body,
        rigged_mesh,
        set(bone_names),
    )
    if weighted_vertices != EXPECTED_VERTICES:
        raise RuntimeError(
            f"MHR weight transfer left vertices unweighted: {weighted_vertices}."
        )
    _prepare_body(body, armature)

    _remove_objects(list({*source_scene_objects, *imported} - {armature}))
    for pose_bone in armature.pose.bones:
        pose_bone.custom_shape = None
    _remove_objects(
        [obj for obj in bpy.data.objects if obj not in {body, armature}]
    )
    bpy.context.scene.world.color = (0.02, 0.02, 0.02)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    armature.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.export_scene.gltf(
        filepath=str(args.output),
        export_format="GLB",
        use_selection=True,
        export_animations=False,
        export_morph=False,
        export_skins=True,
        export_all_influences=True,
        export_yup=True,
    )
    _write_report(
        args.report,
        output=args.output,
        body=body,
        bone_names=bone_names,
        group_names=group_names,
        weighted_vertices=weighted_vertices,
    )
    print(
        "GH22_META_MHR_CALIBRATION_READY "
        f"vertices={len(body.data.vertices)} bones={len(bone_names)} "
        f"bytes={args.output.stat().st_size}"
    )


if __name__ == "__main__":
    main()
