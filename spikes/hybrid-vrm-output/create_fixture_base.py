"""Create a small, original humanoid GLB fixture for the hybrid VRM spike.

The fixture is intentionally simple. Its purpose is to prove the build contract:
Blender authors geometry and rigging, Three.js inspects composition, and Blender
finalizes a VRM 1.0 artifact.
"""

from __future__ import annotations

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
        raise SystemExit("Expected '-- <output.glb>'") from exc
    return sys.argv[separator + 1 :]


def _clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=True)


def _add_bone(edit_bones, name, head, tail, parent=None, connected=False):
    bone = edit_bones.new(name)
    bone.head = head
    bone.tail = tail
    if parent is not None:
        bone.parent = parent
        bone.use_connect = connected
    return bone


def _create_armature():
    armature_data = bpy.data.armatures.new("HybridSpikeArmature")
    armature = bpy.data.objects.new("Armature", armature_data)
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
        bones, "rightUpperArm", right_shoulder.tail, (-0.38, 0.0, 1.49), right_shoulder, True
    )
    right_lower_arm = _add_bone(
        bones, "rightLowerArm", right_upper_arm.tail, (-0.62, 0.0, 1.49), right_upper_arm, True
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
        bones, "rightLowerLeg", right_upper_leg.tail, (-0.08, 0.0, 0.18), right_upper_leg, True
    )
    _add_bone(
        bones, "rightFoot", right_lower_leg.tail, (-0.08, -0.16, 0.08), right_lower_leg, True
    )

    _add_bone(bones, "L_Eye", (-0.045, -0.095, 1.76), (-0.045, -0.14, 1.76), head)
    _add_bone(bones, "R_Eye", (0.045, -0.095, 1.76), (0.045, -0.14, 1.76), head)
    _add_bone(bones, "jaw", (0.0, -0.02, 1.70), (0.0, -0.08, 1.66), head)

    bpy.ops.object.mode_set(mode="OBJECT")
    return armature


def _material(name: str, color: tuple[float, float, float, float]):
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled is not None:
        principled.inputs["Base Color"].default_value = color
        principled.inputs["Roughness"].default_value = 0.55
    return material


def _bind_mesh_to_bone(obj, armature, bone_name: str) -> None:
    group = obj.vertex_groups.new(name=bone_name)
    group.add(range(len(obj.data.vertices)), 1.0, "REPLACE")
    modifier = obj.modifiers.new(name="Armature", type="ARMATURE")
    modifier.object = armature


def _create_body(armature):
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
    return body


def _create_head(armature):
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
    return head


def _create_eye(armature, name: str, bone_name: str, location):
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
    return eye


def main() -> None:
    arguments = _arguments()
    if len(arguments) != 1:
        raise SystemExit("Usage: blender --background --python create_fixture_base.py -- <output.glb>")

    output_path = Path(arguments[0]).resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    _clear_scene()
    armature = _create_armature()
    _create_body(armature)
    _create_head(armature)
    _create_eye(armature, "LeftEyeMesh", "L_Eye", (-0.045, -0.112, 1.76))
    _create_eye(armature, "RightEyeMesh", "R_Eye", (0.045, -0.112, 1.76))

    bpy.ops.object.select_all(action="SELECT")
    bpy.context.view_layer.objects.active = armature
    result = bpy.ops.export_scene.gltf(
        filepath=str(output_path),
        export_format="GLB",
        use_selection=False,
        export_skins=True,
        export_morph=True,
        export_morph_normal=True,
        export_apply=False,
    )
    if "FINISHED" not in result:
        raise SystemExit(f"glTF export failed: {result}")

    print(f"Created original humanoid fixture: {output_path} ({output_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
