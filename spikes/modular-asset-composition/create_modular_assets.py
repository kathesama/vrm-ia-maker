"""Generate original modular GLB fixtures for the composition spike.

The geometry is intentionally simple. The spike validates asset boundaries,
selection, skeleton compatibility, attachment semantics, and VRM export rather
than production character quality.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import bpy


REQUIRED_EXPRESSIONS = (
    "blink",
    "blinkLeft",
    "blinkRight",
    "aa",
    "ih",
    "ou",
    "ee",
    "oh",
    "happy",
    "sad",
    "angry",
    "surprised",
    "relaxed",
)


def _arguments() -> list[str]:
    try:
        separator = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit("Expected '-- <output-directory>'") from exc
    return sys.argv[separator + 1 :]


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=True)
    for collection_name in (
        "meshes",
        "armatures",
        "materials",
        "images",
        "actions",
        "curves",
        "cameras",
        "lights",
        "shape_keys",
    ):
        collection = getattr(bpy.data, collection_name, None)
        if collection is None:
            continue
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def _material(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.55
    return material


def _add_bone(edit_bones, name, head, tail, parent=None, connected=False):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    if parent is not None:
        bone.parent = parent
        bone.use_connect = connected
    return bone


def _create_armature(object_name: str, data_name: str):
    armature_data = bpy.data.armatures.new(data_name)
    armature = bpy.data.objects.new(object_name, armature_data)
    bpy.context.collection.objects.link(armature)
    bpy.context.view_layer.objects.active = armature
    armature.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT")

    bones = armature_data.edit_bones
    hips = _add_bone(bones, "hips", (0.0, 0.0, 0.90), (0.0, 0.0, 1.05))
    spine = _add_bone(bones, "spine", hips.tail, (0.0, 0.0, 1.20), hips, True)
    chest = _add_bone(bones, "chest", spine.tail, (0.0, 0.0, 1.38), spine, True)
    upper_chest = _add_bone(
        bones, "upperChest", chest.tail, (0.0, 0.0, 1.53), chest, True
    )
    neck = _add_bone(bones, "neck", upper_chest.tail, (0.0, 0.0, 1.64), upper_chest, True)
    head = _add_bone(bones, "head", neck.tail, (0.0, 0.0, 1.86), neck, True)

    left_shoulder = _add_bone(
        bones, "leftShoulder", (0.0, 0.0, 1.49), (0.13, 0.0, 1.49), upper_chest
    )
    left_upper_arm = _add_bone(
        bones, "leftUpperArm", left_shoulder.tail, (0.38, 0.0, 1.49), left_shoulder, True
    )
    left_lower_arm = _add_bone(
        bones, "leftLowerArm", left_upper_arm.tail, (0.62, 0.0, 1.49), left_upper_arm, True
    )
    _add_bone(
        bones, "leftHand", left_lower_arm.tail, (0.74, 0.0, 1.49), left_lower_arm, True
    )

    right_shoulder = _add_bone(
        bones, "rightShoulder", (0.0, 0.0, 1.49), (-0.13, 0.0, 1.49), upper_chest
    )
    right_upper_arm = _add_bone(
        bones,
        "rightUpperArm",
        right_shoulder.tail,
        (-0.38, 0.0, 1.49),
        right_shoulder,
        True,
    )
    right_lower_arm = _add_bone(
        bones,
        "rightLowerArm",
        right_upper_arm.tail,
        (-0.62, 0.0, 1.49),
        right_upper_arm,
        True,
    )
    _add_bone(
        bones, "rightHand", right_lower_arm.tail, (-0.74, 0.0, 1.49), right_lower_arm, True
    )

    left_upper_leg = _add_bone(
        bones, "leftUpperLeg", (0.08, 0.0, 0.96), (0.08, 0.0, 0.56), hips
    )
    left_lower_leg = _add_bone(
        bones, "leftLowerLeg", left_upper_leg.tail, (0.08, 0.0, 0.18), left_upper_leg, True
    )
    _add_bone(
        bones, "leftFoot", left_lower_leg.tail, (0.08, -0.16, 0.08), left_lower_leg, True
    )

    right_upper_leg = _add_bone(
        bones, "rightUpperLeg", (-0.08, 0.0, 0.96), (-0.08, 0.0, 0.56), hips
    )
    right_lower_leg = _add_bone(
        bones,
        "rightLowerLeg",
        right_upper_leg.tail,
        (-0.08, 0.0, 0.18),
        right_upper_leg,
        True,
    )
    _add_bone(
        bones, "rightFoot", right_lower_leg.tail, (-0.08, -0.16, 0.08), right_lower_leg, True
    )

    _add_bone(bones, "L_Eye", (-0.045, -0.095, 1.76), (-0.045, -0.14, 1.76), head)
    _add_bone(bones, "R_Eye", (0.045, -0.095, 1.76), (0.045, -0.14, 1.76), head)
    _add_bone(bones, "jaw", (0.0, -0.02, 1.70), (0.0, -0.08, 1.66), head)

    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _bind_mesh_to_bone(obj, armature, bone_name: str) -> None:
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = armature
    obj.parent = armature


def _create_base_scene() -> None:
    armature = _create_armature("Armature", "ModularBaseArmature")

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=12,
        location=(0.0, 0.0, 1.24),
        scale=(0.22, 0.14, 0.43),
    )
    body = bpy.context.object
    body.name = "Body"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    body.data.materials.append(_material("Skin_Body", (0.66, 0.36, 0.24, 1.0)))
    _bind_mesh_to_bone(body, armature, "chest")

    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=32,
        ring_count=16,
        location=(0.0, 0.0, 1.75),
        scale=(0.145, 0.125, 0.18),
    )
    head = bpy.context.object
    head.name = "Head"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    head.data.materials.append(_material("Skin_Head", (0.72, 0.42, 0.30, 1.0)))
    _bind_mesh_to_bone(head, armature, "head")

    basis = head.shape_key_add(name="Basis")
    for expression_index, expression_name in enumerate(REQUIRED_EXPRESSIONS, start=1):
        key = head.shape_key_add(name=expression_name)
        vertex_index = expression_index % len(key.data)
        source = basis.data[vertex_index].co
        key.data[vertex_index].co = (
            source.x + 0.0015 * expression_index,
            source.y - 0.0008 * expression_index,
            source.z + (0.001 if expression_index % 2 else -0.001) * expression_index,
        )

    for name, bone_name, location in (
        ("LeftEyeMesh", "L_Eye", (-0.045, -0.112, 1.76)),
        ("RightEyeMesh", "R_Eye", (0.045, -0.112, 1.76)),
    ):
        bpy.ops.mesh.primitive_uv_sphere_add(
            segments=16,
            ring_count=8,
            location=location,
            scale=(0.025, 0.012, 0.025),
        )
        eye = bpy.context.object
        eye.name = name
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        eye.data.materials.append(_material(f"Eye_{name}", (0.20, 0.55, 0.78, 1.0)))
        _bind_mesh_to_bone(eye, armature, bone_name)


def _create_hair_scene() -> None:
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=12,
        location=(0.0, 0.02, 1.82),
        scale=(0.165, 0.14, 0.13),
    )
    hair = bpy.context.object
    hair.name = "Hair_Rigid"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    hair.data.materials.append(_material("Hair_Primary", (0.12, 0.07, 0.10, 1.0)))


def _create_outfit_scene() -> None:
    armature = _create_armature("OutfitArmature", "OutfitArmatureData")
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=24,
        ring_count=12,
        location=(0.0, 0.005, 1.24),
        scale=(0.235, 0.151, 0.44),
    )
    outfit = bpy.context.object
    outfit.name = "OutfitMesh"
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    outfit.data.materials.append(_material("Outfit_Primary", (0.08, 0.09, 0.14, 1.0)))

    chest_group = outfit.vertex_groups.new(name="chest")
    upper_group = outfit.vertex_groups.new(name="upperChest")
    left_arm_group = outfit.vertex_groups.new(name="leftUpperArm")
    right_arm_group = outfit.vertex_groups.new(name="rightUpperArm")
    vertex_indices = list(range(len(outfit.data.vertices)))
    chest_group.add(vertex_indices, 0.45, "REPLACE")
    upper_group.add(vertex_indices, 0.35, "ADD")
    left_arm_group.add(vertex_indices, 0.10, "ADD")
    right_arm_group.add(vertex_indices, 0.10, "ADD")
    modifier = outfit.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = armature
    outfit.parent = armature


def _create_accessory_scene() -> None:
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=0.045, location=(0.0, -0.155, 1.45))
    accessory = bpy.context.object
    accessory.name = "Accessory_Brooch"
    accessory.scale = (1.25, 0.35, 1.0)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    accessory.data.materials.append(_material("Accessory_Primary", (0.30, 0.62, 0.72, 1.0)))


def _export_glb(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    bpy.ops.object.select_all(action="SELECT")
    result = bpy.ops.export_scene.gltf(
        filepath=str(path),
        export_format="GLB",
        use_selection=False,
        export_skins=True,
        export_morph=True,
        export_morph_normal=True,
        export_apply=False,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"glTF export failed for {path}: {result}")
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"glTF export did not create {path}")


def main() -> None:
    arguments = _arguments()
    if len(arguments) != 1:
        raise SystemExit(
            "Usage: blender --background --python create_modular_assets.py -- <output-directory>"
        )

    output_dir = Path(arguments[0]).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    generation_report: dict[str, dict[str, int | str]] = {}

    builders = (
        ("base", _create_base_scene),
        ("hair", _create_hair_scene),
        ("outfit", _create_outfit_scene),
        ("accessory", _create_accessory_scene),
    )
    for asset_name, builder in builders:
        _clear_scene()
        builder()
        output_path = output_dir / f"{asset_name}.glb"
        _export_glb(output_path)
        generation_report[asset_name] = {
            "file": output_path.name,
            "byte_length": output_path.stat().st_size,
        }
        print(f"Created modular fixture {asset_name}: {output_path}")

    report_path = output_dir.parent / "asset-generation-report.json"
    report_path.write_text(json.dumps(generation_report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
