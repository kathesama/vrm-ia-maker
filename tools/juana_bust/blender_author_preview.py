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
from mathutils import Vector


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
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    principled.inputs["Base Color"].default_value = (*color[:3], color[3])
    principled.inputs["Metallic"].default_value = metallic
    principled.inputs["Roughness"].default_value = roughness
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
    hue.inputs["Saturation"].default_value = 0.92
    hue.inputs["Value"].default_value = 0.62
    links.new(image_node.outputs["Color"], hue.inputs["Color"])
    links.new(hue.outputs["Color"], principled.inputs["Base Color"])
    principled.inputs["Roughness"].default_value = 0.52
    if "Subsurface Weight" in principled.inputs:
        principled.inputs["Subsurface Weight"].default_value = 0.08
    if "Subsurface Radius" in principled.inputs:
        principled.inputs["Subsurface Radius"].default_value = (1.0, 0.45, 0.25)
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
    hue = nodes.new("ShaderNodeHueSaturation")
    hue.inputs["Hue"].default_value = 0.5
    hue.inputs["Saturation"].default_value = 0.72
    hue.inputs["Value"].default_value = value
    links.new(image_node.outputs["Color"], hue.inputs["Color"])
    links.new(hue.outputs["Color"], principled.inputs["Base Color"])
    links.new(image_node.outputs["Alpha"], principled.inputs["Alpha"])
    principled.inputs["Roughness"].default_value = 0.72
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
    parts = []
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=48,
        ring_count=24,
        radius=1.0,
        location=center,
    )
    sclera = bpy.context.object
    sclera.scale = (0.0175, 0.0145, 0.017)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _assign_material(sclera, materials["sclera"])
    parts.append(sclera)

    for radius, depth, offset, material_name in (
        (0.0108, 0.0022, 0.0137, "iris"),
        (0.0048, 0.0017, 0.0158, "pupil"),
        (0.00075, 0.00055, 0.0170, "eye_highlight"),
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
        detail.scale = (radius, depth, radius)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        _assign_material(detail, materials[material_name])
        parts.append(detail)

    eye = _join_objects(parts, f"Juana_Eye_{side}")
    _smooth(eye)
    _parent_to_bone(eye, armature, f"eye.{side}")
    eye["source"] = "MakeHuman hm08 eye placement; repository-authored geometry"
    eye["status"] = "provisional"
    return eye


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


def _cut_system_hair_for_asymmetry(
    hair: bpy.types.Object,
    eye_center: Vector,
) -> None:
    mesh = hair.data
    edit_mesh = bmesh.new()
    edit_mesh.from_mesh(mesh)
    delete_vertices = []
    for vertex in edit_mesh.verts:
        on_close_cut_side = vertex.co.x > 0.006
        below_crown = vertex.co.z < eye_center.z + 0.145
        outside_swept_crown = vertex.co.x > 0.065 and vertex.co.z < eye_center.z + 0.205
        if (on_close_cut_side and below_crown) or outside_swept_crown:
            delete_vertices.append(vertex)
    bmesh.ops.delete(edit_mesh, geom=delete_vertices, context="VERTS")
    for vertex in edit_mesh.verts:
        if vertex.co.x < -0.004:
            side_weight = min(1.0, (-vertex.co.x - 0.004) / 0.08)
            vertex.co.y -= 0.018 * side_weight
    edit_mesh.to_mesh(mesh)
    edit_mesh.free()
    mesh.update()
    hair["hair_side_convention"] = "close-cut anatomical left; long anatomical right"
    hair["source_asset"] = "MakeHuman system asset long01, CC0-1.0"
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
    _assign_material(short_hair, materials["short_hair_texture"])
    _smooth(short_hair)
    short_hair["hair_side_convention"] = (
        "close-cut anatomical left; covered by long hair on anatomical right"
    )
    short_hair["source_asset"] = "MakeHuman system asset short01, CC0-1.0"
    short_hair["status"] = "provisional_visual_assumption"
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
        center=Vector((0.0, -0.012, 1.43)),
        radius_x=0.057,
        radius_y=0.078,
        half_height=0.016,
        material=materials["choker"],
    )
    _parent_to_bone(choker, armature, "neck03")

    bpy.ops.mesh.primitive_cube_add(location=(0.0, 0.068, 1.43), scale=(0.008, 0.004, 0.009))
    closure = bpy.context.object
    closure.name = "Juana_Choker_Gold_Closure"
    _assign_material(closure, materials["gold"])
    closure_bevel = closure.modifiers.new("Gold closure edge finish", "BEVEL")
    closure_bevel.width = 0.002
    closure_bevel.segments = 3
    _parent_to_bone(closure, armature, "neck03")

    bpy.ops.object.text_add(location=(0.0, -0.094, 1.425), rotation=(math.pi / 2.0, 0.0, 0.0))
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
            [(-0.056, -0.075, 1.40), (-0.045, -0.115, 1.32), (0.0, -0.145, 1.25)],
            [(0.056, -0.075, 1.40), (0.045, -0.115, 1.32), (0.0, -0.145, 1.25)],
        ],
        0.00125,
        materials["gold"],
        radii=(0.7, 0.8, 0.6),
    )
    bpy.ops.mesh.primitive_ico_sphere_add(
        subdivisions=2,
        radius=0.012,
        location=(0.0, -0.15, 1.235),
    )
    pendant = bpy.context.object
    pendant.name = "Juana_Gold_Pendant"
    pendant.scale = (0.65, 0.35, 1.2)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    _assign_material(pendant, materials["gold"])

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
    background.inputs["Strength"].default_value = 0.12
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.35
    scene.render.filepath = ""
    scene.render.use_overwrite = True
    scene.camera = None


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


