"""Author and render the provisional GH-22 Juana talking bust inside Blender."""

from __future__ import annotations

import argparse
import importlib
import json
import math
import sys
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

PROXY_BUST_CUTOFF_WORLD_Z = 1.18


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


def _import_mpfb(module_suffix: str) -> Any:
    candidates = (
        f"bl_ext.user_default.mpfb.{module_suffix}",
        f"mpfb.{module_suffix}",
    )
    for module_name in candidates:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
    loaded = next(
        (name for name in sys.modules if name.endswith(f".mpfb.{module_suffix}")),
        None,
    )
    if loaded is not None:
        return importlib.import_module(loaded)
    raise RuntimeError(f"MPFB module {module_suffix} is not available in this Blender profile.")


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for collection in tuple(bpy.data.collections):
        if collection.users == 0:
            bpy.data.collections.remove(collection)


def _material(
    name: str,
    color: Sequence[float],
    *,
    metallic: float = 0.0,
    roughness: float = 0.45,
    coat: float = 0.0,
    specular_ior_level: float | None = None,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color[:3], color[3])
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
    if specular_ior_level is not None and "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = specular_ior_level
    if "Coat Weight" in principled.inputs:
        principled.inputs["Coat Weight"].default_value = coat
    return material


def _skin_material(texture_path: Path) -> bpy.types.Material:
    material = bpy.data.materials.new("Juana_Skin_Material")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.name = "Verified_MakeHuman_Skin_Texture"
    image_node.image = bpy.data.images.load(str(texture_path), check_existing=True)
    hue = nodes.new("ShaderNodeHueSaturation")
    hue.inputs["Hue"].default_value = 0.5
    hue.inputs["Saturation"].default_value = 0.94
    hue.inputs["Value"].default_value = 0.79
    warm_tint = nodes.new("ShaderNodeMixRGB")
    warm_tint.name = "Juana_Warm_Golden_Brown_Tint"
    warm_tint.blend_type = "MULTIPLY"
    warm_tint.inputs["Fac"].default_value = 0.32
    warm_tint.inputs[2].default_value = (0.72, 0.60, 0.48, 1.0)
    links.new(image_node.outputs["Color"], hue.inputs["Color"])
    links.new(hue.outputs["Color"], warm_tint.inputs[1])
    links.new(warm_tint.outputs["Color"], principled.inputs["Base Color"])
    principled.inputs["Roughness"].default_value = 0.64
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = 0.25
    if "Coat Weight" in principled.inputs:
        principled.inputs["Coat Weight"].default_value = 0.0
    if "Subsurface Weight" in principled.inputs:
        principled.inputs["Subsurface Weight"].default_value = 0.035
    if "Subsurface Radius" in principled.inputs:
        principled.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.25)
    material["approved_tone"] = "warm_golden_brown"
    material["status"] = "provisional_visual_assumption"
    return material


def _hair_texture_material(
    name: str,
    texture_path: Path,
    tint: Sequence[float],
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.name = "Verified_MakeHuman_Long01_Texture"
    image_node.image = bpy.data.images.load(str(texture_path), check_existing=True)
    multiply = nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs["Fac"].default_value = 1.0
    multiply.inputs[2].default_value = (*tint[:3], 1.0)
    links.new(image_node.outputs["Color"], multiply.inputs[1])
    links.new(multiply.outputs["Color"], principled.inputs["Base Color"])
    links.new(image_node.outputs["Alpha"], principled.inputs["Alpha"])
    principled.inputs["Roughness"].default_value = 0.82
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = 0.16
    if "Coat Weight" in principled.inputs:
        principled.inputs["Coat Weight"].default_value = 0.0
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    return material


def _undercut_material() -> bpy.types.Material:
    material = bpy.data.materials.new("Juana_Hair_Undercut_Texture")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 150.0
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.72
    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.28
    ramp.color_ramp.elements[0].color = (0.0003, 0.0001, 0.00005, 1.0)
    ramp.color_ramp.elements[1].position = 0.72
    ramp.color_ramp.elements[1].color = (0.008, 0.0025, 0.001, 1.0)
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.12
    bump.inputs["Distance"].default_value = 0.0004
    links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], principled.inputs["Base Color"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], principled.inputs["Normal"])
    principled.inputs["Roughness"].default_value = 0.82
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = 0.12
    return material


