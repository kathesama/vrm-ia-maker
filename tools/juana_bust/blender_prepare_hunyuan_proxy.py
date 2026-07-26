"""Prepare the traceable Hunyuan bust as a reduced visual-identity proxy."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from array import array
from pathlib import Path
from typing import Any

import bpy
from mathutils import Vector

SOURCE_SHA256 = "ead2c523ff3c44a57cf79527c3f439443f6f077067735a90c7efbb7065525364"
SOURCE_BYTE_LENGTH = 83_723_136
DEFAULT_TARGET_TRIANGLES = 350_000


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument(
        "--target-triangles",
        type=int,
        default=DEFAULT_TARGET_TRIANGLES,
    )
    arguments = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(arguments)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_source(path: Path) -> None:
    if not path.is_file():
        raise RuntimeError(f"Required Hunyuan source is missing: {path}.")
    actual_length = path.stat().st_size
    actual_sha256 = _sha256_file(path)
    if actual_length != SOURCE_BYTE_LENGTH or actual_sha256 != SOURCE_SHA256:
        raise RuntimeError(
            "Hunyuan source integrity mismatch: "
            f"expected sha256={SOURCE_SHA256}, bytes={SOURCE_BYTE_LENGTH}; "
            f"actual sha256={actual_sha256}, bytes={actual_length}."
        )


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    for mesh in tuple(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for material in tuple(bpy.data.materials):
        if material.users == 0:
            bpy.data.materials.remove(material)


def _source_mesh() -> bpy.types.Object:
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if len(meshes) != 1:
        summary = [(obj.name, obj.type) for obj in bpy.context.scene.objects]
        raise RuntimeError(f"Expected one imported Hunyuan mesh; found {summary}.")
    return meshes[0]


def _base_color_image(material: bpy.types.Material) -> bpy.types.Image:
    if not material.use_nodes or material.node_tree is None:
        raise RuntimeError("Hunyuan material does not use nodes.")
    principled = next(
        (
            node
            for node in material.node_tree.nodes
            if node.bl_idname == "ShaderNodeBsdfPrincipled"
        ),
        None,
    )
    if principled is None:
        raise RuntimeError("Hunyuan material has no Principled BSDF node.")
    base_color = principled.inputs.get("Base Color")
    if base_color is None or not base_color.is_linked:
        raise RuntimeError("Hunyuan material has no linked base-color texture.")
    source_node = base_color.links[0].from_node
    if source_node.bl_idname != "ShaderNodeTexImage" or source_node.image is None:
        raise RuntimeError("Hunyuan base color is not provided by an image texture.")
    return source_node.image


def _neutral_material(
    source_material: bpy.types.Material,
    *,
    maximum_texture_size: int = 2048,
) -> tuple[bpy.types.Material, bpy.types.Image]:
    base_image = _base_color_image(source_material)
    if max(base_image.size) > maximum_texture_size:
        width, height = base_image.size
        scale = maximum_texture_size / max(width, height)
        base_image.scale(
            max(1, int(round(width * scale))),
            max(1, int(round(height * scale))),
        )
    base_image.name = "Juana_Hunyuan_Derived_BaseColor"
    base_image["source_sha256"] = SOURCE_SHA256
    base_image["ai_generated"] = True

    material = bpy.data.materials.new("Juana_Hunyuan_Identity_Material")
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.name = "Derived_Hunyuan_BaseColor"
    image_node.image = base_image
    links.new(image_node.outputs["Color"], principled.inputs["Base Color"])
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = 0.58
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = 0.22
    if "Coat Weight" in principled.inputs:
        principled.inputs["Coat Weight"].default_value = 0.0
    material["source_sha256"] = SOURCE_SHA256
    material["processing"] = "base_color_only_neutral_pbr"
    material["ai_generated"] = True
    return material, base_image


def _tinted_material(
    name: str,
    image: bpy.types.Image,
    *,
    tint: tuple[float, float, float, float],
    roughness: float,
    specular_ior_level: float,
) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links
    principled = nodes.get("Principled BSDF")
    image_node = nodes.new("ShaderNodeTexImage")
    image_node.image = image
    multiply = nodes.new("ShaderNodeMixRGB")
    multiply.blend_type = "MULTIPLY"
    multiply.inputs["Fac"].default_value = 1.0
    multiply.inputs[2].default_value = tint
    links.new(image_node.outputs["Color"], multiply.inputs[1])
    links.new(multiply.outputs["Color"], principled.inputs["Base Color"])
    principled.inputs["Metallic"].default_value = 0.0
    principled.inputs["Roughness"].default_value = roughness
    if "Specular IOR Level" in principled.inputs:
        principled.inputs["Specular IOR Level"].default_value = specular_ior_level
    if "Coat Weight" in principled.inputs:
        principled.inputs["Coat Weight"].default_value = 0.0
    material["source_sha256"] = SOURCE_SHA256
    material["ai_generated"] = True
    return material


def _assign_semantic_materials(
    obj: bpy.types.Object,
    image: bpy.types.Image,
) -> dict[str, int]:
    if obj.data.uv_layers.active is None:
        raise RuntimeError("Derived identity proxy has no active UV layer.")
    skin = _tinted_material(
        "Juana_Hunyuan_Skin_Warm_Golden_Brown",
        image,
        tint=(0.58, 0.42, 0.31, 1.0),
        roughness=0.68,
        specular_ior_level=0.18,
    )
    hair = _tinted_material(
        "Juana_Hunyuan_Hair_Low_Specular",
        image,
        tint=(0.62, 0.50, 0.43, 1.0),
        roughness=0.82,
        specular_ior_level=0.08,
    )
    obj.data.materials.append(skin)
    obj.data.materials.append(hair)

    width, height = image.size
    pixels = array("f", [0.0]) * (width * height * 4)
    image.pixels.foreach_get(pixels)
    uv_data = obj.data.uv_layers.active.data
    counts = {
        "source_neutral": 0,
        "skin_warm_golden_brown": 0,
        "hair_low_specular": 0,
    }
    for polygon in obj.data.polygons:
        uv = sum(
            (uv_data[index].uv for index in polygon.loop_indices),
            Vector((0.0, 0.0)),
        ) / len(polygon.loop_indices)
        pixel_x = min(width - 1, max(0, int((float(uv.x) % 1.0) * width)))
        pixel_y = min(height - 1, max(0, int((float(uv.y) % 1.0) * height)))
        offset = (pixel_y * width + pixel_x) * 4
        red, green, blue = pixels[offset : offset + 3]
        local_center = sum(
            (obj.data.vertices[index].co for index in polygon.vertices),
            Vector(),
        ) / len(polygon.vertices)
        center = obj.matrix_world @ local_center
        brightness = (red + green + blue) / 3.0

        in_eye_opening = (
            center.y < -0.12
            and 0.724 < center.z < 0.748
            and (
                ((center.x + 0.013) / 0.020) ** 2
                + ((center.z - 0.736) / 0.009) ** 2
                < 1.0
                or ((center.x - 0.093) / 0.020) ** 2
                + ((center.z - 0.737) / 0.009) ** 2
                < 1.0
            )
        )
        in_face = (
            0.52 < center.z < 0.88
            and abs(center.x - 0.040) < 0.15
            and center.y < -0.065
        )
        in_neck = (
            0.50 < center.z <= 0.58
            and abs(center.x - 0.040) < 0.085
            and center.y < 0.06
        )
        in_hair_silhouette = center.z > 0.44 and (
            center.x < -0.075 or center.y > 0.02 or center.z > 0.845
        )
        is_skin = (
            (in_face or in_neck)
            and not in_eye_opening
            and brightness > 0.16
            and red >= green * 0.94
            and red >= blue * 0.92
        )
        is_hair = (
            center.z > 0.44
            and not is_skin
            and (brightness < 0.18 or in_hair_silhouette)
        )
        if is_hair:
            polygon.material_index = 2
            counts["hair_low_specular"] += 1
        elif is_skin:
            polygon.material_index = 1
            counts["skin_warm_golden_brown"] += 1
        else:
            polygon.material_index = 0
            counts["source_neutral"] += 1
    obj.data.update()
    return counts


def _apply_triangle_budget(
    obj: bpy.types.Object,
    *,
    target_triangles: int,
) -> tuple[int, int]:
    source_triangles = len(obj.data.loop_triangles)
    if target_triangles <= 0:
        raise RuntimeError("Target triangle count must be positive.")
    if source_triangles <= target_triangles:
        return source_triangles, source_triangles

    ratio = target_triangles / source_triangles
    modifier = obj.modifiers.new("Juana Hunyuan visual-proxy reduction", "DECIMATE")
    modifier.decimate_type = "COLLAPSE"
    modifier.ratio = ratio
    modifier.use_collapse_triangulate = True
    bpy.context.view_layer.objects.active = obj
    obj.select_set(True)
    bpy.ops.object.modifier_apply(modifier=modifier.name)
    obj.select_set(False)
    obj.data.calc_loop_triangles()
    return source_triangles, len(obj.data.loop_triangles)


def _write_report(
    path: Path,
    *,
    output: Path,
    source_triangles: int,
    output_triangles: int,
    vertex_count: int,
    semantic_material_counts: dict[str, int],
) -> None:
    report: dict[str, Any] = {
        "schema_version": "1.0",
        "status": "provisional_visual_proxy",
        "source": {
            "sha256": SOURCE_SHA256,
            "byte_length": SOURCE_BYTE_LENGTH,
            "origin": "Tencent HY 3D Global",
        },
        "processing": {
            "source_triangles": source_triangles,
            "output_triangles": output_triangles,
            "output_vertices": vertex_count,
            "material_policy": (
                "embedded base color only with neutral physically based response"
            ),
            "maximum_texture_size": 2048,
            "semantic_material_counts": semantic_material_counts,
            "production_topology": False,
        },
        "output": {
            "path": str(output),
            "sha256": _sha256_file(output),
            "byte_length": output.stat().st_size,
        },
        "disclosure": {
            "ai_generated": True,
            "visual_checkpoint_only": True,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    args = _arguments()
    args.source = args.source.resolve()
    args.output = args.output.resolve()
    args.report = args.report.resolve()
    _verify_source(args.source)
    if args.target_triangles > 400_000:
        raise RuntimeError("Visual proxy triangle budget must not exceed 400000.")

    _clear_scene()
    bpy.ops.import_scene.gltf(filepath=str(args.source))
    source = _source_mesh()
    if len(source.data.materials) != 1 or source.data.materials[0] is None:
        raise RuntimeError("Expected one Hunyuan source material.")
    neutral_material, base_color_image = _neutral_material(source.data.materials[0])
    source.data.materials.clear()
    source.data.materials.append(neutral_material)
    source.name = "Juana_Hunyuan_Identity_Proxy"
    source.data.name = "Juana_Hunyuan_Identity_Proxy_Mesh"
    source["source_sha256"] = SOURCE_SHA256
    source["source_origin"] = "Tencent HY 3D Global"
    source["ai_generated"] = True
    source["status"] = "provisional_visual_proxy"
    source["production_topology"] = False

    source_triangles, output_triangles = _apply_triangle_budget(
        source,
        target_triangles=args.target_triangles,
    )
    semantic_material_counts = _assign_semantic_materials(source, base_color_image)
    for polygon in source.data.polygons:
        polygon.use_smooth = True

    args.output.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="DESELECT")
    source.select_set(True)
    bpy.context.view_layer.objects.active = source
    bpy.ops.export_scene.gltf(
        filepath=str(args.output),
        export_format="GLB",
        use_selection=True,
        export_animations=False,
        export_morph=False,
        export_skins=False,
        export_yup=True,
    )
    _write_report(
        args.report,
        output=args.output,
        source_triangles=source_triangles,
        output_triangles=output_triangles,
        vertex_count=len(source.data.vertices),
        semantic_material_counts=semantic_material_counts,
    )
    print(
        "GH22_HUNYUAN_PROXY_READY "
        f"triangles={output_triangles} bytes={args.output.stat().st_size}"
    )


if __name__ == "__main__":
    main()
