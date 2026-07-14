"""Assemble selected modular assets and export a VRM 1.0 avatar in Blender."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType

import addon_utils
import bpy


def _parse_arguments() -> argparse.Namespace:
    try:
        separator = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit("Expected '-- --spec <file> --output <file> --report <file>'") from exc

    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--build-script", required=True)
    return parser.parse_args(sys.argv[separator + 1 :])


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


def _import_glb(path: Path) -> list:
    before = set(bpy.data.objects.keys())
    result = bpy.ops.import_scene.gltf(filepath=str(path))
    if "FINISHED" not in result:
        raise RuntimeError(f"glTF import failed for {path}: {result}")
    imported = [obj for obj in bpy.data.objects if obj.name not in before]
    if not imported:
        raise RuntimeError(f"glTF import created no objects for {path}")
    return imported


def _find_object(objects: list, expected_name: str):
    exact = [obj for obj in objects if obj.name == expected_name]
    if exact:
        return exact[0]
    prefixed = [obj for obj in objects if obj.name.startswith(f"{expected_name}.")]
    if prefixed:
        return prefixed[0]
    raise RuntimeError(f"Imported component object not found: {expected_name}")


def _find_armature(objects: list):
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(f"Expected one imported armature, found {len(armatures)}")
    return armatures[0]


def _attach_rigid_component(component: dict, imported: list, base_armature) -> None:
    attachment_bone = component.get("attachment_bone")
    if attachment_bone not in base_armature.data.bones:
        raise RuntimeError(
            f"Component {component['asset_id']} references missing attachment bone {attachment_bone}"
        )

    obj = _find_object(imported, component["object_name"])
    world_matrix = obj.matrix_world.copy()
    obj.parent = base_armature
    obj.parent_type = "BONE"
    obj.parent_bone = attachment_bone
    obj.matrix_world = world_matrix


def _rebind_skinned_component(component: dict, imported: list, base_armature) -> None:
    component_armature = _find_armature(imported)
    mesh = _find_object(imported, component["object_name"])
    if mesh.type != "MESH":
        raise RuntimeError(f"Skinned component {component['asset_id']} is not a mesh")

    base_bones = {bone.name for bone in base_armature.data.bones}
    component_bones = {bone.name for bone in component_armature.data.bones}
    required_bones = set(component.get("required_bones", []))
    missing_required = sorted(required_bones.difference(component_bones))
    if missing_required:
        raise RuntimeError(
            f"Skinned component {component['asset_id']} lacks required bones: {missing_required}"
        )
    unknown_bones = sorted(component_bones.difference(base_bones))
    if unknown_bones:
        raise RuntimeError(
            f"Skinned component {component['asset_id']} uses bones absent from the base: {unknown_bones}"
        )

    vertex_groups = {group.name for group in mesh.vertex_groups}
    unknown_groups = sorted(vertex_groups.difference(base_bones))
    if unknown_groups:
        raise RuntimeError(
            f"Skinned component {component['asset_id']} has unknown vertex groups: {unknown_groups}"
        )

    world_matrix = mesh.matrix_world.copy()
    armature_modifiers = [modifier for modifier in mesh.modifiers if modifier.type == "ARMATURE"]
    if not armature_modifiers:
        armature_modifiers = [mesh.modifiers.new(name="Armature", type="ARMATURE")]
    for modifier in armature_modifiers:
        modifier.object = base_armature
    mesh.parent = base_armature
    mesh.matrix_world = world_matrix

    armature_data = component_armature.data
    bpy.data.objects.remove(component_armature, do_unlink=True)
    if armature_data.users == 0:
        bpy.data.armatures.remove(armature_data)


def _hex_to_rgba(value: str) -> tuple[float, float, float, float]:
    if len(value) != 7 or not value.startswith("#"):
        raise ValueError(f"Expected #RRGGBB color, got {value!r}")
    return (
        int(value[1:3], 16) / 255,
        int(value[3:5], 16) / 255,
        int(value[5:7], 16) / 255,
        1.0,
    )


def _apply_material_overrides(overrides: dict[str, str]) -> None:
    for expected_name, color in overrides.items():
        candidates = [
            material
            for material in bpy.data.materials
            if material.name == expected_name or material.name.startswith(f"{expected_name}.")
        ]
        if not candidates:
            raise RuntimeError(f"Material override target not found: {expected_name}")
        rgba = _hex_to_rgba(color)
        for material in candidates:
            material.diffuse_color = rgba
            material.use_nodes = True
            principled = material.node_tree.nodes.get("Principled BSDF")
            if principled is not None:
                principled.inputs["Base Color"].default_value = rgba


def _load_build_module(path: Path) -> ModuleType:
    module_spec = importlib.util.spec_from_file_location("modular_spike_build_avatar", path)
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Cannot load build module from {path}")
    module = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = module
    module_spec.loader.exec_module(module)
    return module


def main() -> int:
    arguments = _parse_arguments()
    compiled_path = Path(arguments.spec).resolve()
    output_path = Path(arguments.output).resolve()
    report_path = Path(arguments.report).resolve()
    build_script_path = Path(arguments.build_script).resolve()
    compiled = json.loads(compiled_path.read_text(encoding="utf-8"))

    if compiled.get("schema_version") != "1.0":
        raise ValueError("CompiledAssemblySpec schema_version must be 1.0.")

    addon_utils.enable("io_scene_vrm", default_set=True, persistent=True)
    _clear_scene()

    base_path = Path(compiled["base_asset"]["path"]).resolve()
    base_objects = _import_glb(base_path)
    base_armature = _find_armature(base_objects)
    base_armature.name = "Armature"

    assembly_events = []
    for component in compiled["components"]:
        component_path = Path(component["path"]).resolve()
        imported = _import_glb(component_path)
        if component["kind"] == "rigid_attachment":
            _attach_rigid_component(component, imported, base_armature)
        elif component["kind"] == "skinned_mesh":
            _rebind_skinned_component(component, imported, base_armature)
        else:
            raise RuntimeError(f"Unsupported component kind: {component['kind']}")
        assembly_events.append(
            {
                "asset_id": component["asset_id"],
                "slot": component["slot"],
                "kind": component["kind"],
                "object_name": component["object_name"],
            }
        )

    _apply_material_overrides(compiled.get("material_overrides", {}))

    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if armatures != [base_armature]:
        raise RuntimeError(
            f"Modular assembly must contain exactly one base armature; found {[obj.name for obj in armatures]}"
        )

    build_module = _load_build_module(build_script_path)
    build_module._apply_spec(bpy, compiled["vrm_spec"], "assembled.glb")

    os.environ["BLENDER_VRM_AUTOMATIC_LICENSE_CONFIRMATION"] = "true"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = bpy.ops.export_scene.vrm(
        "EXEC_DEFAULT",
        filepath=str(output_path),
        armature_object_name=base_armature.name,
        ignore_warning=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"VRM export failed: {result}")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"VRM export did not create {output_path}")

    build_module._validate_vrm(str(output_path))

    scene_objects = sorted(obj.name for obj in bpy.data.objects)
    report = {
        "valid": True,
        "character_id": compiled["character_id"],
        "output": str(output_path),
        "byte_length": output_path.stat().st_size,
        "armature_objects": [base_armature.name],
        "selected_components": assembly_events,
        "disabled_components": compiled.get("disabled_components", []),
        "scene_objects_before_export": scene_objects,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Exported modular VRM: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