def _alpha_detail_material(
    name: str,
    texture_path: Path,
    *,
    value: float,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.name = f"Verified_{name}_Texture"
    image_node.image = bpy.data.images.load(str(texture_path), check_existing=True)
    detail_value = max(0.001, value * 0.018)
    principled.inputs["Base Color"].default_value = (
        detail_value,
        detail_value * 0.45,
        detail_value * 0.22,
        1.0,
    )
    links.new(image_node.outputs["Alpha"], principled.inputs["Alpha"])
    principled.inputs["Roughness"].default_value = 0.82
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = 0.1
    if hasattr(material, "surface_render_method"):
        material.surface_render_method = "DITHERED"
    return material


def _assign_material(obj: bpy.types.Object, material: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(material)


def _smooth(obj: bpy.types.Object) -> None:
    if obj.type == "MESH":
        for polygon in obj.data.polygons:
            polygon.use_smooth = True


def _load_targets(
    target_service: Any,
    body: bpy.types.Object,
    target_root: Path,
    controls: Sequence[tuple[str, str, float]],
) -> None:
    for name, relative_path, weight in controls:
        key = target_service.load_target(
            body,
            str(target_root / relative_path),
            weight=weight,
            name=name,
        )
        key.slider_min = 0.0
        key.slider_max = 1.0


def _combine_shape_keys(
    body: bpy.types.Object,
    name: str,
    components: Sequence[tuple[str, float]],
) -> None:
    keys = body.data.shape_keys.key_blocks
    basis = keys["Basis"]
    combined = body.shape_key_add(name=name, from_mix=False)
    for index, point in enumerate(combined.data):
        coordinate = basis.data[index].co.copy()
        for component_name, weight in components:
            coordinate += (keys[component_name].data[index].co - basis.data[index].co) * weight
        point.co = coordinate
    combined.value = 0.0
    combined.slider_min = 0.0
    combined.slider_max = 1.0


def _bone_world_position(armature: bpy.types.Object, bone_name: str) -> Vector:
    bone = armature.data.bones[bone_name]
    return armature.matrix_world @ bone.head_local


def _parent_to_bone(
    obj: bpy.types.Object,
    armature: bpy.types.Object,
    bone_name: str,
) -> None:
    world_matrix = obj.matrix_world.copy()
    obj.parent = armature
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.matrix_world = world_matrix


def _join_objects(objects: Sequence[bpy.types.Object], name: str) -> bpy.types.Object:
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    bpy.ops.object.join()
    objects[0].name = name
    return objects[0]


def _create_eye(
    side: str,
    center: Vector,
    armature: bpy.types.Object,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object:
    center = center + Vector((0.0, 0.005, 0.0))
    parts = []
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=1.0,
        location=center,
    )
    sclera = bpy.context.object
    sclera.scale = (0.0170, 0.0144, 0.0087)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _assign_material(sclera, materials["sclera"])
    parts.append(sclera)

    for radius_x, radius_z, depth, offset, material_name in (
        (0.0088, 0.0067, 0.0019, 0.0135, "iris_rim"),
        (0.0074, 0.0056, 0.0017, 0.0148, "iris"),
        (0.0033, 0.0028, 0.0014, 0.0161, "pupil"),
        (0.00055, 0.00055, 0.0004, 0.0171, "eye_highlight"),
    ):
        highlight_x = -0.0022 if material_name == "eye_highlight" else 0.0
        highlight_z = 0.0025 if material_name == "eye_highlight" else 0.0
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=32,
            ring_count=16,
            radius=1.0,
            location=(
                center.x + highlight_x,
                center.y - offset,
                center.z + highlight_z,
            ),
        )
        detail = bpy.context.object
        detail.scale = (radius_x, depth, radius_z)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        _assign_material(detail, materials[material_name])
        parts.append(detail)

    eye = _join_objects(parts, f"Juana_Eye_{side}")
    _smooth(eye)
    _parent_to_bone(eye, armature, f"eye.{side}")
    eye["source"] = "MakeHuman hm08 eye placement; repository-authored geometry"
    eye["status"] = "provisional_visual_assumption"
    eye["appearance"] = "narrow_almond_amber"
    return eye


def _create_iris_overlay(
    side: str,
    center: Vector,
    armature: bpy.types.Object,
    materials: dict[str, bpy.types.Material],
) -> bpy.types.Object:
    parts = []
    for radius_x, radius_z, depth, y_offset, material_name in (
        (0.0083, 0.0053, 0.0008, 0.0000, "iris_rim"),
        (0.0075, 0.0048, 0.0007, -0.0006, "iris"),
        (0.0032, 0.0024, 0.0006, -0.0011, "pupil"),
        (0.00042, 0.00042, 0.00025, -0.0015, "eye_highlight"),
    ):
        highlight_x = -0.0020 if material_name == "eye_highlight" else 0.0
        highlight_z = 0.0020 if material_name == "eye_highlight" else 0.0
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=32,
            ring_count=16,
            radius=1.0,
            location=(
                center.x + highlight_x,
                center.y + y_offset,
                center.z + highlight_z,
            ),
        )
        detail = bpy.context.object
        detail.scale = (radius_x, depth, radius_z)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        _assign_material(detail, materials[material_name])
        parts.append(detail)
    overlay = _join_objects(parts, f"Juana_Iris_Overlay_{side}")
    _smooth(overlay)
    bpy.context.view_layer.update()
    _parent_to_bone(overlay, armature, f"eye.{side}")
    overlay["source"] = "Repository-authored overlay aligned to Hunyuan eye landmarks"
    overlay["status"] = "functional_provisional"
    overlay["appearance"] = "warm_amber_brown"
    return overlay


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _add_likeness_pass_shape(
    body: bpy.types.Object,
    calibration: dict[str, Any],
) -> bpy.types.ShapeKey:
    keys = body.data.shape_keys.key_blocks
    basis = keys["Basis"]
    likeness = body.shape_key_add(name="identity_likeness_pass_3", from_mix=False)
    eye_line = 1.553
    lower_face_compression = 1.0 - float(calibration["eye_to_chin_compression"])
    lower_face_max_up = float(calibration["lower_face_max_up_m"])
    for index, point in enumerate(likeness.data):
        coordinate = basis.data[index].co.copy()
        original = coordinate.copy()
        front_weight = _clamp01((-original.y + 0.020) / 0.10)
        lateral_direction = 0.0 if abs(original.x) < 1e-7 else math.copysign(1.0, original.x)

        if 1.47 < original.z < 1.57 and abs(original.x) < 0.105:
            cheek_weight = 1.0 - abs(original.z - 1.52) / 0.05
            lateral_weight = _clamp01(abs(original.x) / 0.065)
            coordinate.x += (
                lateral_direction * 0.0040 * cheek_weight * front_weight * lateral_weight
            )

        if 1.365 < original.z < 1.495 and abs(original.x) < 0.105:
            jaw_weight = 1.0 - abs(original.z - 1.43) / 0.065
            lateral_weight = 0.35 + 0.65 * _clamp01(abs(original.x) / 0.07)
            coordinate.x += lateral_direction * 0.0045 * jaw_weight * front_weight * lateral_weight

        if 1.32 < original.z < eye_line and abs(original.x) < 0.115:
            compression = min(
                lower_face_max_up,
                (eye_line - original.z) * lower_face_compression,
            )
            neck_fade = _clamp01((original.z - 1.32) / 0.02)
            side_fade = _clamp01((0.115 - abs(original.x)) / 0.025)
            coordinate.z += compression * front_weight * neck_fade * side_fade

        absolute_x = abs(original.x)
        if 1.525 < original.z < 1.58 and 0.006 < absolute_x < 0.073 and original.y < -0.105:
            eye_weight = 1.0 - abs(absolute_x - 0.035) / 0.038
            eye_weight = _clamp01(eye_weight)
            coordinate.x += lateral_direction * 0.0042 * eye_weight
            coordinate.z += (1.552 - original.z) * 0.34 * eye_weight
            outer_corner = _clamp01((absolute_x - 0.036) / 0.025)
            coordinate.z += 0.0014 * outer_corner * eye_weight

        if original.y < -0.105 and absolute_x < 0.038:
            if 1.495 < original.z < 1.565:
                bridge_weight = 1.0 - abs(original.z - 1.53) / 0.035
                coordinate.y -= 0.0040 * _clamp01(bridge_weight)
                coordinate.x *= 1.02
            elif 1.455 < original.z <= 1.495:
                alar_weight = 1.0 - abs(original.z - 1.475) / 0.02
                coordinate.y -= 0.0040 * _clamp01(alar_weight)
                coordinate.x += (
                    lateral_direction
                    * 0.0012
                    * _clamp01(alar_weight)
                    * _clamp01(absolute_x / 0.032)
                )

        if 1.415 < original.z < 1.48 and absolute_x < 0.063 and original.y < -0.115:
            lip_weight = 1.0 - abs(original.z - 1.448) / 0.033
            corner_weight = 1.0 - _clamp01(absolute_x / 0.063)
            coordinate.y -= 0.0015 * _clamp01(lip_weight) * (0.45 + 0.55 * corner_weight)
            if 1.448 < original.z < 1.47 and absolute_x < 0.018:
                coordinate.z += 0.0013 * (1.0 - absolute_x / 0.018)

        if 1.335 < original.z < 1.415 and absolute_x < 0.055:
            chin_weight = _clamp01(1.0 - abs(original.z - 1.375) / 0.04)
            coordinate.y -= 0.0035 * chin_weight * front_weight

        point.co = coordinate
    likeness.value = 1.0
    likeness.slider_min = 0.0
    likeness.slider_max = 1.0
    body["likeness_revision"] = "gh-22-likeness-pass-3"
    body["likeness_status"] = "changes_requested_provisional"
    body["likeness_transfer_method"] = "manual_landmark_calibration"
    return likeness


