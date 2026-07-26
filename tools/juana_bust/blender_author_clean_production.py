"""Build the clean single-character GH-22 Juana production checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector, geometry
from mathutils.bvhtree import BVHTree

TARGET_CONTROL_TRANSFER_STRENGTH = 0.48
HIGHPOLY_SHRINKWRAP_STRENGTH = 0.40


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--toolchain-root", type=Path, required=True)
    parser.add_argument("--references-root", type=Path, required=True)
    parser.add_argument("--render-manifest", type=Path, required=True)
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Expected JSON object in {path}.")
    return value


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _resolve_local_path(repository_root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repository_root / path


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in tuple(bpy.data.collections):
        bpy.data.collections.remove(collection)


def _create_collection(scene: bpy.types.Scene, name: str) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    return collection


def _activate_collection(collection: bpy.types.Collection) -> None:
    layer_collection = bpy.context.view_layer.layer_collection.children.get(collection.name)
    if layer_collection is None:
        raise RuntimeError(f"Collection {collection.name} is not linked to the view layer.")
    bpy.context.view_layer.active_layer_collection = layer_collection


def _relocate(obj: bpy.types.Object, collection: bpy.types.Collection) -> None:
    for source in tuple(obj.users_collection):
        source.objects.unlink(obj)
    collection.objects.link(obj)


def _link_export(obj: bpy.types.Object, export_collection: bpy.types.Collection) -> None:
    if export_collection not in obj.users_collection:
        export_collection.objects.link(obj)


def _triangle_count(obj: bpy.types.Object) -> int:
    if obj.type != "MESH":
        return 0
    return sum(max(0, len(polygon.vertices) - 2) for polygon in obj.data.polygons)


def _mark_object(
    obj: bpy.types.Object,
    *,
    role: str,
    exportable: bool,
    renderable: bool,
    source_sha256: str | None = None,
) -> None:
    obj["source_role"] = role
    obj["exportable"] = exportable
    obj["renderable"] = renderable
    obj["root_transform_applied"] = True
    if source_sha256 is not None:
        obj["source_sha256"] = source_sha256
    obj.hide_render = not renderable


def _bake_mesh_world_transform(obj: bpy.types.Object) -> None:
    if obj.type != "MESH":
        return
    world = obj.matrix_world.copy()
    obj.data.transform(world)
    obj.parent = None
    obj.matrix_world = Matrix.Identity(4)
    obj.data.update()


def _bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    coordinates = [obj.matrix_world @ vertex.co for vertex in obj.data.vertices]
    return (
        Vector(tuple(min(coordinate[index] for coordinate in coordinates) for index in range(3))),
        Vector(tuple(max(coordinate[index] for coordinate in coordinates) for index in range(3))),
    )


def _percentile(values: Sequence[float], quantile: float) -> float:
    if not values:
        raise RuntimeError("Cannot measure an empty body band.")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * quantile)))
    return ordered[index]


def _band_metrics(
    obj: bpy.types.Object,
    *,
    center_z: float,
    half_height: float,
    torso_half_width: float,
    quantile: float = 0.95,
) -> dict[str, float]:
    minimum, maximum = _bounds(obj)
    center_x = (minimum.x + maximum.x) * 0.5
    center_y = (minimum.y + maximum.y) * 0.5
    selected = [
        obj.matrix_world @ vertex.co
        for vertex in obj.data.vertices
        if abs((obj.matrix_world @ vertex.co).z - center_z) <= half_height
        and abs((obj.matrix_world @ vertex.co).x - center_x) <= torso_half_width
    ]
    return {
        "width": 2.0
        * _percentile([abs(point.x - center_x) for point in selected], quantile),
        "depth": 2.0
        * _percentile([abs(point.y - center_y) for point in selected], quantile),
        "sample_count": float(len(selected)),
    }


def _bake_shape_mix(body: bpy.types.Object) -> None:
    if body.data.shape_keys is None:
        return
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.shape_key_remove(all=True, apply_mix=True)


def _normalize_and_fit_body(
    body: bpy.types.Object,
    sam_reference: bpy.types.Object,
    profile: Mapping[str, Any],
) -> dict[str, Any]:
    body_minimum, body_maximum = _bounds(body)
    sam_minimum, sam_maximum = _bounds(sam_reference)
    source_height = body_maximum.z - body_minimum.z
    target_height = sam_maximum.z - sam_minimum.z
    uniform_scale = target_height / source_height
    body_center_x = (body_minimum.x + body_maximum.x) * 0.5
    body_center_y = (body_minimum.y + body_maximum.y) * 0.5
    body.data.transform(
        Matrix.Translation((-body_center_x, -body_center_y, -body_minimum.z))
    )
    body.data.transform(Matrix.Diagonal((uniform_scale, uniform_scale, uniform_scale, 1.0)))
    body.matrix_world = Matrix.Identity(4)
    body.data.update()

    band_specs = profile["bands"]
    if not isinstance(band_specs, Mapping):
        raise RuntimeError("Approved body profile bands must be a mapping.")
    bands = sorted(
        (
            str(name),
            float(spec["z_fraction"]),
            spec,
        )
        for name, spec in band_specs.items()
    )
    bands.sort(key=lambda item: item[1])
    sam_torso_half_width = float(profile["sam3d_torso_half_width_m"])
    sam_quantile = float(profile["sam3d_band_quantile"])
    profiles: dict[str, dict[str, float]] = {}
    control_points: list[tuple[float, float, float]] = []
    for name, fraction, spec in bands:
        center_z = target_height * fraction
        half_height = target_height * 0.018
        target = _band_metrics(
            sam_reference,
            center_z=center_z,
            half_height=half_height,
            torso_half_width=sam_torso_half_width,
            quantile=sam_quantile,
        )
        current = _band_metrics(
            body,
            center_z=center_z,
            half_height=half_height,
            torso_half_width=0.285,
        )
        raw_width_scale = target["width"] / current["width"]
        raw_depth_scale = target["depth"] / current["depth"]
        width_limits = tuple(float(value) for value in spec["width_scale_range"])
        depth_limits = tuple(float(value) for value in spec["depth_scale_range"])
        width_scale = max(width_limits[0], min(width_limits[1], raw_width_scale))
        depth_scale = max(depth_limits[0], min(depth_limits[1], raw_depth_scale))
        profiles[name] = {
            "z_fraction": fraction,
            "sam_width": target["width"],
            "sam_depth": target["depth"],
            "production_width_before": current["width"],
            "production_depth_before": current["depth"],
            "raw_width_scale": raw_width_scale,
            "raw_depth_scale": raw_depth_scale,
            "width_scale_min": width_limits[0],
            "width_scale_max": width_limits[1],
            "depth_scale_min": depth_limits[0],
            "depth_scale_max": depth_limits[1],
            "width_scale": width_scale,
            "depth_scale": depth_scale,
        }
        control_points.append((fraction, width_scale, depth_scale))

    def interpolated_scales(fraction: float) -> tuple[float, float]:
        if fraction <= control_points[0][0]:
            return control_points[0][1], control_points[0][2]
        if fraction >= control_points[-1][0]:
            return control_points[-1][1], control_points[-1][2]
        for left, right in zip(control_points, control_points[1:], strict=False):
            if left[0] <= fraction <= right[0]:
                amount = (fraction - left[0]) / (right[0] - left[0])
                return (
                    left[1] + (right[1] - left[1]) * amount,
                    left[2] + (right[2] - left[2]) * amount,
                )
        raise RuntimeError("Body profile interpolation failed.")

    for vertex in body.data.vertices:
        fraction = vertex.co.z / target_height
        torso_weight = max(0.0, min(1.0, (0.31 - abs(vertex.co.x)) / 0.055))
        vertical_weight = min(
            max(0.0, (fraction - 0.42) / 0.06),
            max(0.0, (0.88 - fraction) / 0.06),
            1.0,
        )
        weight = torso_weight * vertical_weight
        if weight <= 0.0:
            continue
        width_scale, depth_scale = interpolated_scales(fraction)
        vertex.co.x *= 1.0 + (width_scale - 1.0) * weight
        vertex.co.y *= 1.0 + (depth_scale - 1.0) * weight
    body.data.update()

    for name, fraction, _spec in bands:
        after = _band_metrics(
            body,
            center_z=target_height * fraction,
            half_height=target_height * 0.018,
            torso_half_width=0.285,
        )
        profiles[name]["production_width_after"] = after["width"]
        profiles[name]["production_depth_after"] = after["depth"]

    return {
        "method": "sam3d_normalized_approved_profile_cage_fit",
        "profile": str(profile["name"]),
        "source_height": source_height,
        "target_height": target_height,
        "uniform_scale": uniform_scale,
        "sam3d_torso_half_width_m": sam_torso_half_width,
        "sam3d_band_quantile": sam_quantile,
        "bands": profiles,
    }


def _import_single_mesh(
    path: Path,
    collection: bpy.types.Collection,
    *,
    expected_name: str,
    role: str,
    source_sha256: str,
) -> bpy.types.Object:
    before = set(bpy.data.objects)
    _activate_collection(collection)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    meshes = [obj for obj in imported if obj.type == "MESH"]
    if len(meshes) != 1:
        imported_summary = [(obj.name, obj.type) for obj in imported]
        raise RuntimeError(
            f"Expected one mesh in {path}; imported {imported_summary}."
        )
    obj = meshes[0]
    _bake_mesh_world_transform(obj)
    obj.name = expected_name
    obj.data.name = f"{expected_name}_Mesh"
    _relocate(obj, collection)
    _mark_object(
        obj,
        role=role,
        exportable=False,
        renderable=False,
        source_sha256=source_sha256,
    )
    for extra in imported:
        if extra != obj:
            bpy.data.objects.remove(extra, do_unlink=True)
    return obj


def _crop_highpoly_face_helper(helper: bpy.types.Object) -> int:
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(helper.data)
    delete_vertices = [
        vertex
        for vertex in edit_mesh.verts
        if not (
            -0.100 < vertex.co.x < 0.180
            and -0.270 < vertex.co.y < 0.080
            and 0.420 < vertex.co.z < 0.825
        )
    ]
    bmesh.ops.delete(edit_mesh, geom=delete_vertices, context="VERTS")
    retained = len(edit_mesh.verts)
    edit_mesh.to_mesh(helper.data)
    edit_mesh.free()
    helper.data.update()
    if retained < 1000:
        raise RuntimeError(f"High-poly face helper retained too few vertices: {retained}.")
    return retained


def _filter_highpoly_face_surface(helper: bpy.types.Object) -> dict[str, int | str]:
    material = helper.data.materials[0] if helper.data.materials else None
    if material is None or not material.use_nodes or material.node_tree is None:
        raise RuntimeError("High-poly face filtering requires a node-based source material.")
    source_image = next(
        (
            node.image
            for node in material.node_tree.nodes
            if node.type == "TEX_IMAGE" and node.image is not None
        ),
        None,
    )
    if source_image is None:
        raise RuntimeError("High-poly face filtering requires a base-color image.")

    sample_image = source_image.copy()
    try:
        sample_image.scale(512, 512)
        width, height = sample_image.size
        pixels = np.empty(width * height * 4, dtype=np.float32)
        sample_image.pixels.foreach_get(pixels)
        pixels = pixels.reshape((height, width, 4))

        edit_mesh = bmesh.new()
        edit_mesh.from_mesh(helper.data)
        uv_layer = edit_mesh.loops.layers.uv.active
        if uv_layer is None:
            edit_mesh.free()
            raise RuntimeError("High-poly face filtering requires an active UV layer.")

        remove_faces = []
        retained_faces = 0
        for face in edit_mesh.faces:
            center = face.calc_center_median()
            spatial_match = (
                abs(center.x) < 0.090
                and center.y < 0.025
                and 1.44 < center.z < 1.69
            )
            if not spatial_match:
                remove_faces.append(face)
                continue
            uv = sum(
                (loop[uv_layer].uv for loop in face.loops),
                Vector((0.0, 0.0)),
            ) / len(face.loops)
            pixel_x = min(width - 1, max(0, int((uv.x % 1.0) * width)))
            pixel_y = min(height - 1, max(0, int((uv.y % 1.0) * height)))
            red, green, blue = (float(value) for value in pixels[pixel_y, pixel_x, :3])
            skin_match = (
                red > 0.12
                and red > green * 1.04
                and green > blue * 1.03
                and (red + green + blue) / 3.0 < 0.70
            )
            if skin_match:
                retained_faces += 1
            else:
                remove_faces.append(face)

        bmesh.ops.delete(edit_mesh, geom=remove_faces, context="FACES")
        loose_edges = [edge for edge in edit_mesh.edges if not edge.link_faces]
        if loose_edges:
            bmesh.ops.delete(edit_mesh, geom=loose_edges, context="EDGES")
        loose_vertices = [vertex for vertex in edit_mesh.verts if not vertex.link_edges]
        if loose_vertices:
            bmesh.ops.delete(edit_mesh, geom=loose_vertices, context="VERTS")
        retained_vertices = len(edit_mesh.verts)
        edit_mesh.to_mesh(helper.data)
        edit_mesh.free()
        helper.data.update()
    finally:
        bpy.data.images.remove(sample_image)

    if retained_faces < 1000 or retained_vertices < 1000:
        raise RuntimeError(
            "Filtered high-poly face surface is unexpectedly small: "
            f"faces={retained_faces}, vertices={retained_vertices}."
        )
    return {
        "method": "front_surface_and_base_color_skin_filter",
        "retained_faces": retained_faces,
        "retained_vertices": retained_vertices,
    }


def _import_highpoly_reference(
    path: Path,
    collection: bpy.types.Collection,
    *,
    source_sha256: str,
    target_eye_midpoint: Vector,
    target_eye_distance: float,
) -> tuple[bpy.types.Object, bpy.types.Object, dict[str, Any]]:
    before = set(bpy.data.objects)
    _activate_collection(collection)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    meshes = sorted(
        (obj for obj in imported if obj.type == "MESH"),
        key=lambda item: len(item.data.vertices),
        reverse=True,
    )
    if not meshes or len(meshes[0].data.vertices) != 924342:
        raise RuntimeError(f"High-poly bust main mesh was not found in {path}.")
    main = meshes[0]
    _bake_mesh_world_transform(main)
    helper = main.copy()
    helper.data = main.data.copy()
    collection.objects.link(helper)
    retained_face_vertices = _crop_highpoly_face_helper(helper)

    source_eye_midpoint = Vector((0.040093, -0.156858, 0.736104))
    source_eye_distance = 0.106
    scale_x = target_eye_distance / source_eye_distance
    scale_yz = 0.82 * (scale_x / 0.86)
    scale = Vector((scale_x, scale_yz, scale_yz))
    scaled_eye_midpoint = Vector(
        (
            source_eye_midpoint.x * scale.x,
            source_eye_midpoint.y * scale.y,
            source_eye_midpoint.z * scale.z,
        )
    )
    alignment = Matrix.Translation(target_eye_midpoint - scaled_eye_midpoint) @ Matrix.Diagonal(
        (*scale, 1.0)
    )
    main.data.transform(alignment)
    helper.data.transform(alignment)
    main.matrix_world = Matrix.Identity(4)
    helper.matrix_world = Matrix.Identity(4)
    main.data.update()
    helper.data.update()
    face_surface_filter = _filter_highpoly_face_surface(helper)

    main.name = "Juana_Highpoly_Bust_Reference"
    main.data.name = "Juana_Highpoly_Bust_Reference_Mesh"
    main["immutable_reference"] = True
    main["normalized_alignment"] = "eye_landmark_similarity_transform"
    _mark_object(
        main,
        role="reference_highpoly",
        exportable=False,
        renderable=False,
        source_sha256=source_sha256,
    )
    helper.name = "Juana_Highpoly_Face_Fit_Helper"
    helper.data.name = "Juana_Highpoly_Face_Fit_Helper_Mesh"
    helper["derived_fit_helper"] = True
    _mark_object(
        helper,
        role="reference_highpoly_helper",
        exportable=False,
        renderable=False,
        source_sha256=source_sha256,
    )
    _relocate(main, collection)
    _relocate(helper, collection)
    for extra in imported:
        if extra not in {main, helper}:
            if extra.type == "MESH":
                _bake_mesh_world_transform(extra)
                extra.name = f"Juana_Highpoly_Auxiliary_{extra.name}"
                _relocate(extra, collection)
                _mark_object(
                    extra,
                    role="reference_highpoly_auxiliary",
                    exportable=False,
                    renderable=False,
                    source_sha256=source_sha256,
                )
            else:
                bpy.data.objects.remove(extra, do_unlink=True)
    return main, helper, {
        "method": "explicit_eye_landmark_similarity_transform",
        "source_eye_midpoint": list(source_eye_midpoint),
        "target_eye_midpoint": list(target_eye_midpoint),
        "source_eye_distance": source_eye_distance,
        "target_eye_distance": target_eye_distance,
        "scale": list(scale),
        "retained_face_helper_vertices": retained_face_vertices,
        "face_surface_filter": face_surface_filter,
    }


def _import_vrm_donor(
    path: Path,
    collection: bpy.types.Collection,
    *,
    source_sha256: str,
) -> dict[str, Any]:
    before = set(bpy.data.objects)
    _activate_collection(collection)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in before]
    meshes = []
    armatures = []
    for obj in imported:
        if obj.type not in {"MESH", "ARMATURE"}:
            bpy.data.objects.remove(obj, do_unlink=True)
            continue
        original_name = obj.name
        obj.name = f"DonorVRM_{original_name}"
        obj["donor_original_name"] = original_name
        _relocate(obj, collection)
        _mark_object(
            obj,
            role="donor_vrm_rig" if obj.type == "ARMATURE" else "donor_vrm_mesh",
            exportable=False,
            renderable=False,
            source_sha256=source_sha256,
        )
        if obj.type == "MESH":
            meshes.append(
                {
                    "name": original_name,
                    "vertices": len(obj.data.vertices),
                    "triangles": _triangle_count(obj),
                }
            )
        else:
            armatures.append(
                {
                    "name": original_name,
                    "bones": sorted(bone.name for bone in obj.data.bones),
                }
            )
    return {"meshes": meshes, "armatures": armatures}


def _apply_face_landmark_cage(body: bpy.types.Object, eye_line: float) -> dict[str, Any]:
    face_front_y = min(
        vertex.co.y
        for vertex in body.data.vertices
        if abs(vertex.co.x) < 0.13 and eye_line - 0.22 < vertex.co.z < eye_line + 0.07
    )
    face_back_y = face_front_y + 0.105
    changed = 0
    for vertex in body.data.vertices:
        coordinate = vertex.co
        front_weight = max(0.0, min(1.0, (face_back_y - coordinate.y) / 0.105))
        side_weight = max(0.0, min(1.0, (0.125 - abs(coordinate.x)) / 0.035))
        if front_weight <= 0.0 or side_weight <= 0.0:
            continue
        original = coordinate.copy()
        if eye_line - 0.22 < coordinate.z < eye_line:
            compression = max(0.0, min(1.0, (eye_line - coordinate.z) / 0.20))
            coordinate.z += 0.010 * compression * front_weight * side_weight
        cheek_weight = max(0.0, 1.0 - abs(coordinate.z - (eye_line - 0.055)) / 0.060)
        jaw_weight = max(0.0, 1.0 - abs(coordinate.z - (eye_line - 0.135)) / 0.070)
        lateral = 1.0 if coordinate.x >= 0.0 else -1.0
        coordinate.x += lateral * (
            0.0040 * cheek_weight + 0.0045 * jaw_weight
        ) * front_weight
        if abs(coordinate.x) < 0.040 and eye_line - 0.105 < coordinate.z < eye_line + 0.020:
            coordinate.y -= 0.0040 * front_weight
            coordinate.x *= 1.035
        if abs(coordinate.x) < 0.067 and eye_line - 0.155 < coordinate.z < eye_line - 0.090:
            coordinate.y -= 0.0025 * front_weight
        if eye_line - 0.025 < coordinate.z < eye_line + 0.035 and abs(coordinate.x) < 0.085:
            coordinate.z = eye_line + (coordinate.z - eye_line) * 0.76
        if (coordinate - original).length > 1e-7:
            changed += 1
    body.data.update()
    return {
        "method": "landmark_driven_masked_cage_deformation",
        "changed_vertices": changed,
        "eye_line_z": eye_line,
        "face_front_y": face_front_y,
        "face_back_y": face_back_y,
        "lower_face_compression_m": 0.010,
        "cheekbone_expansion_m": 0.0040,
        "jaw_expansion_m": 0.0045,
        "nose_projection_m": 0.0040,
        "lip_projection_m": 0.0025,
        "eye_vertical_scale": 0.76,
    }


def _apply_masked_shrinkwrap(
    body: bpy.types.Object,
    target: bpy.types.Object,
    *,
    eye_line: float,
) -> dict[str, Any]:
    group = body.vertex_groups.new(name="Juana_Highpoly_Face_Mask")
    group_name = group.name
    face_front_y = min(
        vertex.co.y
        for vertex in body.data.vertices
        if abs(vertex.co.x) < 0.125 and eye_line - 0.22 < vertex.co.z < eye_line + 0.07
    )
    face_back_y = face_front_y + 0.105
    weighted = 0
    for vertex in body.data.vertices:
        coordinate = vertex.co
        x_weight = max(0.0, min(1.0, (0.115 - abs(coordinate.x)) / 0.030))
        z_weight = min(
            max(0.0, (coordinate.z - (eye_line - 0.205)) / 0.055),
            max(0.0, ((eye_line + 0.055) - coordinate.z) / 0.040),
            1.0,
        )
        front_weight = max(0.0, min(1.0, (face_back_y - coordinate.y) / 0.105))
        weight = x_weight * z_weight * front_weight * HIGHPOLY_SHRINKWRAP_STRENGTH
        if weight > 0.02:
            group.add([vertex.index], weight, "REPLACE")
            weighted += 1
    if weighted < 50:
        raise RuntimeError(f"High-poly face mask is unexpectedly small: {weighted} vertices.")

    modifier = body.modifiers.new("Juana masked high-poly face fit", "SHRINKWRAP")
    modifier.target = target
    modifier.vertex_group = group_name
    modifier.wrap_method = "NEAREST_SURFACEPOINT"
    modifier.wrap_mode = "ON_SURFACE"
    modifier.offset = 0.0005
    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    return {
        "method": "controlled_masked_shrinkwrap",
        "vertex_group": group_name,
        "weighted_vertices": weighted,
        "projection_method": "nearest_surface_point",
        "maximum_weight": HIGHPOLY_SHRINKWRAP_STRENGTH,
        "face_front_y": face_front_y,
        "face_back_y": face_back_y,
        "offset_m": 0.0005,
    }


def _bisect_at_neck(
    obj: bpy.types.Object,
    *,
    neck_cut_z: float,
    keep_above: bool,
) -> None:
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(obj.data)
    bmesh.ops.bisect_plane(
        edit_mesh,
        geom=[*edit_mesh.verts, *edit_mesh.edges, *edit_mesh.faces],
        dist=0.000001,
        plane_co=(0.0, 0.0, neck_cut_z),
        plane_no=(0.0, 0.0, 1.0),
        clear_inner=keep_above,
        clear_outer=not keep_above,
    )
    loose_vertices = [vertex for vertex in edit_mesh.verts if not vertex.link_edges]
    if loose_vertices:
        bmesh.ops.delete(edit_mesh, geom=loose_vertices, context="VERTS")
    edit_mesh.to_mesh(obj.data)
    edit_mesh.free()
    obj.data.update()


def _split_body_and_head(
    body: bpy.types.Object,
    collection_body: bpy.types.Collection,
    collection_head: bpy.types.Collection,
    *,
    neck_cut_z: float,
) -> tuple[bpy.types.Object, bpy.types.Object]:
    head = body.copy()
    head.data = body.data.copy()
    collection_head.objects.link(head)
    _bisect_at_neck(head, neck_cut_z=neck_cut_z, keep_above=True)
    _bisect_at_neck(body, neck_cut_z=neck_cut_z, keep_above=False)
    body.name = "Juana_Production_Body"
    body.data.name = "Juana_Production_Body_Mesh"
    head.name = "Juana_Production_Head"
    head.data.name = "Juana_Production_Head_Mesh"
    _relocate(body, collection_body)
    _relocate(head, collection_head)
    return body, head


def _convert_to_mesh(obj: bpy.types.Object) -> bpy.types.Object:
    if obj.type == "MESH":
        return obj
    bpy.ops.object.select_all(action="DESELECT")
    obj.hide_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.convert(target="MESH")
    return bpy.context.object


def _transfer_nearest_face_uv(
    source: bpy.types.Object,
    target: bpy.types.Object,
) -> dict[str, float | int]:
    if source.type != "MESH" or target.type != "MESH":
        raise RuntimeError("UV transfer requires mesh source and target objects.")
    source_uv = source.data.uv_layers.active
    target_uv = target.data.uv_layers.active
    if source_uv is None or target_uv is None:
        raise RuntimeError("UV transfer requires active UV layers on source and target.")
    if any(len(polygon.vertices) != 3 for polygon in source.data.polygons):
        raise RuntimeError("High-poly face helper must be triangulated for UV transfer.")

    source_vertices = [source.matrix_world @ vertex.co for vertex in source.data.vertices]
    source_polygons = [tuple(polygon.vertices) for polygon in source.data.polygons]
    tree = BVHTree.FromPolygons(source_vertices, source_polygons, all_triangles=True)
    if tree is None:
        raise RuntimeError("Could not build the high-poly face BVH.")

    distances = []
    transferred_loops = 0
    transferred_vertices: dict[int, Vector] = {}
    transferred_polygons = 0
    target_face_front_y = min(
        vertex.co.y
        for vertex in target.data.vertices
        if abs(vertex.co.x) < 0.14 and vertex.co.z > 1.40
    )
    target_face_back_y = target_face_front_y + 0.115
    for polygon in target.data.polygons:
        polygon_center = target.matrix_world @ polygon.center
        is_face_polygon = (
            abs(polygon_center.x) < 0.145
            and 1.40 < polygon_center.z < 1.72
            and polygon_center.y < target_face_back_y
        )
        polygon.material_index = 0 if is_face_polygon else 1
        if not is_face_polygon:
            continue
        transferred_polygons += 1
        for target_loop_index in polygon.loop_indices:
            target_vertex_index = target.data.loops[target_loop_index].vertex_index
            transferred = transferred_vertices.get(target_vertex_index)
            if transferred is None:
                target_coordinate = (
                    target.matrix_world @ target.data.vertices[target_vertex_index].co
                )
                nearest, _normal, source_polygon_index, distance = tree.find_nearest(
                    target_coordinate
                )
                if nearest is None or source_polygon_index is None:
                    continue
                source_polygon = source.data.polygons[source_polygon_index]
                source_loop_indices = tuple(source_polygon.loop_indices)
                source_vertex_indices = tuple(source_polygon.vertices)
                source_coordinates = [
                    source_vertices[index] for index in source_vertex_indices
                ]
                source_uv_coordinates = [
                    Vector((*source_uv.data[index].uv, 0.0))
                    for index in source_loop_indices
                ]
                transferred = geometry.barycentric_transform(
                    nearest,
                    source_coordinates[0],
                    source_coordinates[1],
                    source_coordinates[2],
                    source_uv_coordinates[0],
                    source_uv_coordinates[1],
                    source_uv_coordinates[2],
                )
                transferred_vertices[target_vertex_index] = transferred
                distances.append(float(distance))
            target_uv.data[target_loop_index].uv = transferred.xy
            transferred_loops += 1
    target.data.update()
    if transferred_loops == 0:
        raise RuntimeError("High-poly UV transfer did not map any target loops.")
    ordered = sorted(distances)
    return {
        "transferred_polygons": transferred_polygons,
        "transferred_vertices": len(transferred_vertices),
        "transferred_loops": transferred_loops,
        "target_face_front_y": target_face_front_y,
        "target_face_back_y": target_face_back_y,
        "nearest_distance_min": ordered[0],
        "nearest_distance_median": ordered[len(ordered) // 2],
        "nearest_distance_max": ordered[-1],
    }


def _bake_head_texture(
    scene: bpy.types.Scene,
    head: bpy.types.Object,
    source: bpy.types.Object,
    output_path: Path,
    *,
    approved_skin_color: Sequence[float],
) -> dict[str, Any]:
    if len(approved_skin_color) != 3:
        raise RuntimeError("Approved skin color must contain three linear channels.")
    final_skin_color = tuple(float(channel) for channel in approved_skin_color)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    projection_source = head.copy()
    projection_source.data = head.data.copy()
    source.users_collection[0].objects.link(projection_source)
    projection_source.name = "Juana_Highpoly_UV_Projection_Helper"
    projection_source.data.name = "Juana_Highpoly_UV_Projection_Helper_Mesh"
    projection_source.parent = None
    projection_source.matrix_world = head.matrix_world.copy()
    for modifier in tuple(projection_source.modifiers):
        projection_source.modifiers.remove(modifier)
    print("GH22_HEAD_UV_TRANSFER_START", flush=True)
    uv_transfer = _transfer_nearest_face_uv(source, projection_source)
    print("GH22_HEAD_UV_TRANSFER_COMPLETE", flush=True)
    projection_source.data.materials.clear()
    for source_material in source.data.materials:
        projection_source.data.materials.append(source_material)
    fallback = bpy.data.materials.new("Juana_Head_Bake_Fallback_Warm_Skin")
    fallback.use_nodes = True
    fallback_principled = fallback.node_tree.nodes.get("Principled BSDF")
    fallback_principled.inputs["Base Color"].default_value = (*final_skin_color, 1.0)
    fallback_principled.inputs["Roughness"].default_value = 0.62
    projection_source.data.materials.append(fallback)
    _mark_object(
        projection_source,
        role="reference_highpoly_texture_projection_helper",
        exportable=False,
        renderable=False,
        source_sha256=source.get("source_sha256"),
    )

    image = bpy.data.images.new(
        "Juana_Highpoly_Head_Bake",
        width=512,
        height=512,
        alpha=True,
        float_buffer=False,
    )
    image.generated_color = (*final_skin_color, 1.0)
    material = bpy.data.materials.new("Juana_Production_Head_Baked_Material")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    texture = nodes.new("ShaderNodeTexImage")
    texture.name = "Juana_Highpoly_Head_Bake_Target"
    texture.image = image
    nodes.active = texture
    links.new(texture.outputs["Color"], principled.inputs["Base Color"])
    principled.inputs["Roughness"].default_value = 0.62
    head.data.materials.clear()
    head.data.materials.append(material)

    source_minimum, source_maximum = _bounds(source)
    head_minimum, head_maximum = _bounds(head)
    bake_debug = {
        "source_bounds_min": list(source_minimum),
        "source_bounds_max": list(source_maximum),
        "head_bounds_min": list(head_minimum),
        "head_bounds_max": list(head_maximum),
        "source_uv_layers": [layer.name for layer in source.data.uv_layers],
        "head_uv_layers": [layer.name for layer in head.data.uv_layers],
        "source_materials": [
            material.name if material is not None else None
            for material in source.data.materials
        ],
        "source_image_nodes": [
            node.image.name
            for source_material in source.data.materials
            if source_material is not None
            and source_material.use_nodes
            and source_material.node_tree is not None
            for node in source_material.node_tree.nodes
            if node.type == "TEX_IMAGE" and node.image is not None
        ],
        "projection_helper_uv_layers": [
            layer.name for layer in projection_source.data.uv_layers
        ],
        "projection_helper_topology_matches_target": (
            len(projection_source.data.vertices) == len(head.data.vertices)
            and len(projection_source.data.polygons) == len(head.data.polygons)
        ),
        "uv_transfer": uv_transfer,
    }
    _write_json(output_path.parent.parent / "head-bake-debug.json", bake_debug)

    previous_engine = scene.render.engine
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    bpy.ops.object.select_all(action="DESELECT")
    projection_source.hide_set(False)
    projection_source.hide_render = False
    projection_source.select_set(True)
    head.hide_set(False)
    head.select_set(True)
    bpy.context.view_layer.objects.active = head
    scene.render.bake.use_selected_to_active = True
    scene.render.bake.use_cage = False
    scene.render.bake.cage_extrusion = 0.002
    scene.render.bake.max_ray_distance = 0.006
    scene.render.bake.margin = 8
    print("GH22_HEAD_TEXTURE_BAKE_START", flush=True)
    bpy.ops.object.bake(type="DIFFUSE", pass_filter={"COLOR"})
    print("GH22_HEAD_TEXTURE_BAKE_COMPLETE", flush=True)
    sampled_peak = max(
        max(float(image.pixels[index + channel]) for channel in range(3))
        for index in range(0, len(image.pixels), 64)
    )
    if sampled_peak < 0.08:
        raise RuntimeError(
            f"High-poly head texture bake produced no usable color: sampled_peak={sampled_peak}."
        )
    skin_samples: list[tuple[float, float, float]] = []
    for index in range(0, len(image.pixels), 64):
        red = float(image.pixels[index])
        green = float(image.pixels[index + 1])
        blue = float(image.pixels[index + 2])
        if (
            0.08 < max(red, green, blue) < 0.95
            and red > blue * 1.08
            and red > green * 0.92
            and green > blue * 0.88
        ):
            skin_samples.append((red, green, blue))
    if len(skin_samples) < 32:
        derived_skin_color = (0.46, 0.34, 0.26)
    else:
        ordered_red = sorted(sample[0] for sample in skin_samples)
        ordered_green = sorted(sample[1] for sample in skin_samples)
        ordered_blue = sorted(sample[2] for sample in skin_samples)
        middle = len(skin_samples) // 2
        derived_skin_color = (
            ordered_red[middle],
            ordered_green[middle],
            ordered_blue[middle],
        )
    for link in tuple(principled.inputs["Base Color"].links):
        links.remove(link)
    principled.inputs["Base Color"].default_value = (*final_skin_color, 1.0)
    material["highpoly_bake_evidence"] = str(output_path)
    material["application"] = "approved_master_reference_skin_tone"
    image.filepath_raw = str(output_path)
    image.file_format = "PNG"
    image.save()
    scene.render.engine = previous_engine
    bpy.data.objects.remove(projection_source, do_unlink=True)
    return {
        "method": "nearest_face_uv_transfer_then_selected_to_active_diffuse_bake",
        "source": source.name,
        "target": head.name,
        "resolution": [512, 512],
        "cage_extrusion_m": 0.002,
        "max_ray_distance_m": 0.006,
        "skin_sample_count": len(skin_samples),
        "donor_derived_skin_color_linear": list(derived_skin_color),
        "applied_skin_color_linear": list(final_skin_color),
        "baked_image_directly_applied": False,
        "output": str(output_path),
        "sha256": _sha256(output_path),
        "byte_length": output_path.stat().st_size,
    }


def _set_render_visibility(objects: Iterable[bpy.types.Object], visible: set[str]) -> None:
    for obj in objects:
        if obj.type in {"MESH", "CURVE", "FONT"}:
            obj.hide_render = obj.name not in visible


def _render(scene: bpy.types.Scene, camera: bpy.types.Object, path: Path) -> None:
    scene.camera = camera
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)


def _wire_material() -> bpy.types.Material:
    material = bpy.data.materials.new("Juana_Wireframe_Review")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    for node in tuple(nodes):
        nodes.remove(node)
    output = nodes.new("ShaderNodeOutputMaterial")
    emission = nodes.new("ShaderNodeEmission")
    emission.inputs["Color"].default_value = (0.82, 0.92, 1.0, 1.0)
    emission.inputs["Strength"].default_value = 1.5
    links.new(emission.outputs["Emission"], output.inputs["Surface"])
    return material


def _render_wireframe(
    scene: bpy.types.Scene,
    camera: bpy.types.Object,
    path: Path,
    sources: Sequence[bpy.types.Object],
    diagnostic_collection: bpy.types.Collection,
) -> None:
    material = _wire_material()
    wires = []
    for source in sources:
        duplicate = source.copy()
        duplicate.data = source.data.copy()
        diagnostic_collection.objects.link(duplicate)
        duplicate.parent = None
        duplicate.matrix_world = source.matrix_world.copy()
        for modifier in tuple(duplicate.modifiers):
            duplicate.modifiers.remove(modifier)
        duplicate.data.materials.clear()
        duplicate.data.materials.append(material)
        modifier = duplicate.modifiers.new("Topology wire", "WIREFRAME")
        modifier.thickness = 0.00055
        modifier.use_replace = True
        duplicate.name = f"{source.name}_WireframeReview"
        _mark_object(
            duplicate,
            role="review_wireframe",
            exportable=False,
            renderable=False,
        )
        duplicate.hide_render = False
        wires.append(duplicate)
    _set_render_visibility(bpy.context.scene.objects, {wire.name for wire in wires})
    _render(scene, camera, path)
    for wire in wires:
        bpy.data.objects.remove(wire, do_unlink=True)


def _object_inventory(obj: bpy.types.Object) -> dict[str, Any]:
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
        value.update(
            {
                "vertices": len(obj.data.vertices),
                "triangles": _triangle_count(obj),
            }
        )
    if armature_modifier is not None and armature_modifier.object is not None:
        value["skinned_to"] = armature_modifier.object.name
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = _arguments()
    sys.path.insert(0, str(args.repo_root))
    from tools.juana_bust import blender_author_preview as components
    from tools.juana_bust.production_gate import (
        validate_scene_inventory,
        validate_visual_profile,
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    render_root = args.output_root / "renders"
    texture_root = args.output_root / "textures"
    render_root.mkdir(parents=True, exist_ok=True)
    texture_root.mkdir(parents=True, exist_ok=True)
    manifest = _load_json(args.render_manifest)
    evidence = _load_json(args.repo_root / "tools" / "juana_bust" / "source-evidence.json")
    lock = _load_json(args.repo_root / "tools" / "juana_bust" / "toolchain-lock.json")
    donors = {item["id"]: item for item in evidence["donors"]}
    visual_correction = evidence["visual_correction_pass_2"]
    body_profile = visual_correction["body_profile"]
    skin_profile = visual_correction["skin"]

    approved_references = [
        *visual_correction["body_references"],
        {
            "path": skin_profile["reference_path"],
            "sha256": skin_profile["reference_sha256"],
        },
    ]
    for reference in approved_references:
        reference_path = _resolve_local_path(args.repo_root, reference["path"])
        if not reference_path.is_file() or _sha256(reference_path) != reference["sha256"]:
            raise RuntimeError(f"Approved visual reference integrity mismatch: {reference_path}.")

    for donor in donors.values():
        source = _resolve_local_path(args.repo_root, donor["local_path"])
        if not source.is_file():
            raise RuntimeError(f"Required donor is missing: {source}.")
        if source.stat().st_size != donor["byte_length"] or _sha256(source) != donor["sha256"]:
            raise RuntimeError(f"Donor integrity mismatch: {donor['id']} at {source}.")

    sam_asset = args.repo_root / donors["juana-sam3d-humanmesh-donor"]["derived_reference"]["path"]
    if _sha256(sam_asset) != donors["juana-sam3d-humanmesh-donor"]["derived_reference"]["sha256"]:
        raise RuntimeError("Normalized SAM 3D reference integrity mismatch.")

    _clear_scene()
    scene = bpy.context.scene
    components._configure_scene(scene, manifest)
    collections = {
        name: _create_collection(scene, name)
        for name in (
            "_REFERENCE_SAM3D",
            "_REFERENCE_HIGHPOLY",
            "_DONOR_VRM",
            "_PRODUCTION_BODY",
            "_PRODUCTION_HEAD",
            "_PRODUCTION_HAIR",
            "_PRODUCTION_OUTFIT",
            "_RIG",
            "_EXPORT",
            "_REVIEW_CAMERAS",
            "_REVIEW_LIGHTS",
            "_REVIEW_DIAGNOSTICS",
        )
    }

    sam_reference = _import_single_mesh(
        sam_asset,
        collections["_REFERENCE_SAM3D"],
        expected_name="SAM3D_HumanMesh_Reference",
        role="reference_sam3d",
        source_sha256=donors["juana-sam3d-humanmesh-donor"]["sha256"],
    )
    donor_vrm_report = _import_vrm_donor(
        _resolve_local_path(
            args.repo_root,
            donors["juana-provisional-vrm-donor"]["local_path"],
        ),
        collections["_DONOR_VRM"],
        source_sha256=donors["juana-provisional-vrm-donor"]["sha256"],
    )

    human_module = components._import_mpfb("services.humanservice")
    target_module = components._import_mpfb("services.targetservice")
    export_module = components._import_mpfb("services.exportservice")
    HumanService = human_module.HumanService
    TargetService = target_module.TargetService
    ExportService = export_module.ExportService

    _activate_collection(collections["_PRODUCTION_BODY"])
    macro_settings = {
        **lock["human_base"]["macro_settings"],
        **body_profile["macro_overrides"],
    }
    body = HumanService.create_human(
        mask_helpers=True,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=0.1,
        macro_detail_dict=macro_settings,
    )
    body.name = "Juana_Production_Base"
    body.data.name = "Juana_Production_Base_Mesh"
    target_root = (
        args.toolchain_root
        / "blender-profile"
        / "extensions"
        / "user_default"
        / "mpfb"
        / "data"
        / "targets"
    )
    controls = tuple(
        (
            item["name"],
            item["target"],
            float(item["weight"]) * TARGET_CONTROL_TRANSFER_STRENGTH,
        )
        for item in evidence["likeness_pass_3"]["target_controls"]
    )
    components._load_targets(TargetService, body, target_root, controls)
    _bake_shape_mix(body)
    body_fit = _normalize_and_fit_body(body, sam_reference, body_profile)
    body_fit["effective_macro_settings"] = macro_settings
    print(f"GH22_BODY_PROFILE {json.dumps(body_fit, sort_keys=True)}", flush=True)

    armature = HumanService.add_builtin_rig(body, "default")
    if armature is None:
        raise RuntimeError("MPFB did not create the production humanoid rig.")
    armature.name = "Juana_Production_Rig"
    armature.data.name = "Juana_Production_Rig_Data"
    armature.show_in_front = False
    _relocate(armature, collections["_RIG"])
    _mark_object(
        armature,
        role="production_rig",
        exportable=True,
        renderable=False,
    )
    armature["vrm_contract_donor_sha256"] = donors["juana-provisional-vrm-donor"]["sha256"]
    armature["adapter_id"] = "juana-mpfb-default-bust"
    components._create_jaw_action(armature)
    _link_export(armature, collections["_EXPORT"])

    left_eye_center = components._bone_world_position(armature, "eye.L")
    right_eye_center = components._bone_world_position(armature, "eye.R")
    target_eye_midpoint = (left_eye_center + right_eye_center) * 0.5
    target_eye_distance = abs(left_eye_center.x - right_eye_center.x)
    highpoly_main, highpoly_face, highpoly_alignment = _import_highpoly_reference(
        _resolve_local_path(
            args.repo_root,
            donors["juana-highpoly-bust-donor"]["local_path"],
        ),
        collections["_REFERENCE_HIGHPOLY"],
        source_sha256=donors["juana-highpoly-bust-donor"]["sha256"],
        target_eye_midpoint=target_eye_midpoint,
        target_eye_distance=target_eye_distance,
    )
    face_cage = _apply_face_landmark_cage(body, target_eye_midpoint.z)
    shrinkwrap = _apply_masked_shrinkwrap(
        body,
        highpoly_face,
        eye_line=target_eye_midpoint.z,
    )

    long_hair = HumanService.add_mhclo_asset(
        str(args.toolchain_root / "assets" / "extracted" / "hair" / "long01" / "long01.mhclo"),
        body,
        asset_type="Hair",
        subdiv_levels=1,
        material_type="NONE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    short_hair = HumanService.add_mhclo_asset(
        str(args.toolchain_root / "assets" / "extracted" / "hair" / "short01" / "short01.mhclo"),
        body,
        asset_type="Hair",
        subdiv_levels=1,
        material_type="NONE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    eyelashes = HumanService.add_mhclo_asset(
        str(
            args.toolchain_root
            / "assets"
            / "extracted"
            / "eyelashes"
            / "eyelashes03"
            / "eyelashes03.mhclo"
        ),
        body,
        asset_type="Eyelashes",
        subdiv_levels=0,
        material_type="NONE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    jacket = HumanService.add_mhclo_asset(
        str(
            args.toolchain_root
            / "assets"
            / "extracted"
            / "clothes"
            / "female_elegantsuit01"
            / "female_elegantsuit01.mhclo"
        ),
        body,
        asset_type="Outfit",
        subdiv_levels=1,
        material_type="NONE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    underlayer = HumanService.add_mhclo_asset(
        str(
            args.toolchain_root
            / "assets"
            / "extracted"
            / "clothes"
            / "female_casualsuit02"
            / "female_casualsuit02.mhclo"
        ),
        body,
        asset_type="Underlayer",
        subdiv_levels=1,
        material_type="NONE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    ExportService.bake_modifiers_remove_helpers(
        body,
        bake_masks=False,
        bake_subdiv=False,
        remove_helpers=True,
        also_proxy=False,
    )
    for modifier in tuple(body.modifiers):
        if modifier.type == "MASK":
            body.modifiers.remove(modifier)

    approved_skin_color = tuple(float(channel) for channel in skin_profile["base_color_linear"])
    materials = {
        "skin": components._material(
            "Juana_Approved_Skin_Base",
            (*approved_skin_color, 1.0),
            roughness=0.62,
            specular_ior_level=0.25,
        ),
        "sclera": components._material(
            "Juana_Eye_Sclera", (0.64, 0.58, 0.51, 1.0), roughness=0.52
        ),
        "iris_rim": components._material(
            "Juana_Eye_Amber_Rim", (0.018, 0.006, 0.002, 1.0), roughness=0.46
        ),
        "iris": components._material(
            "Juana_Eye_Amber", (0.10, 0.035, 0.008, 1.0), roughness=0.42
        ),
        "pupil": components._material(
            "Juana_Eye_Pupil", (0.008, 0.006, 0.005, 1.0), roughness=0.12
        ),
        "eye_highlight": components._material(
            "Juana_Eye_Highlight", (1.0, 1.0, 1.0, 1.0), roughness=0.05
        ),
        "hair_texture": components._hair_texture_material(
            "Juana_Hair_Long_Texture",
            args.toolchain_root / "assets" / "extracted" / "hair" / "long01" / "long01_diffuse.png",
            (0.040, 0.012, 0.006, 1.0),
        ),
        "short_hair_texture": components._hair_texture_material(
            "Juana_Hair_Short_Texture",
            args.toolchain_root
            / "assets"
            / "extracted"
            / "hair"
            / "short01"
            / "short01_diffuse.png",
            (0.028, 0.008, 0.004, 1.0),
        ),
        "undercut": components._undercut_material(),
        "eyebrow": components._material(
            "Juana_Eyebrow_Dark", (0.006, 0.0018, 0.0007, 1.0), roughness=0.84
        ),
        "eyelashes": components._alpha_detail_material(
            "Juana_Eyelashes",
            args.toolchain_root
            / "assets"
            / "extracted"
            / "eyelashes"
            / "eyelashes03"
            / "eyelashes03.png",
            value=0.26,
        ),
        "outfit_inner": components._material(
            "Juana_Outfit_Inner_Pearl", (0.78, 0.80, 0.82, 1.0), roughness=0.28, coat=0.2
        ),
        "outfit_jacket": components._material(
            "Juana_Outfit_Jacket_Pearl", (0.93, 0.95, 0.98, 1.0), roughness=0.16, coat=0.58
        ),
    }
    components._assign_material(body, materials["skin"])
    components._smooth(body)
    hair_objects = components._create_hair(
        body,
        target_eye_midpoint,
        materials,
        long_hair,
        short_hair,
    )
    components._prepare_system_underlayer(underlayer, materials["outfit_inner"])
    components._open_system_jacket(jacket, materials["outfit_jacket"])
    outfit_objects = [underlayer, jacket]
    eyelashes.name = "Juana_Production_Eyelashes"
    components._assign_material(eyelashes, materials["eyelashes"])

    production_body, production_head = _split_body_and_head(
        body,
        collections["_PRODUCTION_BODY"],
        collections["_PRODUCTION_HEAD"],
        neck_cut_z=target_eye_midpoint.z - 0.245,
    )
    _mark_object(
        production_body,
        role="production_body",
        exportable=True,
        renderable=True,
    )
    _mark_object(
        production_head,
        role="production_head",
        exportable=True,
        renderable=True,
    )
    _link_export(production_body, collections["_EXPORT"])
    _link_export(production_head, collections["_EXPORT"])

    texture_bake = _bake_head_texture(
        scene,
        production_head,
        highpoly_face,
        texture_root / "juana-head-highpoly-bake.png",
        approved_skin_color=approved_skin_color,
    )
    production_body.data.materials.clear()
    production_body.data.materials.append(production_head.active_material)
    skin_material = {
        "application": "approved_master_reference_skin_tone",
        "reference_path": skin_profile["reference_path"],
        "reference_sha256": skin_profile["reference_sha256"],
        "base_color_linear": list(approved_skin_color),
        "finish": skin_profile["finish"],
    }
    eyes = [
        components._create_eye("L", left_eye_center, armature, materials),
        components._create_eye("R", right_eye_center, armature, materials),
    ]
    for eye, side in zip(eyes, ("L", "R"), strict=True):
        eye.name = f"Juana_Production_Eye_{side}"
        _relocate(eye, collections["_PRODUCTION_HEAD"])
        _mark_object(eye, role="production_eye", exportable=True, renderable=True)
        _link_export(eye, collections["_EXPORT"])
    brows = components._create_eyebrows(
        left_eye_center,
        right_eye_center,
        production_head,
        armature,
        materials["eyebrow"],
    )
    brows.name = "Juana_Production_Eyebrows"
    for detail in (brows, eyelashes):
        _relocate(detail, collections["_PRODUCTION_HEAD"])
        _mark_object(detail, role="production_head_detail", exportable=True, renderable=True)
        _link_export(detail, collections["_EXPORT"])

    converted_hair = []
    for index, obj in enumerate(hair_objects, start=1):
        obj = _convert_to_mesh(obj)
        obj.name = f"Juana_Production_Hair_{index:02d}"
        _relocate(obj, collections["_PRODUCTION_HAIR"])
        _mark_object(obj, role="production_hair", exportable=True, renderable=True)
        _link_export(obj, collections["_EXPORT"])
        converted_hair.append(obj)
    for index, obj in enumerate(outfit_objects, start=1):
        obj.name = f"Juana_Production_Outfit_{index:02d}"
        _relocate(obj, collections["_PRODUCTION_OUTFIT"])
        _mark_object(obj, role="production_outfit", exportable=True, renderable=True)
        _link_export(obj, collections["_EXPORT"])

    production_renderables = {
        obj.name
        for obj in bpy.context.scene.objects
        if str(obj.get("source_role", "")).startswith("production_")
        and obj.type == "MESH"
    }
    cameras = [components._create_camera(view) for view in manifest["views"]]
    for camera in cameras:
        _relocate(camera, collections["_REVIEW_CAMERAS"])
        _mark_object(camera, role="review_camera", exportable=False, renderable=False)
    lights = [
        components._create_area_light(
            "Juana_Key_Light",
            (1.3, -1.7, 2.25),
            175.0,
            (1.0, 0.96, 0.92),
            1.25,
            (0.0, 0.0, target_eye_midpoint.z),
        ),
        components._create_area_light(
            "Juana_Fill_Light",
            (-1.35, -1.25, 1.75),
            80.0,
            (0.92, 0.96, 1.0),
            1.4,
            (0.0, 0.0, target_eye_midpoint.z),
        ),
        components._create_area_light(
            "Juana_Rim_Light",
            (-0.2, 1.3, 2.15),
            105.0,
            (1.0, 0.96, 0.90),
            0.9,
            (0.0, 0.0, target_eye_midpoint.z),
        ),
    ]
    for light in lights:
        _relocate(light, collections["_REVIEW_LIGHTS"])
        _mark_object(light, role="review_light", exportable=False, renderable=False)
        light.hide_render = False

    _set_render_visibility(bpy.context.scene.objects, production_renderables)
    for view, camera in zip(manifest["views"], cameras, strict=True):
        _render(scene, camera, render_root / f"{view['id']}.png")

    _render_wireframe(
        scene,
        cameras[0],
        render_root / manifest["diagnostics"]["wireframe"],
        [production_body, production_head],
        collections["_REVIEW_DIAGNOSTICS"],
    )
    _set_render_visibility(bpy.context.scene.objects, production_renderables)

    body_camera_data = bpy.data.cameras.new("Camera_body_comparison")
    body_camera_data.lens = 62.0
    body_camera = bpy.data.objects.new("Camera_body_comparison", body_camera_data)
    collections["_REVIEW_CAMERAS"].objects.link(body_camera)
    body_camera.location = (0.0, -3.0, 0.90)
    body_camera.rotation_euler = (
        Vector((0.0, 0.0, 0.90)) - body_camera.location
    ).to_track_quat("-Z", "Y").to_euler()
    _mark_object(body_camera, role="review_camera", exportable=False, renderable=False)

    _set_render_visibility(bpy.context.scene.objects, {sam_reference.name})
    _render(
        scene,
        body_camera,
        render_root / manifest["diagnostics"]["sam3d_reference_body"],
    )
    _set_render_visibility(
        bpy.context.scene.objects,
        {production_body.name, production_head.name, *(eye.name for eye in eyes)},
    )
    _render(
        scene,
        body_camera,
        render_root / manifest["diagnostics"]["production_body"],
    )
    _set_render_visibility(bpy.context.scene.objects, {highpoly_main.name})
    _render(
        scene,
        cameras[0],
        render_root / manifest["diagnostics"]["highpoly_reference_head"],
    )
    _set_render_visibility(
        bpy.context.scene.objects,
        {production_head.name, *(eye.name for eye in eyes), brows.name, eyelashes.name},
    )
    _render(
        scene,
        cameras[0],
        render_root / manifest["diagnostics"]["production_head"],
    )
    _set_render_visibility(bpy.context.scene.objects, production_renderables)

    inventory = {
        "schema_version": "1.0",
        "status": "pending_gate",
        "collections": sorted(collection.name for collection in bpy.data.collections),
        "objects": [_object_inventory(obj) for obj in bpy.context.scene.objects],
    }
    gate_result = validate_scene_inventory(inventory)
    visual_gate_result = validate_visual_profile(
        {
            "body_fit": body_fit,
            "skin_material": skin_material,
        }
    )
    inventory["status"] = "passed"
    inventory["gate_result"] = gate_result
    inventory["visual_gate_result"] = visual_gate_result
    inventory_path = args.output_root / "exported-mesh-inventory.json"
    _write_json(inventory_path, inventory)

    bpy.ops.object.select_all(action="DESELECT")
    export_objects = [
        obj
        for obj in bpy.context.scene.objects
        if bool(obj.get("exportable", False))
    ]
    for obj in export_objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.export_scene.gltf(
        filepath=str(args.output_root / "juana-clean-production-provisional.glb"),
        export_format="GLB",
        use_selection=True,
        export_extras=True,
        export_animations=False,
        export_morph=False,
        export_skins=True,
        export_all_influences=True,
        export_yup=True,
    )

    fit_report = {
        "schema_version": "1.0",
        "status": "passed",
        "body_fit": body_fit,
        "skin_material": skin_material,
        "visual_gate_result": visual_gate_result,
        "highpoly_alignment": highpoly_alignment,
        "face_cage": face_cage,
        "masked_shrinkwrap": shrinkwrap,
        "texture_bake": texture_bake,
        "production_topology": {
            "body": _object_inventory(production_body),
            "head": _object_inventory(production_head),
            "eyes": [_object_inventory(eye) for eye in eyes],
            "rig": _object_inventory(armature),
        },
        "donor_vrm": donor_vrm_report,
        "provisional_boundary": {
            "visual_canon_approved": False,
            "final_vrm": False,
            "next_gate": "Kathy visual and topology review",
        },
    }
    _write_json(args.output_root / "production-fit-report.json", fit_report)
    _write_json(
        args.output_root / "scene-report.json",
        {
            "schema_version": "1.0",
            "status": "ready_for_visual_and_topology_review",
            "ticket": "GH-22",
            "collections": inventory["collections"],
            "gate_result": gate_result,
            "renders": sorted(path.name for path in render_root.glob("*.png")),
            "provisional_boundary": fit_report["provisional_boundary"],
        },
    )

    for name in ("_REFERENCE_SAM3D", "_REFERENCE_HIGHPOLY", "_DONOR_VRM", "_RIG", "_EXPORT"):
        collections[name].hide_viewport = True
    bpy.ops.object.select_all(action="DESELECT")
    scene.camera = cameras[0]
    bpy.ops.wm.save_as_mainfile(
        filepath=str(args.output_root / "juana-clean-production-provisional.blend")
    )
    print("GH22_CLEAN_PRODUCTION_AUTHORING_COMPLETE")


if __name__ == "__main__":
    main()
