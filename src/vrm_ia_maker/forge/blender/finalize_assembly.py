"""Assemble a schema 1.1 composition and export one staged VRM in Blender."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

_HEX_DIGITS = frozenset("0123456789abcdefABCDEF")
_COMPILED_FIELDS = {
    "schema_version",
    "character_id",
    "display_name",
    "asset_pack_id",
    "base_adapter_id",
    "base_adapter_version",
    "provenance",
    "base_asset",
    "components",
    "disabled_components",
    "material_overrides",
    "vrm_spec",
}


def _parse_arguments() -> argparse.Namespace:
    try:
        separator = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit(
            "Expected '-- --spec <file> --output <file> --evidence <file>'."
        ) from exc

    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--evidence", required=True)
    return parser.parse_args(sys.argv[separator + 1 :])


def _validate_compiled_spec(compiled: Mapping[str, object]) -> None:
    if compiled.get("schema_version") != "1.1":
        raise ValueError("CompiledAssemblySpec schema_version must be 1.1.")
    _reject_extra(compiled, _COMPILED_FIELDS, "CompiledAssemblySpec")
    for field_name in (
        "character_id",
        "display_name",
        "asset_pack_id",
        "base_adapter_id",
        "base_adapter_version",
    ):
        _string(compiled.get(field_name), f"CompiledAssemblySpec {field_name}")

    base_asset = _mapping(compiled.get("base_asset"), "base_asset")
    _validate_asset(base_asset, "base_asset")
    components = _sequence(compiled.get("components"), "components")
    for index, raw_component in enumerate(components):
        component = _mapping(raw_component, f"components[{index}]")
        _validate_component(component, index)

    disabled_components = _sequence(
        compiled.get("disabled_components"),
        "disabled_components",
    )
    for index, raw_disabled in enumerate(disabled_components):
        disabled = _mapping(raw_disabled, f"disabled_components[{index}]")
        for field_name in ("asset_id", "slot", "object_name"):
            _string(
                disabled.get(field_name),
                f"disabled_components[{index}].{field_name}",
            )

    overrides = _mapping(compiled.get("material_overrides"), "material_overrides")
    for material_name, color in overrides.items():
        _string(material_name, "Material override name")
        _hex_to_rgba(_string(color, f"Material override {material_name}"))

    vrm_spec = _mapping(compiled.get("vrm_spec"), "vrm_spec")
    _validate_vrm_spec(vrm_spec, compiled, base_asset)


def _validate_asset(asset: Mapping[str, object], label: str) -> None:
    for field_name in ("asset_id", "path", "object_name", "sha256"):
        _string(asset.get(field_name), f"{label}.{field_name}")
    digest = str(asset["sha256"])
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{label}.sha256 must be a lowercase SHA-256 digest.")


def _validate_component(component: Mapping[str, object], index: int) -> None:
    label = f"components[{index}]"
    _validate_asset(component, label)
    for field_name in ("slot", "kind"):
        _string(component.get(field_name), f"{label}.{field_name}")
    kind = component["kind"]
    if kind == "rigid_attachment":
        _string(component.get("attachment_bone"), f"{label}.attachment_bone")
    elif kind == "skinned_mesh":
        required_bones = _sequence(
            component.get("required_bones"),
            f"{label}.required_bones",
        )
        if not required_bones:
            raise ValueError(f"{label}.required_bones cannot be empty.")
        for bone_name in required_bones:
            _string(bone_name, f"{label}.required_bones value")
    else:
        raise ValueError(f"Unsupported component kind: {kind!r}.")


def _validate_vrm_spec(
    vrm_spec: Mapping[str, object],
    compiled: Mapping[str, object],
    base_asset: Mapping[str, object],
) -> None:
    if vrm_spec.get("spec_version") != "1.0":
        raise ValueError("VrmBuildSpec spec_version must be 1.0.")
    if vrm_spec.get("avatar_id") != compiled["character_id"]:
        raise ValueError("VrmBuildSpec avatar_id must match character_id.")
    if vrm_spec.get("display_name") != compiled["display_name"]:
        raise ValueError("VrmBuildSpec display_name must match the assembly.")
    if vrm_spec.get("base_asset_id") != base_asset["asset_id"]:
        raise ValueError("VrmBuildSpec base_asset_id must match base_asset.")
    for field_name in ("bones", "expression_map", "look_at", "metadata"):
        value = _mapping(vrm_spec.get(field_name), f"vrm_spec.{field_name}")
        if not value:
            raise ValueError(f"vrm_spec.{field_name} cannot be empty.")


def _verify_asset_hash(path: Path, expected_digest: str, asset_id: str) -> None:
    if not path.is_file():
        raise RuntimeError(f"Asset {asset_id} does not exist: {path}.")
    digest = hashlib.sha256()
    with path.open("rb") as asset_file:
        for chunk in iter(lambda: asset_file.read(1024 * 1024), b""):
            digest.update(chunk)
    actual_digest = digest.hexdigest()
    if actual_digest != expected_digest:
        raise RuntimeError(
            f"SHA-256 mismatch for asset {asset_id}: expected {expected_digest}, "
            f"got {actual_digest}."
        )


def _clear_scene(bpy_module: Any) -> None:
    bpy_module.ops.object.select_all(action="SELECT")
    bpy_module.ops.object.delete(use_global=True)
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
        collection = getattr(bpy_module.data, collection_name, None)
        if collection is None:
            continue
        for block in list(collection):
            if block.users == 0:
                collection.remove(block)


def _import_glb(bpy_module: Any, path: Path) -> list[Any]:
    object_names_before = set(bpy_module.data.objects.keys())
    result = bpy_module.ops.import_scene.gltf(filepath=str(path))
    if "FINISHED" not in result:
        raise RuntimeError(f"glTF import failed for {path}: {result}.")
    imported = [
        obj for obj in bpy_module.data.objects if obj.name not in object_names_before
    ]
    if not imported:
        raise RuntimeError(f"glTF import created no objects for {path}.")
    return imported


def _find_object(objects: Sequence[Any], expected_name: str) -> Any:
    matches = [
        obj
        for obj in objects
        if obj.name == expected_name or obj.name.startswith(f"{expected_name}.")
    ]
    if not matches:
        raise RuntimeError(f"Imported object not found: {expected_name}.")
    if len(matches) != 1:
        raise RuntimeError(
            f"Imported object identity is ambiguous for {expected_name}: "
            f"{sorted(obj.name for obj in matches)}."
        )
    return matches[0]


def _find_armature(objects: Sequence[Any], label: str) -> Any:
    armatures = [obj for obj in objects if obj.type == "ARMATURE"]
    if len(armatures) != 1:
        raise RuntimeError(
            f"{label} must contain exactly one armature; found "
            f"{sorted(obj.name for obj in armatures)}."
        )
    return armatures[0]


def _attach_rigid_component(
    component: Mapping[str, object],
    imported: Sequence[Any],
    base_armature: Any,
) -> None:
    imported_armatures = [obj.name for obj in imported if obj.type == "ARMATURE"]
    if imported_armatures:
        raise RuntimeError(
            f"Rigid component {component['asset_id']} cannot contain armatures: "
            f"{sorted(imported_armatures)}."
        )
    attachment_bone = _string(
        component.get("attachment_bone"),
        f"Attachment bone for {component['asset_id']}",
    )
    if attachment_bone not in base_armature.data.bones:
        raise RuntimeError(
            f"Component {component['asset_id']} references missing attachment bone "
            f"{attachment_bone!r}."
        )
    obj = _find_object(
        imported,
        _string(component.get("object_name"), "Component object_name"),
    )
    world_matrix = obj.matrix_world.copy()
    obj.parent = base_armature
    obj.parent_type = "BONE"
    obj.parent_bone = attachment_bone
    obj.matrix_world = world_matrix


def _rebind_skinned_component(
    bpy_module: Any,
    component: Mapping[str, object],
    imported: Sequence[Any],
    base_armature: Any,
) -> None:
    component_armature = _find_armature(
        imported,
        f"Skinned component {component['asset_id']}",
    )
    mesh = _find_object(
        imported,
        _string(component.get("object_name"), "Component object_name"),
    )
    if mesh.type != "MESH":
        raise RuntimeError(f"Skinned component {component['asset_id']} is not a mesh.")

    base_bones = {bone.name for bone in base_armature.data.bones.values()}
    component_bones = {bone.name for bone in component_armature.data.bones.values()}
    required_bones = {
        _string(value, f"Required bone for {component['asset_id']}")
        for value in _sequence(component.get("required_bones"), "required_bones")
    }
    missing_required = sorted(required_bones.difference(component_bones))
    if missing_required:
        raise RuntimeError(
            f"Skinned component {component['asset_id']} lacks required bones: "
            f"{missing_required}."
        )
    unknown_bones = sorted(component_bones.difference(base_bones))
    if unknown_bones:
        raise RuntimeError(
            f"Skinned component {component['asset_id']} uses bones absent from the "
            f"base: {unknown_bones}."
        )
    unknown_groups = sorted(
        group.name for group in mesh.vertex_groups if group.name not in base_bones
    )
    if unknown_groups:
        raise RuntimeError(
            f"Skinned component {component['asset_id']} has unknown vertex groups: "
            f"{unknown_groups}."
        )

    world_matrix = mesh.matrix_world.copy()
    armature_modifiers = [
        modifier for modifier in mesh.modifiers if modifier.type == "ARMATURE"
    ]
    if not armature_modifiers:
        armature_modifiers = [
            mesh.modifiers.new(name="Armature", type="ARMATURE")
        ]
    for modifier in armature_modifiers:
        modifier.object = base_armature
    mesh.parent = base_armature
    mesh.matrix_world = world_matrix

    armature_data = component_armature.data
    bpy_module.data.objects.remove(component_armature, do_unlink=True)
    if armature_data.users == 0:
        bpy_module.data.armatures.remove(armature_data)


def _hex_to_rgba(value: str) -> tuple[float, float, float, float]:
    if (
        len(value) != 7
        or not value.startswith("#")
        or any(character not in _HEX_DIGITS for character in value[1:])
    ):
        raise ValueError(f"Expected #RRGGBB color, got {value!r}.")
    return (
        int(value[1:3], 16) / 255,
        int(value[3:5], 16) / 255,
        int(value[5:7], 16) / 255,
        1.0,
    )


def _apply_material_overrides(
    bpy_module: Any,
    overrides: Mapping[str, object],
) -> None:
    for expected_name, raw_color in overrides.items():
        candidates = [
            material
            for material in bpy_module.data.materials
            if material.name == expected_name
            or material.name.startswith(f"{expected_name}.")
        ]
        if not candidates:
            raise RuntimeError(f"Material override target not found: {expected_name}.")
        rgba = _hex_to_rgba(_string(raw_color, f"Color for {expected_name}"))
        for material in candidates:
            material.diffuse_color = rgba
            material.use_nodes = True
            node_tree = getattr(material, "node_tree", None)
            if node_tree is None:
                continue
            principled = node_tree.nodes.get("Principled BSDF")
            if principled is not None:
                principled.inputs["Base Color"].default_value = rgba


def _resolve_asset_path(asset: Mapping[str, object], spec_path: Path) -> Path:
    path = Path(_string(asset.get("path"), f"Path for {asset.get('asset_id')}"))
    if not path.is_absolute():
        path = spec_path.parent / path
    return path.resolve()


def _write_evidence(
    path: Path,
    *,
    compiled: Mapping[str, object],
    base_armature: Any,
    selected_components: list[dict[str, str]],
    configured: Mapping[str, list[str]],
    scene_objects: Sequence[Any],
) -> None:
    evidence = {
        "schema_version": "1.0",
        "character_id": compiled["character_id"],
        "base_adapter_id": compiled["base_adapter_id"],
        "base_adapter_version": compiled["base_adapter_version"],
        "armature_objects": [base_armature.name],
        "selected_components": selected_components,
        "disabled_components": compiled["disabled_components"],
        "scene_objects_before_export": sorted(obj.name for obj in scene_objects),
        "humanoid_bones": configured["humanoid_bones"],
        "expressions": configured["expressions"],
        "look_at": _mapping(compiled["vrm_spec"], "vrm_spec")["look_at"],
        "metadata": _mapping(compiled["vrm_spec"], "vrm_spec")["metadata"],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as evidence_file:
        json.dump(evidence, evidence_file, indent=2)
        evidence_file.write("\n")


def _configure_vrm(
    *,
    armature: Any,
    scene_objects: Sequence[Any],
    vrm_spec: Mapping[str, object],
) -> dict[str, list[str]]:
    if __package__:
        from .vrm_setup import configure_vrm

        return configure_vrm(
            armature=armature,
            scene_objects=scene_objects,
            vrm_spec=vrm_spec,
        )

    module_path = Path(__file__).resolve().with_name("vrm_setup.py")
    module_spec = importlib.util.spec_from_file_location(
        "vrm_ia_maker_blender_vrm_setup",
        module_path,
    )
    if module_spec is None or module_spec.loader is None:
        raise RuntimeError(f"Cannot load VRM setup module from {module_path}.")
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    configure_vrm = module.configure_vrm
    configured = configure_vrm(
        armature=armature,
        scene_objects=scene_objects,
        vrm_spec=vrm_spec,
    )
    if not isinstance(configured, dict):
        raise RuntimeError("VRM setup returned invalid configuration evidence.")
    return configured


def main() -> int:
    arguments = _parse_arguments()
    spec_path = Path(arguments.spec).resolve()
    output_path = Path(arguments.output).resolve()
    evidence_path = Path(arguments.evidence).resolve()
    if output_path.exists() or evidence_path.exists():
        raise FileExistsError("Staged Blender output targets must not already exist.")

    compiled_value = json.loads(spec_path.read_text(encoding="utf-8"))
    if not isinstance(compiled_value, Mapping):
        raise ValueError("CompiledAssemblySpec must contain a JSON object.")
    compiled = compiled_value
    _validate_compiled_spec(compiled)

    base_asset = _mapping(compiled["base_asset"], "base_asset")
    component_records = [
        _mapping(component, f"components[{index}]")
        for index, component in enumerate(
            _sequence(compiled["components"], "components")
        )
    ]
    for asset in (base_asset, *component_records):
        _verify_asset_hash(
            _resolve_asset_path(asset, spec_path),
            _string(asset["sha256"], "Asset sha256"),
            _string(asset["asset_id"], "Asset asset_id"),
        )

    import addon_utils  # type: ignore[import-not-found]
    import bpy  # type: ignore[import-not-found]

    addon_utils.enable("io_scene_vrm", default_set=True, persistent=True)
    _clear_scene(bpy)
    base_objects = _import_glb(bpy, _resolve_asset_path(base_asset, spec_path))
    base_armature = _find_armature(base_objects, "Base asset")
    expected_base_object = _find_object(
        base_objects,
        _string(base_asset["object_name"], "Base object_name"),
    )
    if expected_base_object is not base_armature:
        raise RuntimeError(
            f"Base object {base_asset['object_name']!r} is not the imported armature."
        )

    selected_components: list[dict[str, str]] = []
    for component in component_records:
        imported = _import_glb(bpy, _resolve_asset_path(component, spec_path))
        kind = _string(component["kind"], "Component kind")
        if kind == "rigid_attachment":
            _attach_rigid_component(component, imported, base_armature)
        elif kind == "skinned_mesh":
            _rebind_skinned_component(bpy, component, imported, base_armature)
        else:
            raise RuntimeError(f"Unsupported component kind: {kind}.")
        selected_components.append(
            {
                "asset_id": _string(component["asset_id"], "Component asset_id"),
                "slot": _string(component["slot"], "Component slot"),
                "kind": kind,
                "object_name": _string(
                    component["object_name"],
                    "Component object_name",
                ),
            }
        )

    _apply_material_overrides(
        bpy,
        _mapping(compiled["material_overrides"], "material_overrides"),
    )
    armatures = [obj for obj in bpy.data.objects if obj.type == "ARMATURE"]
    if len(armatures) != 1 or armatures[0] is not base_armature:
        raise RuntimeError(
            "Modular assembly must contain exactly one base armature; found "
            f"{sorted(obj.name for obj in armatures)}."
        )

    vrm_spec = _mapping(compiled["vrm_spec"], "vrm_spec")
    configured = _configure_vrm(
        armature=base_armature,
        scene_objects=list(bpy.data.objects),
        vrm_spec=vrm_spec,
    )
    scene_objects = list(bpy.data.objects)

    os.environ["BLENDER_VRM_AUTOMATIC_LICENSE_CONFIRMATION"] = "true"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = bpy.ops.export_scene.vrm(
        "EXEC_DEFAULT",
        filepath=str(output_path),
        armature_object_name=base_armature.name,
        ignore_warning=True,
    )
    if "FINISHED" not in result:
        raise RuntimeError(f"VRM export failed: {result}.")
    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError(f"VRM export did not create {output_path}.")

    _write_evidence(
        evidence_path,
        compiled=compiled,
        base_armature=base_armature,
        selected_components=selected_components,
        configured=configured,
        scene_objects=scene_objects,
    )
    print(f"Exported production modular VRM: {output_path}")
    return 0


def _reject_extra(
    value: Mapping[str, object],
    allowed_fields: set[str],
    label: str,
) -> None:
    unexpected = sorted(set(value).difference(allowed_fields))
    if unexpected:
        raise ValueError(f"{label} contains unexpected fields: {unexpected}.")


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    return value


def _sequence(value: object, label: str) -> Sequence[object]:
    if not isinstance(value, Sequence) or isinstance(
        value,
        str | bytes | bytearray,
    ):
        raise ValueError(f"{label} must be an array.")
    return value


def _string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{label} must be a non-empty string.")
    return value


if __name__ == "__main__":
    raise SystemExit(main())