def _create_eyebrows(
    left_center: Vector,
    right_center: Vector,
    body: bpy.types.Object,
    armature: bpy.types.Object,
    material: bpy.types.Material,
) -> bpy.types.Object:
    vertices: list[tuple[float, float, float]] = []
    faces: list[tuple[int, int, int, int]] = []
    x_offsets = (0.026, 0.014, 0.002, -0.010, -0.018)
    z_offsets = (0.018, 0.024, 0.028, 0.026, 0.022)
    y_offsets = (-0.021, -0.025, -0.026, -0.022, -0.015)
    half_heights = (0.0014, 0.0025, 0.0030, 0.0028, 0.0018)

    for center, mirror in ((left_center, 1.0), (right_center, -1.0)):
        start = len(vertices)
        for x_offset, y_offset, z_offset, half_height in zip(
            x_offsets,
            y_offsets,
            z_offsets,
            half_heights,
            strict=True,
        ):
            x = center.x + mirror * x_offset
            y = center.y + y_offset
            z = center.z + z_offset
            vertices.extend(
                (
                    (x, y, z + half_height),
                    (x, y, z - half_height),
                )
            )
        for segment in range(len(x_offsets) - 1):
            current = start + segment * 2
            following = current + 2
            faces.append((current, following, following + 1, current + 1))

    mesh = bpy.data.meshes.new("Juana_Eyebrows_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    brows = bpy.data.objects.new("Juana_Eyebrows", mesh)
    bpy.context.collection.objects.link(brows)
    subdivision = brows.modifiers.new("Juana brow curvature", "SUBSURF")
    subdivision.levels = 2
    subdivision.render_levels = 2
    shrinkwrap = brows.modifiers.new("Juana brow surface fit", "SHRINKWRAP")
    shrinkwrap.target = body
    shrinkwrap.wrap_method = "NEAREST_SURFACEPOINT"
    shrinkwrap.wrap_mode = "OUTSIDE_SURFACE"
    shrinkwrap.offset = 0.0015
    solidify = brows.modifiers.new("Juana brow thickness", "SOLIDIFY")
    solidify.thickness = 0.0015
    solidify.offset = 0.0
    bevel = brows.modifiers.new("Juana brow edge finish", "BEVEL")
    bevel.width = 0.001
    bevel.segments = 3
    _smooth(brows)
    _parent_to_bone(brows, armature, "head")
    brows["source_asset"] = "Repository-authored geometry fitted to approved Juana references"
    brows["appearance"] = "thick_dark_strong_arch"
    brows["status"] = "provisional_visual_assumption"
    return brows


def _create_curve_object(
    name: str,
    splines: Sequence[Sequence[Sequence[float]]],
    bevel_depth: float,
    material: bpy.types.Material,
    *,
    radii: Sequence[float] | None = None,
) -> bpy.types.Object:
    curve = bpy.data.curves.new(name, "CURVE")
    curve.dimensions = "3D"
    curve.resolution_u = 4
    curve.bevel_depth = bevel_depth
    curve.bevel_resolution = 3
    curve.use_fill_caps = True
    for points in splines:
        spline = curve.splines.new("BEZIER")
        spline.bezier_points.add(len(points) - 1)
        for index, (point, coordinate) in enumerate(zip(spline.bezier_points, points, strict=True)):
            point.co = coordinate
            point.handle_left_type = "AUTO"
            point.handle_right_type = "AUTO"
            point.radius = radii[index] if radii and index < len(radii) else 1.0
    obj = bpy.data.objects.new(name, curve)
    bpy.context.collection.objects.link(obj)
    curve.materials.append(material)
    return obj


def _create_scalp_cap(
    center: Vector,
    radii: Vector,
    material: bpy.types.Material,
) -> bpy.types.Object:
    segments = 64
    rings = 20
    vertices: list[tuple[float, float, float]] = [(center.x, center.y, center.z + radii.z)]
    candidate_faces: list[tuple[int, ...]] = []
    for ring in range(1, rings + 1):
        amount = ring / rings
        for segment in range(segments):
            phi = 2.0 * math.pi * segment / segments
            frontness = max(0.0, -math.sin(phi))
            backness = max(0.0, math.sin(phi))
            max_theta = 1.62 - 0.48 * frontness + 0.22 * backness
            theta = amount * max_theta
            vertices.append(
                (
                    center.x + radii.x * math.sin(theta) * math.cos(phi),
                    center.y + radii.y * math.sin(theta) * math.sin(phi),
                    center.z + radii.z * math.cos(theta),
                )
            )
    for segment in range(segments):
        candidate_faces.append((0, 1 + segment, 1 + (segment + 1) % segments))
    for ring in range(1, rings):
        current = 1 + (ring - 1) * segments
        following = current + segments
        for segment in range(segments):
            next_segment = (segment + 1) % segments
            candidate_faces.append(
                (
                    current + segment,
                    following + segment,
                    following + next_segment,
                    current + next_segment,
                )
            )
    faces = []
    crown_threshold = center.z + radii.z * 0.57
    for face in candidate_faces:
        face_center = sum((Vector(vertices[index]) for index in face), Vector()) / len(face)
        if (
            face_center.z >= crown_threshold
            or face_center.x >= -0.004
            or face_center.y >= center.y + radii.y * 0.58
        ):
            faces.append(face)
    mesh = bpy.data.meshes.new("Juana_Hair_Scalp_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new("Juana_Hair_Scalp", mesh)
    bpy.context.collection.objects.link(obj)
    _smooth(obj)
    solidify = obj.modifiers.new("Scalp thickness", "SOLIDIFY")
    solidify.thickness = 0.0015
    obj["hair_side_convention"] = "close-cut anatomical left; long anatomical right"
    return obj


def _mesh_vertex_components(mesh: bpy.types.Mesh) -> list[list[int]]:
    adjacency = [set() for _ in mesh.vertices]
    for edge in mesh.edges:
        start, end = edge.vertices
        adjacency[start].add(end)
        adjacency[end].add(start)
    visited: set[int] = set()
    components: list[list[int]] = []
    for start in range(len(mesh.vertices)):
        if start in visited:
            continue
        pending = [start]
        visited.add(start)
        component = []
        while pending:
            index = pending.pop()
            component.append(index)
            for neighbor in adjacency[index]:
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        components.append(component)
    return components


def _cut_system_hair_for_asymmetry(
    hair: bpy.types.Object,
    eye_center: Vector,
) -> int:
    mesh = hair.data
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(mesh)
    delete_vertices = []
    for vertex in edit_mesh.verts:
        on_close_cut_side = vertex.co.x > 0.006
        below_crown = vertex.co.z < eye_center.z + 0.145
        outside_swept_crown = vertex.co.x > 0.065 and vertex.co.z < eye_center.z + 0.205
        flat_front_curtain = (
            vertex.co.x < -0.002 and vertex.co.y < -0.095 and vertex.co.z < eye_center.z + 0.085
        )
        if (on_close_cut_side and below_crown) or outside_swept_crown or flat_front_curtain:
            delete_vertices.append(vertex)
    bmesh.ops.delete(edit_mesh, geom=delete_vertices, context="VERTS")
    visited = set()
    small_islands = []
    for start in tuple(edit_mesh.verts):
        if start in visited:
            continue
        pending = [start]
        visited.add(start)
        island = []
        while pending:
            vertex = pending.pop()
            island.append(vertex)
            for edge in vertex.link_edges:
                neighbor = edge.other_vert(vertex)
                if neighbor not in visited:
                    visited.add(neighbor)
                    pending.append(neighbor)
        if len(island) < 20:
            small_islands.extend(island)
    if small_islands:
        bmesh.ops.delete(edit_mesh, geom=small_islands, context="VERTS")
    for vertex in edit_mesh.verts:
        if vertex.co.x < -0.004:
            side_weight = min(1.0, (-vertex.co.x - 0.004) / 0.08)
            vertex.co.y -= 0.018 * side_weight
            vertical_phase = (vertex.co.z - eye_center.z) * 38.0
            lateral_phase = (-vertex.co.x) * 24.0
            wave = math.sin(vertical_phase + lateral_phase)
            vertex.co.y += 0.018 * wave * side_weight
            vertex.co.x += 0.011 * wave * side_weight
            if vertex.co.z < eye_center.z:
                vertex.co.x -= 0.008 * side_weight
    edit_mesh.to_mesh(mesh)
    edit_mesh.free()
    mesh.update()
    clump_components = [
        component for component in _mesh_vertex_components(mesh) if len(component) >= 20
    ]
    clump_components.sort(key=min)
    for component_index, component in enumerate(clump_components):
        phase = component_index * 0.73
        for vertex_index in component:
            vertex = mesh.vertices[vertex_index]
            if vertex.co.x >= 0.01:
                continue
            side_weight = min(1.0, max(0.0, (-vertex.co.x + 0.01) / 0.10))
            wave = math.sin((vertex.co.z - eye_center.z) * 22.0 + phase)
            vertex.co.x += 0.0055 * wave * side_weight
            vertex.co.y += 0.0075 * wave * side_weight
    mesh.update()
    hair["hair_side_convention"] = "close-cut anatomical left; long anatomical right"
    hair["construction"] = (
        f"{len(clump_components)} connected large flowing slightly wavy mesh clumps"
    )
    hair["flowing_clump_count"] = len(clump_components)
    hair["source_asset"] = "MakeHuman system asset long01, CC0-1.0"
    hair["status"] = "provisional_visual_assumption"
    return len(clump_components)


def _cut_short_hair_for_undercut(
    hair: bpy.types.Object,
    eye_center: Vector,
) -> None:
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(hair.data)
    delete_vertices = [
        vertex
        for vertex in edit_mesh.verts
        if vertex.co.x < -0.012 or (vertex.co.z < eye_center.z - 0.045 and vertex.co.y < -0.025)
    ]
    bmesh.ops.delete(edit_mesh, geom=delete_vertices, context="VERTS")
    edit_mesh.to_mesh(hair.data)
    edit_mesh.free()
    hair.data.update()
    hair["construction"] = "anatomical-left close-cut undercut patch"
    hair["hair_side_convention"] = (
        "close-cut anatomical left; covered by long hair on anatomical right"
    )
    hair["source_asset"] = "MakeHuman system asset short01, CC0-1.0"
    hair["status"] = "provisional_visual_assumption"


def _create_hair(
    body: bpy.types.Object,
    eye_center: Vector,
    materials: dict[str, bpy.types.Material],
    long_hair: bpy.types.Object,
    short_hair: bpy.types.Object,
) -> list[bpy.types.Object]:
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    evaluated_mesh = evaluated.to_mesh()
    _ = max(vertex.co.z for vertex in evaluated_mesh.vertices)
    evaluated.to_mesh_clear()
    long_hair.name = "Juana_Hair_Long_Right"
    _cut_system_hair_for_asymmetry(long_hair, eye_center)
    _assign_material(long_hair, materials["hair_texture"])
    long_hair.location.x -= 0.006
    long_hair.location.y -= 0.010
    _smooth(long_hair)

    short_hair.name = "Juana_Hair_Close_Cut_Base"
    _cut_short_hair_for_undercut(short_hair, eye_center)
    _assign_material(short_hair, materials["undercut"])
    _smooth(short_hair)
    return [short_hair, long_hair]


def _smooth_underlayer_neckline(obj: bpy.types.Object) -> None:
    edge_face_count: dict[tuple[int, int], int] = {}
    for polygon in obj.data.polygons:
        indices = tuple(polygon.vertices)
        for start, end in zip(indices, (*indices[1:], indices[0]), strict=True):
            edge = tuple(sorted((start, end)))
            edge_face_count[edge] = edge_face_count.get(edge, 0) + 1
    boundary_vertices = {
        index for edge, count in edge_face_count.items() if count == 1 for index in edge
    }
    for index in boundary_vertices:
        vertex = obj.data.vertices[index]
        if vertex.co.y < -0.02 and vertex.co.z > 1.145:
            vertex.co.z = 1.205
    obj.data.update()


def _open_system_jacket(
    jacket: bpy.types.Object,
    material: bpy.types.Material,
) -> None:
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(jacket.data)
    opening_base = 0.014
    opening_slope = 0.43
    opening_start = 1.02
    geometry = [*edit_mesh.verts, *edit_mesh.edges, *edit_mesh.faces]
    for side in (-1.0, 1.0):
        bmesh.ops.bisect_plane(
            edit_mesh,
            geom=geometry,
            dist=0.00001,
            plane_co=(side * opening_base, 0.0, opening_start),
            plane_no=(1.0, 0.0, -side * opening_slope),
            clear_inner=False,
            clear_outer=False,
        )
        geometry = [*edit_mesh.verts, *edit_mesh.edges, *edit_mesh.faces]
    delete_faces = []
    for face in edit_mesh.faces:
        center = face.calc_center_median()
        opening = opening_base + max(0.0, center.z - opening_start) * opening_slope
        if center.y < -0.02 and center.z > opening_start and abs(center.x) < opening:
            delete_faces.append(face)
    bmesh.ops.delete(edit_mesh, geom=delete_faces, context="FACES")
    loose_vertices = [vertex for vertex in edit_mesh.verts if not vertex.link_faces]
    bmesh.ops.delete(edit_mesh, geom=loose_vertices, context="VERTS")
    edit_mesh.to_mesh(jacket.data)
    edit_mesh.free()
    jacket.data.update()
    jacket.name = "Juana_Outfit_Jacket"
    _assign_material(jacket, material)
    _smooth(jacket)
    bevel = jacket.modifiers.new("Juana jacket opening finish", "BEVEL")
    bevel.width = 0.0012
    bevel.segments = 3
    jacket["construction"] = "open pearl-white leather-or-latex technical jacket"
    jacket["source_asset"] = "MakeHuman female_elegantsuit01 topology, CC0-1.0"
    jacket["status"] = "provisional_visual_assumption"


def _prepare_system_underlayer(
    underlayer: bpy.types.Object,
    material: bpy.types.Material,
) -> None:
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(underlayer.data)
    bmesh.ops.bisect_plane(
        edit_mesh,
        geom=[*edit_mesh.verts, *edit_mesh.edges, *edit_mesh.faces],
        dist=0.00001,
        plane_co=(0.0, 0.0, 1.205),
        plane_no=(0.0, 0.0, 1.0),
        clear_inner=False,
        clear_outer=False,
    )
    delete_faces = [
        face
        for face in edit_mesh.faces
        if face.calc_center_median().y < -0.02 and face.calc_center_median().z > 1.205
    ]
    bmesh.ops.delete(edit_mesh, geom=delete_faces, context="FACES")
    loose_vertices = [vertex for vertex in edit_mesh.verts if not vertex.link_faces]
    bmesh.ops.delete(edit_mesh, geom=loose_vertices, context="VERTS")
    edit_mesh.to_mesh(underlayer.data)
    edit_mesh.free()
    underlayer.data.update()
    underlayer.name = "Juana_Outfit_Inner"
    _assign_material(underlayer, material)
    _smooth(underlayer)
    underlayer["construction"] = "fitted pearl-white low straight neckline"
    underlayer["source_asset"] = "MakeHuman female_casualsuit02 topology, CC0-1.0"
    underlayer["status"] = "provisional_visual_assumption"


def _create_elliptical_band(
    name: str,
    *,
    center: Vector,
    radius_x: float,
    radius_y: float,
    half_height: float,
    material: bpy.types.Material,
) -> bpy.types.Object:
    segments = 64
    vertices = []
    for z in (center.z - half_height, center.z + half_height):
        for index in range(segments):
            angle = 2.0 * math.pi * index / segments
            vertices.append(
                (
                    center.x + radius_x * math.cos(angle),
                    center.y + radius_y * math.sin(angle),
                    z,
                )
            )
    faces = []
    for index in range(segments):
        following = (index + 1) % segments
        faces.append((index, following, segments + following, segments + index))
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    _smooth(obj)
    solidify = obj.modifiers.new(f"{name} thickness", "SOLIDIFY")
    solidify.thickness = 0.0025
    solidify.offset = 0.0
    bevel = obj.modifiers.new(f"{name} edge finish", "BEVEL")
    bevel.width = 0.001
    bevel.segments = 2
    return obj


def _surface_shell(
    body: bpy.types.Object,
    name: str,
    predicate: Callable[[Vector], bool],
    material: bpy.types.Material,
    *,
    offset: float,
    thickness: float,
) -> bpy.types.Object:
    evaluated = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    source = evaluated.to_mesh()
    selected = []
    for polygon in source.polygons:
        center = sum((source.vertices[index].co for index in polygon.vertices), Vector()) / len(
            polygon.vertices
        )
        if predicate(center):
            selected.append(polygon)
    referenced = sorted({index for polygon in selected for index in polygon.vertices})
    index_map = {source_index: target_index for target_index, source_index in enumerate(referenced)}
    vertices = [
        tuple(source.vertices[index].co + source.vertices[index].normal * offset)
        for index in referenced
    ]
    faces = [tuple(index_map[index] for index in polygon.vertices) for polygon in selected]
    evaluated.to_mesh_clear()
    mesh = bpy.data.meshes.new(f"{name}_Mesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.materials.append(material)
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    _smooth(obj)
    subdivision = obj.modifiers.new(f"{name} surface smoothing", "SUBSURF")
    subdivision.levels = 1
    subdivision.render_levels = 1
    solidify = obj.modifiers.new(f"{name} thickness", "SOLIDIFY")
    solidify.thickness = thickness
    solidify.offset = 1.0
    bevel = obj.modifiers.new(f"{name} edge finish", "BEVEL")
    bevel.width = 0.0015
    bevel.segments = 3
    return obj


def _import_meta_body_calibration(
    path: Path,
    target_eye_midpoint: Vector,
) -> bpy.types.Object:
    existing_objects = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported = [obj for obj in bpy.data.objects if obj not in existing_objects]
    imported_bodies = [
        obj
        for obj in imported
        if obj.type == "MESH" and obj.name.startswith("Juana_Meta_MHR_Body_Calibration")
    ]
    imported_armatures = [obj for obj in imported if obj.type == "ARMATURE"]
    if len(imported_bodies) != 1 or len(imported_armatures) != 1:
        summary = [(obj.name, obj.type) for obj in imported]
        raise RuntimeError(f"Unexpected Meta MHR calibration import: {summary}.")

    body = imported_bodies[0]
    source_armature = imported_armatures[0]
    source_eye_midpoint = sum(
        (
            source_armature.matrix_world @ source_armature.data.bones[bone_name].head_local
            for bone_name in ("l_eye", "r_eye")
        ),
        Vector(),
    ) / 2.0
    source_armature.matrix_world = (
        Matrix.Translation(target_eye_midpoint - source_eye_midpoint)
        @ source_armature.matrix_world
    )
    bpy.context.view_layer.update()

    bpy.ops.object.select_all(action="DESELECT")
    body.select_set(True)
    bpy.context.view_layer.objects.active = body
    for modifier in tuple(body.modifiers):
        if modifier.type == "ARMATURE":
            bpy.ops.object.modifier_apply(modifier=modifier.name)
    world_matrix = body.matrix_world.copy()
    body.parent = None
    body.matrix_world = world_matrix
    body.data.transform(body.matrix_world)
    body.matrix_world = Matrix.Identity(4)

    for obj in imported:
        if obj != body and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    body.name = "Juana_Meta_MHR_Body_Calibration_Surface"
    body.data.name = "Juana_Meta_MHR_Body_Calibration_Surface_Mesh"
    body.hide_render = True
    body["status"] = "provisional_body_and_rig_calibration"
    body["source_sha256"] = (
        "8c7afc60df553b66e1cc3143fc2c04878475e97433d9d6af190393f48eec9ccb"
    )
    body["production_base"] = False
    body["face_likeness_source"] = False
    body["visible_use"] = "hidden_body_and_rig_calibration_only"
    return body


def _create_outfit(
    body: bpy.types.Object,
    armature: bpy.types.Object,
    materials: dict[str, bpy.types.Material],
    system_underlayer: bpy.types.Object,
    system_jacket: bpy.types.Object,
) -> list[bpy.types.Object]:
    inner = system_underlayer
    _prepare_system_underlayer(inner, materials["outfit_inner"])
    jacket_obj = system_jacket
    _open_system_jacket(jacket_obj, materials["outfit_jacket"])
    choker = _create_elliptical_band(
        "Juana_Choker",
        center=Vector((0.0, -0.026, 1.429)),
        radius_x=0.058,
        radius_y=0.053,
        half_height=0.015,
        material=materials["choker"],
    )
    choker["construction"] = "surface-fitted black JUANA IA choker"
    _parent_to_bone(choker, armature, "neck03")

    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.028, 1.429), scale=(0.008, 0.004, 0.009))
    closure = bpy.context.object
    closure.name = "Juana_Choker_Gold_Closure"
    _assign_material(closure, materials["gold"])
    closure_bevel = closure.modifiers.new("Gold closure edge finish", "BEVEL")
    closure_bevel.width = 0.002
    closure_bevel.segments = 3
    _parent_to_bone(closure, armature, "neck03")

    bpy.ops.object.text_add(location=(0.0, -0.080, 1.427), rotation=(math.pi / 2.0, 0.0, 0.0))
    text = bpy.context.object
    text.name = "Juana_Choker_Text"
    text.data.body = "JUANA IA"
    text.data.align_x = "CENTER"
    text.data.align_y = "CENTER"
    text.data.size = 0.011
    text.data.extrude = 0.0004
    text.data.materials.append(materials["choker_text"])
    _parent_to_bone(text, armature, "neck03")

    necklace = _create_curve_object(
        "Juana_Necklace",
        [
            [(-0.050, -0.058, 1.40), (-0.075, -0.112, 1.33), (0.0, -0.158, 1.25)],
            [(0.050, -0.058, 1.40), (0.075, -0.112, 1.33), (0.0, -0.158, 1.25)],
        ],
        0.00125,
        materials["gold"],
        radii=(0.7, 0.8, 0.6),
    )
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=2,
        radius=0.012,
        location=(0.0, -0.163, 1.235),
    )
    pendant = bpy.context.object
    pendant.name = "Juana_Gold_Pendant"
    pendant.scale = (0.65, 0.35, 1.2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _assign_material(pendant, materials["gold"])
    _parent_to_bone(necklace, armature, "spine01")
    _parent_to_bone(pendant, armature, "spine01")

    earrings = []
    for side, x in (("L", 0.078), ("R", -0.078)):
        bpy.ops.mesh.primitive_torus_add(
            major_segments=48,
            minor_segments=10,
            major_radius=0.013,
            minor_radius=0.0018,
            location=(x, -0.005, 1.515),
            rotation=(math.pi / 2.0, 0.0, 0.0),
        )
        earring = bpy.context.object
        earring.name = f"Juana_Gold_Hoop_{side}"
        _assign_material(earring, materials["gold"])
        _parent_to_bone(earring, armature, "head")
        earrings.append(earring)

    objects = [
        inner,
        jacket_obj,
        choker,
        closure,
        text,
        necklace,
        pendant,
        *earrings,
    ]
    for obj in objects:
        obj["status"] = "provisional_visual_assumption"
    return objects


def _create_jaw_action(armature: bpy.types.Object) -> bpy.types.Action:
    jaw = armature.pose.bones["jaw"]
    jaw.rotation_mode = "XYZ"
    action = bpy.data.actions.new("Juana_Jaw_Articulation")
    action["status"] = "functional_provisional"
    armature.animation_data_create()
    armature.animation_data.action = action
    for frame, angle in ((1, 0.0), (12, math.radians(18.0)), (24, 0.0)):
        jaw.rotation_euler = (angle, 0.0, 0.0)
        jaw.keyframe_insert(data_path="rotation_euler", frame=frame, group="jaw")
    bpy.context.scene.frame_start = 1
    bpy.context.scene.frame_end = 24
    bpy.context.scene.frame_set(1)
    return action


def _refine_identity_proxy_face(
    proxy: bpy.types.Object,
    source_matrix: Matrix,
    adjustments: dict[str, Any],
) -> None:
    skin_material_indices = {
        index
        for index, material in enumerate(proxy.data.materials)
        if material is not None
        and material.name.startswith("Juana_Hunyuan_Skin_Warm_Golden_Brown")
    }
    skin_vertices = {
        vertex_index
        for polygon in proxy.data.polygons
        if polygon.material_index in skin_material_indices
        for vertex_index in polygon.vertices
    }
    inverse_source_matrix = source_matrix.inverted()
    face_center_x = 0.040
    eye_line_z = 0.736
    eye_centers_x = (-0.013, 0.093)
    for vertex_index, vertex in enumerate(proxy.data.vertices):
        source_coordinate = source_matrix @ proxy.data.vertices[vertex_index].co
        coordinate = source_coordinate.copy()
        for eye_center_x in eye_centers_x:
            eye_weight = (
                max(0.0, 1.0 - abs(coordinate.x - eye_center_x) / 0.033)
                * max(0.0, 1.0 - abs(coordinate.z - eye_line_z) / 0.026)
                * max(0.0, min(1.0, (-0.085 - coordinate.y) / 0.06))
            )
            if eye_weight > 0.0:
                coordinate.x = eye_center_x + (coordinate.x - eye_center_x) * (
                    1.0 + 0.035 * eye_weight
                )
                vertical_scale = 1.0 - (
                    1.0 - adjustments["eye_vertical_scale"]
                ) * eye_weight
                coordinate.z = eye_line_z + (coordinate.z - eye_line_z) * vertical_scale

        if vertex_index not in skin_vertices or not (
            0.53 < source_coordinate.z < 0.82 and source_coordinate.y < -0.065
        ):
            if coordinate != source_coordinate:
                vertex.co = inverse_source_matrix @ coordinate
            continue

        if coordinate.z < eye_line_z:
            vertical_weight = min(1.0, max(0.0, (coordinate.z - 0.53) / 0.206))
            coordinate.z += (
                eye_line_z - coordinate.z
            ) * adjustments["lower_face_vertical_compression"] * vertical_weight

        cheek_weight = max(0.0, 1.0 - abs(coordinate.z - 0.685) / 0.065)
        jaw_weight = max(0.0, 1.0 - abs(coordinate.z - 0.595) / 0.065)
        lateral_offset = coordinate.x - face_center_x
        width_scale = 1.0
        width_scale += (
            adjustments["cheekbone_width_scale"] - 1.0
        ) * cheek_weight
        width_scale += (adjustments["jaw_width_scale"] - 1.0) * jaw_weight
        coordinate.x = face_center_x + lateral_offset * width_scale

        front_weight = max(0.0, min(1.0, (-0.105 - coordinate.y) / 0.07))
        nose_weight = (
            max(0.0, 1.0 - abs(coordinate.x - face_center_x) / 0.038)
            * max(0.0, 1.0 - abs(coordinate.z - 0.695) / 0.075)
            * front_weight
        )
        if nose_weight > 0.0:
            coordinate.x = face_center_x + (
                coordinate.x - face_center_x
            ) * (1.0 + (adjustments["nose_width_scale"] - 1.0) * nose_weight)
            coordinate.y -= adjustments["nose_projection_m"] * nose_weight

        lip_weight = (
            max(0.0, 1.0 - abs(coordinate.x - face_center_x) / 0.052)
            * max(0.0, 1.0 - abs(coordinate.z - 0.625) / 0.032)
            * front_weight
        )
        coordinate.y -= adjustments["lip_projection_m"] * lip_weight
        vertex.co = inverse_source_matrix @ coordinate

    proxy.data.update()
    proxy["likeness_revision"] = "gh-22-likeness-pass-4"
    proxy["face_refinement"] = "localized_reversible_vertex_deformation"


def _crop_identity_proxy_to_bust(
    proxy: bpy.types.Object,
    cutoff_world_z: float,
) -> int:
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(proxy.data)
    delete_vertices = [
        vertex
        for vertex in edit_mesh.verts
        if (proxy.matrix_world @ vertex.co).z < cutoff_world_z
    ]
    if not delete_vertices:
        edit_mesh.free()
        raise RuntimeError("The identity proxy bust crop did not select any lower-body vertices.")
    removed_vertex_count = len(delete_vertices)
    bmesh.ops.delete(edit_mesh, geom=delete_vertices, context="VERTS")
    edit_mesh.to_mesh(proxy.data)
    edit_mesh.free()
    proxy.data.update()
    proxy["presentation_scope"] = "talking_bust_only"
    proxy["presentation_cutoff_world_z"] = cutoff_world_z
    proxy["removed_lower_body_vertices"] = removed_vertex_count
    return removed_vertex_count


def _import_identity_proxy(
    path: Path,
    armature: bpy.types.Object,
    face_adjustments: dict[str, Any],
) -> bpy.types.Object:
    existing_objects = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    imported_meshes = [
        obj
        for obj in bpy.data.objects
        if obj not in existing_objects and obj.type == "MESH"
    ]
    if len(imported_meshes) != 1:
        summary = [(obj.name, obj.type) for obj in bpy.data.objects if obj not in existing_objects]
        raise RuntimeError(
            f"Expected one mesh in the derived identity proxy; imported {summary}."
        )
    proxy = imported_meshes[0]
    proxy.name = "Juana_Hunyuan_Identity_Proxy"
    proxy.data.name = "Juana_Hunyuan_Identity_Proxy_Mesh"

    source_eye_midpoint = Vector((0.040093, -0.156858, 0.736104))
    target_eye_midpoint = Vector((0.0, -0.1135, 1.530))
    bpy.context.view_layer.update()
    source_matrix = proxy.matrix_world.copy()
    world_scale = Vector((0.86, 0.82, 0.82))
    scaled_eye_midpoint = Vector(
        (
            source_eye_midpoint.x * world_scale.x,
            source_eye_midpoint.y * world_scale.y,
            source_eye_midpoint.z * world_scale.z,
        )
    )
    alignment = (
        Matrix.Translation(target_eye_midpoint - scaled_eye_midpoint)
        @ Matrix.Diagonal((*world_scale, 1.0))
        @ source_matrix
    )
    proxy["source_sha256"] = (
        "ead2c523ff3c44a57cf79527c3f439443f6f077067735a90c7efbb7065525364"
    )
    proxy["derived_proxy_sha256"] = (
        "2d8d4d7e44e6f5a2d3b4168d08f05e12ec38c64249d3e1bc129465c28de5dd11"
    )
    proxy["source_origin"] = "Tencent HY 3D Global"
    proxy["ai_generated"] = True
    proxy["status"] = "provisional_visual_proxy"
    proxy["production_topology"] = False
    proxy["integration"] = "visible identity checkpoint over editable MPFB rig"
    face_center_x = 0.040
    for material in proxy.data.materials:
        if material is None or not material.use_nodes or material.node_tree is None:
            continue
        principled = material.node_tree.nodes.get("Principled BSDF")
        if principled is None:
            continue
        image_link = principled.inputs["Base Color"].links
        if not image_link:
            continue
        image_output = image_link[0].from_socket
        material.node_tree.links.remove(image_link[0])
        multiply = material.node_tree.nodes.new("ShaderNodeMixRGB")
        multiply.blend_type = "MULTIPLY"
        multiply.inputs["Fac"].default_value = 1.0
        if material.name.startswith("Juana_Hunyuan_Skin_Warm_Golden_Brown"):
            skin_tint = face_adjustments["skin_tint_linear"]
            multiply.inputs[2].default_value = (*skin_tint, 1.0)
            principled.inputs["Roughness"].default_value = 0.68
            if "Specular IOR Level" in principled.inputs:
                principled.inputs["Specular IOR Level"].default_value = 0.18
        elif material.name.startswith("Juana_Hunyuan_Hair_Low_Specular"):
            multiply.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
            principled.inputs["Roughness"].default_value = 0.82
            if "Specular IOR Level" in principled.inputs:
                principled.inputs["Specular IOR Level"].default_value = 0.08
        else:
            multiply.inputs[2].default_value = (1.0, 1.0, 1.0, 1.0)
        material.node_tree.links.new(image_output, multiply.inputs[1])
        material.node_tree.links.new(multiply.outputs["Color"], principled.inputs["Base Color"])
    hair_material_index = next(
        (
            index
            for index, material in enumerate(proxy.data.materials)
            if material is not None
            and material.name.startswith("Juana_Hunyuan_Hair_Low_Specular")
        ),
        None,
    )
    skin_material_index = next(
        (
            index
            for index, material in enumerate(proxy.data.materials)
            if material is not None
            and material.name.startswith("Juana_Hunyuan_Skin_Warm_Golden_Brown")
        ),
        None,
    )
    if hair_material_index is not None:
        for polygon in proxy.data.polygons:
            if polygon.material_index != 0:
                continue
            center = source_matrix @ (
                sum(
                    (proxy.data.vertices[index].co for index in polygon.vertices),
                    Vector(),
                )
                / len(polygon.vertices)
            )
            if (
                center.y < -0.10
                and 0.755 < center.z < 0.815
                and abs(center.x - face_center_x) < 0.145
            ):
                polygon.material_index = hair_material_index
    if hair_material_index is not None and skin_material_index is not None:
        for polygon in proxy.data.polygons:
            if polygon.material_index != hair_material_index:
                continue
            center = source_matrix @ (
                sum(
                    (proxy.data.vertices[index].co for index in polygon.vertices),
                    Vector(),
                )
                / len(polygon.vertices)
            )
            if (
                0.49 < center.z < 0.60
                and abs(center.x - face_center_x) < 0.075
                and center.y < 0.06
            ):
                polygon.material_index = skin_material_index
    _refine_identity_proxy_face(proxy, source_matrix, face_adjustments)
    proxy["visible_surface"] = "full_bust_identity_surface"
    proxy.matrix_world = alignment
    bpy.context.view_layer.update()
    _crop_identity_proxy_to_bust(proxy, PROXY_BUST_CUTOFF_WORLD_Z)
    _smooth(proxy)
    _parent_to_bone(proxy, armature, "spine01")
    return proxy


def _hide_provisional_scaffold(objects: Sequence[bpy.types.Object]) -> None:
    for obj in objects:
        obj.hide_render = True
        obj.hide_set(True)
        obj["review_visibility"] = "hidden_under_identity_proxy"


def _make_scaffold_transparent_for_export(
    objects: Sequence[bpy.types.Object],
) -> None:
    materials = {
        material
        for obj in objects
        if hasattr(obj.data, "materials")
        for material in obj.data.materials
        if material is not None
    }
    for material in materials:
        if not material.use_nodes or material.node_tree is None:
            continue
        principled = material.node_tree.nodes.get("Principled BSDF")
        if principled is None:
            continue
        principled.inputs["Alpha"].default_value = 0.0
        if "Base Color" in principled.inputs:
            color = principled.inputs["Base Color"].default_value
            color[3] = 0.0
        if hasattr(material, "surface_render_method"):
            material.surface_render_method = "DITHERED"
        material["export_role"] = "transparent_editable_scaffold"


def _create_camera(
    view: dict[str, Any],
) -> bpy.types.Object:
    camera_data = bpy.data.cameras.new(f"Camera_{view['id']}")
    camera_data.lens = float(view["lens_mm"])
    camera_data.sensor_width = 36.0
    camera = bpy.data.objects.new(f"Camera_{view['id']}", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = view["camera_location"]
    direction = Vector(view["target"]) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    camera_data.dof.use_dof = False
    camera_data.clip_start = 0.05
    camera["review_crop"] = "head_neck_and_shoulder_hint"
    camera["target_height"] = float(view["target"][2])
    return camera


def _create_area_light(
    name: str,
    location: Sequence[float],
    energy: float,
    color: Sequence[float],
    size: float,
    target: Sequence[float],
) -> bpy.types.Object:
    data = bpy.data.lights.new(name, "AREA")
    data.energy = energy
    data.color = color
    data.shape = "DISK"
    data.size = size
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = location
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()
    return obj


def _configure_scene(scene: bpy.types.Scene, render_manifest: dict[str, Any]) -> None:
    settings = render_manifest["render"]
    scene.render.engine = settings["engine"]
    scene.render.resolution_x = settings["resolution"][0]
    scene.render.resolution_y = settings["resolution"][1]
    scene.render.resolution_percentage = settings["resolution_percentage"]
    scene.render.image_settings.file_format = settings["image_format"]
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = settings["film_transparent"]
    scene.render.use_file_extension = True
    scene.render.film_transparent = False
    scene.render.image_settings.color_depth = "8"
    scene.view_settings.view_transform = settings["view_transform"]
    try:
        scene.view_settings.look = settings["look"]
    except TypeError:
        scene.view_settings.look = "Medium High Contrast"
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    background.inputs["Color"].default_value = settings["world_color"]
    background.inputs["Strength"].default_value = 0.24
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.58
    scene.render.filepath = ""
    scene.render.use_overwrite = True
    scene.camera = None


def _move_to_collection(
    objects: Sequence[bpy.types.Object],
    collection: bpy.types.Collection,
) -> None:
    for obj in objects:
        for source_collection in tuple(obj.users_collection):
            source_collection.objects.unlink(obj)
        collection.objects.link(obj)


def _create_scene_collection(
    scene: bpy.types.Scene,
    name: str,
) -> bpy.types.Collection:
    collection = bpy.data.collections.new(name)
    scene.collection.children.link(collection)
    return collection


def _configure_saved_review_presentation(
    scene: bpy.types.Scene,
    identity_proxy: bpy.types.Object,
    iris_overlays: Sequence[bpy.types.Object],
    technical_objects: Sequence[bpy.types.Object],
    cameras: Sequence[bpy.types.Object],
    lights: Sequence[bpy.types.Object],
    export_collection: bpy.types.Collection,
) -> None:
    review_collection = _create_scene_collection(scene, "JUANA_REVIEW")
    technical_collection = _create_scene_collection(scene, "JUANA_TECHNICAL")
    camera_collection = _create_scene_collection(scene, "JUANA_CAMERAS")
    lighting_collection = _create_scene_collection(scene, "JUANA_LIGHTING")

    review_objects = [identity_proxy, *iris_overlays]
    _move_to_collection(review_objects, review_collection)
    _move_to_collection(technical_objects, technical_collection)
    _move_to_collection(cameras, camera_collection)
    _move_to_collection(lights, lighting_collection)

    for obj in review_objects:
        obj.hide_set(False)
    for obj in [*technical_objects, *cameras, *lights, *export_collection.objects]:
        obj.hide_set(True)
    for obj in export_collection.objects:
        obj.hide_render = True

    bpy.ops.object.select_all(action="DESELECT")
    scene.camera = cameras[0]
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            space = area.spaces.active
            space.region_3d.view_perspective = "CAMERA"
            space.region_3d.view_camera_zoom = 0
            space.shading.type = "MATERIAL"
            space.overlay.show_extras = False
            space.overlay.show_relationship_lines = False
            space.overlay.show_floor = False
            space.overlay.show_axis_x = False
            space.overlay.show_axis_y = False


def _convert_for_export(
    source: bpy.types.Object,
    export_collection: bpy.types.Collection,
) -> bpy.types.Object:
    duplicate = source.copy()
    duplicate.data = source.data.copy()
    duplicate.animation_data_clear()
    export_collection.objects.link(duplicate)
    duplicate.name = f"{source.name}_Export"
    bpy.context.view_layer.objects.active = duplicate
    duplicate.select_set(True)
    bpy.ops.object.convert(target="MESH")
    duplicate.select_set(False)
    return duplicate


def _world_bbox_dimensions(obj: bpy.types.Object) -> Vector:
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    return Vector(
        (
            max(corner.x for corner in corners) - min(corner.x for corner in corners),
            max(corner.y for corner in corners) - min(corner.y for corner in corners),
            max(corner.z for corner in corners) - min(corner.z for corner in corners),
        )
    )


def _write_scene_report(
    output_path: Path,
    repository_root: Path,
    body: bpy.types.Object,
    armature: bpy.types.Object,
    eyes: Sequence[bpy.types.Object],
    iris_overlays: Sequence[bpy.types.Object],
    facial_details: Sequence[bpy.types.Object],
    hair: Sequence[bpy.types.Object],
    outfit: Sequence[bpy.types.Object],
    identity_proxy: bpy.types.Object,
    body_calibration: bpy.types.Object,
    cameras: Sequence[bpy.types.Object],
    renders: Sequence[Path],
) -> None:
    shape_keys = [key.name for key in body.data.shape_keys.key_blocks]
    eye_aspect_ratios = {
        eye.name: _world_bbox_dimensions(eye).x / _world_bbox_dimensions(eye).z for eye in eyes
    }
    long_hair = next(obj for obj in hair if obj.name == "Juana_Hair_Long_Right")
    flowing_clump_count = int(long_hair.get("flowing_clump_count", 0))
    flowing_clumps = [
        f"{long_hair.name}#mesh-island-{index:02d}" for index in range(1, flowing_clump_count + 1)
    ]
    report = {
        "schema_version": "1.0",
        "status": "provisional_visual_checkpoint",
        "blender_version": bpy.app.version_string,
        "body": {
            "object": body.name,
            "vertices": len(body.data.vertices),
            "polygons": len(body.data.polygons),
            "shape_keys": shape_keys,
        },
        "rig": {
            "object": armature.name,
            "bone_count": len(armature.data.bones),
            "required_bones": [
                "root",
                "spine05",
                "spine03",
                "spine01",
                "neck03",
                "head",
                "eye.L",
                "eye.R",
                "jaw",
            ],
            "jaw_action": "Juana_Jaw_Articulation",
            "jaw_keyframes": [1, 12, 24],
        },
        "eyes": [eye.name for eye in eyes],
        "iris_overlays": [overlay.name for overlay in iris_overlays],
        "facial_details": [obj.name for obj in facial_details],
        "hair": [obj.name for obj in hair],
        "outfit": [obj.name for obj in outfit],
        "identity_proxy": {
            "object": identity_proxy.name,
            "vertices": len(identity_proxy.data.vertices),
            "polygons": len(identity_proxy.data.polygons),
            "source_sha256": identity_proxy.get("source_sha256"),
            "derived_proxy_sha256": identity_proxy.get("derived_proxy_sha256"),
            "ai_generated": bool(identity_proxy.get("ai_generated")),
            "production_topology": bool(identity_proxy.get("production_topology")),
            "parent_bone": identity_proxy.parent_bone,
            "integration": identity_proxy.get("integration"),
            "likeness_revision": identity_proxy.get("likeness_revision"),
            "visible_surface": identity_proxy.get("visible_surface"),
            "presentation_scope": identity_proxy.get("presentation_scope"),
            "presentation_cutoff_world_z": identity_proxy.get(
                "presentation_cutoff_world_z"
            ),
            "removed_lower_body_vertices": identity_proxy.get(
                "removed_lower_body_vertices"
            ),
        },
        "body_calibration": {
            "object": body_calibration.name,
            "vertices": len(body_calibration.data.vertices),
            "polygons": len(body_calibration.data.polygons),
            "source_sha256": body_calibration.get("source_sha256"),
            "production_base": bool(body_calibration.get("production_base")),
            "visible_use": body_calibration.get("visible_use"),
        },
        "cameras": [camera.name for camera in cameras],
        "renders": [path.relative_to(repository_root).as_posix() for path in renders],
        "likeness_pass": {
            "revision": identity_proxy.get("likeness_revision"),
            "review_decision": "changes_requested",
            "eye_width_height_ratios": eye_aspect_ratios,
            "eye_appearance": "narrow_almond_amber",
            "eyebrow_appearance": facial_details[0].get("appearance"),
            "skin_tone": body.active_material.get("approved_tone"),
            "flowing_hair_clump_count": flowing_clump_count,
            "flowing_hair_clumps": flowing_clumps,
            "rig_controls_hidden": bool(armature.hide_render and not armature.show_in_front),
            "visible_identity_source": "Juana_Hunyuan_Identity_Proxy",
            "visible_body_calibration_source": "Juana_Meta_MHR_Body_Calibration_Surface",
        },
        "review_presentation": {
            "crop": "head_neck_and_shoulder_hint",
            "landmark_overlay": "comparisons/front-landmark-overlay.png",
        },
        "provisional_boundary": {
            "visual_canon_approved": False,
            "final_vrm": False,
            "distribution_path": None,
            "visible_identity_proxy": True,
            "production_topology": False,
        },
    }
    output_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = _arguments()
    args.output_root.mkdir(parents=True, exist_ok=True)
    render_root = args.output_root / "renders"
    render_root.mkdir(parents=True, exist_ok=True)
    render_manifest = _load_json(args.render_manifest)
    toolchain_lock = _load_json(args.repo_root / "tools" / "juana_bust" / "toolchain-lock.json")
    source_evidence = _load_json(args.repo_root / "tools" / "juana_bust" / "source-evidence.json")
    macro_settings = toolchain_lock["human_base"]["macro_settings"]

    human_module = _import_mpfb("services.humanservice")
    target_module = _import_mpfb("services.targetservice")
    export_module = _import_mpfb("services.exportservice")
    HumanService = human_module.HumanService
    TargetService = target_module.TargetService
    ExportService = export_module.ExportService

    _clear_scene()
    scene = bpy.context.scene
    _configure_scene(scene, render_manifest)

    body = HumanService.create_human(
        mask_helpers=True,
        detailed_helpers=True,
        extra_vertex_groups=True,
        feet_on_ground=True,
        scale=0.1,
        macro_detail_dict=macro_settings,
    )
    body.name = "Juana_Body"
    body.data.name = "Juana_Body_Mesh"
    body["base_asset_id"] = "makehuman-hm08-juana-bust-r1"
    body["status"] = "provisional_visual_checkpoint"

    mpfb_root = args.toolchain_root / "blender-profile" / "extensions" / "user_default" / "mpfb"
    target_root = mpfb_root / "data" / "targets"
    identity_controls = tuple(
        (
            control["name"],
            control["target"],
            float(control["weight"]),
        )
        for control in source_evidence["likeness_pass_3"]["target_controls"]
    )
    _load_targets(TargetService, body, target_root, identity_controls)
    _add_likeness_pass_shape(
        body,
        source_evidence["likeness_pass_3"]["landmark_calibration"],
    )

    expression_root = target_root / "expression" / "units" / "african"
    expression_controls = (
        (
            "blinkLeft",
            str((expression_root / "eye-left-closure.target.gz").relative_to(target_root)),
            0.0,
        ),
        (
            "blinkRight",
            str((expression_root / "eye-right-closure.target.gz").relative_to(target_root)),
            0.0,
        ),
        ("aa", str((expression_root / "mouth-open.target.gz").relative_to(target_root)), 0.0),
        ("ih", str((expression_root / "mouth-retraction.target.gz").relative_to(target_root)), 0.0),
        ("ou", str((expression_root / "mouth-pursing.target.gz").relative_to(target_root)), 0.0),
        (
            "ee",
            str((expression_root / "mouth-upward-retraction.target.gz").relative_to(target_root)),
            0.0,
        ),
    )
    _load_targets(TargetService, body, target_root, expression_controls)
    _combine_shape_keys(body, "blink", (("blinkLeft", 1.0), ("blinkRight", 1.0)))
    _combine_shape_keys(body, "oh", (("aa", 0.58), ("ou", 0.68)))

    armature = HumanService.add_builtin_rig(body, "default")
    if armature is None:
        raise RuntimeError("MPFB did not create the required default rig.")
    armature.name = "Juana_Armature"
    armature.data.name = "Juana_Armature_Data"
    armature.show_in_front = False
    armature.hide_render = True
    armature["adapter_id"] = "juana-mpfb-default-bust"
    armature["review_controls_hidden"] = True
    _create_jaw_action(armature)
    long_hair_path = (
        args.toolchain_root / "assets" / "extracted" / "hair" / "long01" / "long01.mhclo"
    )
    short_hair_path = (
        args.toolchain_root / "assets" / "extracted" / "hair" / "short01" / "short01.mhclo"
    )
    eyelash_path = (
        args.toolchain_root
        / "assets"
        / "extracted"
        / "eyelashes"
        / "eyelashes03"
        / "eyelashes03.mhclo"
    )
    jacket_path = (
        args.toolchain_root
        / "assets"
        / "extracted"
        / "clothes"
        / "female_elegantsuit01"
        / "female_elegantsuit01.mhclo"
    )
    underlayer_path = (
        args.toolchain_root
        / "assets"
        / "extracted"
        / "clothes"
        / "female_casualsuit02"
        / "female_casualsuit02.mhclo"
    )
    long_hair = HumanService.add_mhclo_asset(
        str(long_hair_path),
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
        str(short_hair_path),
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
        str(eyelash_path),
        body,
        asset_type="Eyelashes",
        subdiv_levels=0,
        material_type="NONE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    system_jacket = HumanService.add_mhclo_asset(
        str(jacket_path),
        body,
        asset_type="Outfit",
        subdiv_levels=1,
        material_type="NONE",
        set_up_rigging=True,
        interpolate_weights=True,
        import_subrig=True,
        import_weights=True,
    )
    system_underlayer = HumanService.add_mhclo_asset(
        str(underlayer_path),
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
        bake_masks=True,
        bake_subdiv=False,
        remove_helpers=True,
        also_proxy=False,
    )

    skin_texture = (
        args.toolchain_root
        / "assets"
        / "extracted"
        / "skins"
        / "young_african_female"
        / "young_darkskinned_female_diffuse.png"
    )
    hair_texture = (
        args.toolchain_root / "assets" / "extracted" / "hair" / "long01" / "long01_diffuse.png"
    )
    short_hair_texture = (
        args.toolchain_root / "assets" / "extracted" / "hair" / "short01" / "short01_diffuse.png"
    )
    eyelash_texture = (
        args.toolchain_root
        / "assets"
        / "extracted"
        / "eyelashes"
        / "eyelashes03"
        / "eyelashes03.png"
    )
    materials = {
        "skin": _skin_material(skin_texture),
        "sclera": _material("Juana_Eye_Sclera", (0.46, 0.40, 0.34, 1.0), roughness=0.52),
        "iris_rim": _material(
            "Juana_Eye_Amber_Rim",
            (0.0015, 0.0004, 0.0001, 1.0),
            roughness=0.46,
            specular_ior_level=0.12,
        ),
        "iris": _material(
            "Juana_Eye_Amber",
            (0.035, 0.009, 0.001, 1.0),
            roughness=0.42,
            specular_ior_level=0.12,
        ),
        "pupil": _material("Juana_Eye_Pupil", (0.008, 0.006, 0.005, 1.0), roughness=0.12),
        "eye_highlight": _material("Juana_Eye_Highlight", (1.0, 1.0, 1.0, 1.0), roughness=0.05),
        "hair_texture": _hair_texture_material(
            "Juana_Hair_Long_Texture", hair_texture, (0.040, 0.012, 0.006, 1.0)
        ),
        "short_hair_texture": _hair_texture_material(
            "Juana_Hair_Short_Texture",
            short_hair_texture,
            (0.028, 0.008, 0.004, 1.0),
        ),
        "undercut": _undercut_material(),
        "eyebrow": _material(
            "Juana_Eyebrow_Dark",
            (0.006, 0.0018, 0.0007, 1.0),
            roughness=0.84,
            specular_ior_level=0.06,
        ),
        "eyelashes": _alpha_detail_material("Juana_Eyelashes", eyelash_texture, value=0.26),
        "outfit_inner": _material(
            "Juana_Outfit_Inner_Pearl", (0.78, 0.80, 0.82, 1.0), roughness=0.28, coat=0.2
        ),
        "outfit_jacket": _material(
            "Juana_Outfit_Jacket_Pearl", (0.93, 0.95, 0.98, 1.0), roughness=0.16, coat=0.58
        ),
        "gold": _material("Juana_Gold", (0.83, 0.48, 0.07, 1.0), metallic=0.92, roughness=0.19),
        "zipper": _material("Juana_Zipper", (0.26, 0.28, 0.31, 1.0), metallic=0.82, roughness=0.26),
        "choker": _material("Juana_Choker_Black", (0.008, 0.009, 0.012, 1.0), roughness=0.2),
        "choker_text": _material(
            "Juana_Choker_Text_White", (0.82, 0.84, 0.88, 1.0), roughness=0.35
        ),
    }
    _assign_material(body, materials["skin"])
    _smooth(body)
    subdivision = body.modifiers.new("Juana render subdivision", "SUBSURF")
    subdivision.levels = 1
    subdivision.render_levels = 1

    left_center = _bone_world_position(armature, "eye.L")
    right_center = _bone_world_position(armature, "eye.R")
    eyes = [
        _create_eye("L", left_center, armature, materials),
        _create_eye("R", right_center, armature, materials),
    ]
    iris_overlays = [
        _create_iris_overlay(
            "R",
            Vector((-0.0457, -0.1195, 1.5290)),
            armature,
            materials,
        ),
        _create_iris_overlay(
            "L",
            Vector((0.0457, -0.1195, 1.5310)),
            armature,
            materials,
        ),
    ]
    eyebrow = _create_eyebrows(
        left_center,
        right_center,
        body,
        armature,
        materials["eyebrow"],
    )
    eyelashes.name = "Juana_Eyelashes"
    _assign_material(eyelashes, materials["eyelashes"])
    facial_details = [eyebrow, eyelashes]
    eyelashes["source_asset"] = "MakeHuman system asset eyelashes03, CC0-1.0"
    eyelashes["status"] = "provisional_visual_assumption"
    eye_center = (left_center + right_center) * 0.5
    hair = _create_hair(body, eye_center, materials, long_hair, short_hair)
    body_calibration = _import_meta_body_calibration(
        args.repo_root
        / source_evidence["generated_body_calibration_reference"][
            "derived_calibration_asset"
        ]["path"],
        Vector((0.0, -0.1135, 1.455)),
    )
    _parent_to_bone(body_calibration, armature, "spine01")
    outfit = _create_outfit(
        body,
        armature,
        materials,
        system_underlayer,
        system_jacket,
    )
    identity_proxy = _import_identity_proxy(
        args.repo_root
        / source_evidence["generated_geometry_reference"]["derived_visual_proxy"]["path"],
        armature,
        source_evidence["likeness_pass_4"]["face_adjustments"],
    )
    _hide_provisional_scaffold(
        [
            body,
            *eyes,
            *facial_details,
            *hair,
            *outfit,
            body_calibration,
        ],
    )

    cameras = [_create_camera(view) for view in render_manifest["views"]]
    lights = [
        _create_area_light(
            "Juana_Key_Light",
            (1.3, -1.7, 2.25),
            175.0,
            (1.0, 0.96, 0.92),
            1.25,
            (0.0, 0.0, 1.5),
        ),
        _create_area_light(
            "Juana_Fill_Light",
            (-1.35, -1.25, 1.75),
            80.0,
            (0.92, 0.96, 1.0),
            1.4,
            (0.0, 0.0, 1.5),
        ),
        _create_area_light(
            "Juana_Rim_Light",
            (-0.2, 1.3, 2.15),
            105.0,
            (1.0, 0.96, 0.90),
            0.9,
            (0.0, 0.0, 1.5),
        ),
        _create_area_light(
            "Juana_Face_Softbox",
            (0.0, -1.0, 1.65),
            32.0,
            (1.0, 1.0, 1.0),
            0.65,
            (0.0, 0.0, 1.53),
        ),
    ]

    render_paths = []
    for view, camera in zip(render_manifest["views"], cameras, strict=True):
        scene.camera = camera
        render_path = render_root / f"{view['id']}.png"
        scene.render.filepath = str(render_path)
        scene.frame_set(render_manifest["render"]["frame"])
        bpy.ops.render.render(write_still=True)
        render_paths.append(render_path)

    export_collection = bpy.data.collections.new("JUANA_GLTF_EXPORT")
    scene.collection.children.link(export_collection)
    export_objects = [
        armature,
        body,
        identity_proxy,
        *eyes,
        *iris_overlays,
        *facial_details,
    ]
    for source in [*hair, *outfit]:
        if source.type in {"CURVE", "FONT"}:
            export_objects.append(_convert_for_export(source, export_collection))
        elif source.type == "MESH":
            export_objects.append(source)

    technical_objects = [
        armature,
        body,
        *eyes,
        *facial_details,
        *hair,
        *outfit,
        body_calibration,
    ]
    _configure_saved_review_presentation(
        scene,
        identity_proxy,
        iris_overlays,
        technical_objects,
        cameras,
        lights,
        export_collection,
    )
    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_root / "juana-bust-provisional.blend"))

    _make_scaffold_transparent_for_export(
        [
            body,
            *eyes,
            *facial_details,
            *hair,
            *outfit,
            body_calibration,
        ],
    )
    bpy.ops.object.select_all(action="DESELECT")
    for obj in export_objects:
        obj.hide_set(False)
        obj.select_set(True)
    bpy.context.view_layer.objects.active = armature
    bpy.ops.export_scene.gltf(
        filepath=str(args.output_root / "juana-bust-provisional.glb"),
        export_format="GLB",
        use_selection=True,
        export_animations=True,
        export_morph=True,
        export_morph_normal=True,
        export_skins=True,
        export_all_influences=True,
        export_yup=True,
    )

    _write_scene_report(
        args.output_root / "scene-report.json",
        args.repo_root,
        body,
        armature,
        eyes,
        iris_overlays,
        facial_details,
        hair,
        outfit,
        identity_proxy,
        body_calibration,
        cameras,
        render_paths,
    )
    print("GH22_PREVIEW_AUTHORING_COMPLETE")


if __name__ == "__main__":
    main()