def _write_scene_report(
    output_path: Path,
    repository_root: Path,
    body: bpy.types.Object,
    armature: bpy.types.Object,
    eyes: Sequence[bpy.types.Object],
    facial_details: Sequence[bpy.types.Object],
    hair: Sequence[bpy.types.Object],
    outfit: Sequence[bpy.types.Object],
    cameras: Sequence[bpy.types.Object],
    renders: Sequence[Path],
) -> None:
    shape_keys = [key.name for key in body.data.shape_keys.key_blocks]
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
        "facial_details": [obj.name for obj in facial_details],
        "hair": [obj.name for obj in hair],
        "outfit": [obj.name for obj in outfit],
        "cameras": [camera.name for camera in cameras],
        "renders": [path.relative_to(repository_root).as_posix() for path in renders],
        "provisional_boundary": {
            "visual_canon_approved": False,
            "final_vrm": False,
            "distribution_path": None,
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
    identity_controls = (
        ("identity_head_oval", "head/head-oval.target.gz", 0.22),
        ("identity_head_narrow", "head/head-scale-horiz-decr.target.gz", 0.02),
        ("identity_cheekbone_left", "cheek/l-cheek-bones-incr.target.gz", 0.42),
        ("identity_cheekbone_right", "cheek/r-cheek-bones-incr.target.gz", 0.42),
        ("identity_cheek_left", "cheek/l-cheek-volume-incr.target.gz", 0.16),
        ("identity_cheek_right", "cheek/r-cheek-volume-incr.target.gz", 0.16),
        ("identity_chin_width", "chin/chin-width-incr.target.gz", 0.20),
        ("identity_chin_height", "chin/chin-height-decr.target.gz", 0.07),
        ("identity_chin_projection", "chin/chin-prominent-incr.target.gz", 0.08),
        ("identity_eye_left", "eyes/l-eye-scale-incr.target.gz", 0.10),
        ("identity_eye_right", "eyes/r-eye-scale-incr.target.gz", 0.10),
        ("identity_brow_arch", "eyebrows/eyebrows-angle-up.target.gz", 0.16),
        ("identity_nose_width", "nose/nose-scale-horiz-decr.target.gz", 0.08),
        ("identity_nose_depth", "nose/nose-scale-depth-incr.target.gz", 0.05),
        ("identity_mouth_width", "mouth/mouth-scale-horiz-incr.target.gz", 0.16),
        ("identity_upper_lip", "mouth/mouth-upperlip-volume-incr.target.gz", 0.31),
        ("identity_lower_lip", "mouth/mouth-lowerlip-volume-incr.target.gz", 0.38),
        ("identity_neck", "neck/neck-scale-horiz-decr.target.gz", 0.06),
        ("identity_shoulders", "torso/measure-shoulder-dist-incr.target.gz", 0.08),
    )
    _load_targets(TargetService, body, target_root, identity_controls)

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
    armature.show_in_front = True
    armature["adapter_id"] = "juana-mpfb-default-bust"
    _create_jaw_action(armature)
    long_hair_path = (
        args.toolchain_root / "assets" / "extracted" / "hair" / "long01" / "long01.mhclo"
    )
    short_hair_path = (
        args.toolchain_root / "assets" / "extracted" / "hair" / "short01" / "short01.mhclo"
    )
    eyebrow_path = (
        args.toolchain_root
        / "assets"
        / "extracted"
        / "eyebrows"
        / "eyebrow002"
        / "eyebrow002.mhclo"
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
    eyebrow = HumanService.add_mhclo_asset(
        str(eyebrow_path),
        body,
        asset_type="Eyebrows",
        subdiv_levels=0,
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
    eyebrow_texture = (
        args.toolchain_root / "assets" / "extracted" / "eyebrows" / "eyebrow002" / "eyebrow002.png"
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
        "sclera": _material("Juana_Eye_Sclera", (0.32, 0.29, 0.26, 1.0), roughness=0.38),
        "iris": _material("Juana_Eye_Amber", (0.09, 0.025, 0.006, 1.0), roughness=0.28),
        "pupil": _material("Juana_Eye_Pupil", (0.008, 0.006, 0.005, 1.0), roughness=0.12),
        "eye_highlight": _material("Juana_Eye_Highlight", (1.0, 1.0, 1.0, 1.0), roughness=0.05),
        "hair": _material("Juana_Hair", (0.008, 0.004, 0.003, 1.0), roughness=0.62),
        "hair_texture": _hair_texture_material(
            "Juana_Hair_Long_Texture", hair_texture, (0.040, 0.012, 0.006, 1.0)
        ),
        "short_hair_texture": _hair_texture_material(
            "Juana_Hair_Short_Texture",
            short_hair_texture,
            (0.028, 0.008, 0.004, 1.0),
        ),
        "hair_highlight": _material(
            "Juana_Hair_Highlight", (0.042, 0.014, 0.006, 1.0), roughness=0.52
        ),
        "eyebrow": _alpha_detail_material("Juana_Eyebrow", eyebrow_texture, value=0.34),
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
    eyebrow.name = "Juana_Eyebrows"
    eyelashes.name = "Juana_Eyelashes"
    _assign_material(eyebrow, materials["eyebrow"])
    _assign_material(eyelashes, materials["eyelashes"])
    facial_details = [eyebrow, eyelashes]
    for detail in facial_details:
        detail["source_asset"] = "MakeHuman system asset, CC0-1.0"
        detail["status"] = "provisional_visual_assumption"
    eye_center = (left_center + right_center) * 0.5
    hair = _create_hair(body, eye_center, materials, long_hair, short_hair)
    outfit = _create_outfit(
        body,
        armature,
        materials,
        system_underlayer,
        system_jacket,
    )

    cameras = [_create_camera(view) for view in render_manifest["views"]]
    _create_area_light(
        "Juana_Key_Light",
        (1.3, -1.7, 2.25),
        260.0,
        (1.0, 0.82, 0.68),
        1.25,
        (0.0, 0.0, 1.38),
    )
    _create_area_light(
        "Juana_Fill_Light",
        (-1.35, -1.25, 1.75),
        95.0,
        (0.62, 0.76, 1.0),
        1.4,
        (0.0, 0.0, 1.38),
    )
    _create_area_light(
        "Juana_Rim_Light",
        (-0.2, 1.3, 2.15),
        180.0,
        (0.78, 0.84, 1.0),
        0.9,
        (0.0, 0.0, 1.43),
    )
    _create_area_light(
        "Juana_Face_Softbox",
        (0.0, -1.0, 1.65),
        65.0,
        (1.0, 0.92, 0.85),
        0.65,
        (0.0, 0.0, 1.5),
    )

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
    export_objects = [armature, body, *eyes, *facial_details]
    for source in [*hair, *outfit]:
        if source.type in {"CURVE", "FONT"}:
            export_objects.append(_convert_for_export(source, export_collection))
        elif source.type == "MESH":
            export_objects.append(source)

    bpy.ops.wm.save_as_mainfile(filepath=str(args.output_root / "juana-bust-provisional.blend"))

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
        facial_details,
        hair,
        outfit,
        cameras,
        render_paths,
    )
    print("GH22_PREVIEW_AUTHORING_COMPLETE")


if __name__ == "__main__":
    main()
