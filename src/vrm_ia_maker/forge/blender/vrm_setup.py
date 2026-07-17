"""Configure VRM 1.0 state from a strict Blender-facing build specification."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import quote

_LOOK_AT_INPUT_MAX_DEGREES = 90.0


def configure_vrm(
    *,
    armature: Any,
    scene_objects: Sequence[Any],
    vrm_spec: Mapping[str, object],
) -> dict[str, list[str]]:
    """Apply adapter-provided VRM mappings and return the configured identities."""
    if armature.type != "ARMATURE":
        raise RuntimeError(f"VRM owner {armature.name!r} is not an armature.")
    extension = getattr(armature.data, "vrm_addon_extension", None)
    if extension is None:
        raise RuntimeError(
            f"Armature {armature.name!r} has no VRM Add-on extension data."
        )
    if vrm_spec.get("spec_version") != "1.0":
        raise ValueError("VrmBuildSpec spec_version must be 1.0.")

    extension.spec_version = "1.0"
    vrm1 = extension.vrm1
    bone_names = _configure_humanoid(
        armature=armature,
        human_bones=vrm1.humanoid.human_bones,
        bone_map=_mapping(vrm_spec.get("bones"), "VrmBuildSpec bones"),
    )
    expression_names = _configure_expressions(
        expressions=vrm1.expressions,
        scene_objects=scene_objects,
        expression_map=_mapping(
            vrm_spec.get("expression_map"),
            "VrmBuildSpec expression_map",
        ),
    )
    _configure_look_at(
        look_at=vrm1.look_at,
        armature=armature,
        bone_map=_mapping(vrm_spec.get("bones"), "VrmBuildSpec bones"),
        specification=_mapping(vrm_spec.get("look_at"), "VrmBuildSpec look_at"),
    )
    _configure_metadata(
        meta=vrm1.meta,
        vrm_spec=vrm_spec,
        metadata=_mapping(vrm_spec.get("metadata"), "VrmBuildSpec metadata"),
    )
    return {
        "humanoid_bones": sorted(bone_names),
        "expressions": sorted(expression_names),
    }


def _configure_humanoid(
    *,
    armature: Any,
    human_bones: Any,
    bone_map: Mapping[str, object],
) -> list[str]:
    if not bone_map:
        raise RuntimeError("VrmBuildSpec bones cannot be empty.")

    available_bones = set(armature.data.bones.keys())
    human_bone_properties = human_bones.human_bone_name_to_human_bone()
    vrm_slots = {
        human_bone_name.value: human_bone
        for human_bone_name, human_bone in human_bone_properties.items()
    }
    for human_bone in vrm_slots.values():
        human_bone.node.bone_name = ""

    assigned_targets: dict[str, str] = {}
    configured: list[str] = []
    for vrm_slot, target_value in bone_map.items():
        target_bone = _string(target_value, f"Bone target for {vrm_slot}")
        human_bone = vrm_slots.get(vrm_slot)
        if human_bone is None:
            raise RuntimeError(f"Unknown VRM humanoid slot: {vrm_slot}.")
        if target_bone not in available_bones:
            raise RuntimeError(
                f"VRM humanoid slot {vrm_slot} references missing armature bone "
                f"{target_bone!r}."
            )
        previous_slot = assigned_targets.get(target_bone)
        if previous_slot is not None:
            raise RuntimeError(
                f"Armature bone {target_bone!r} is assigned to more than one VRM "
                f"humanoid slot: {previous_slot}, {vrm_slot}."
            )
        assigned_targets[target_bone] = vrm_slot
        human_bone.node.bone_name = target_bone
        configured.append(vrm_slot)

    human_bones.initial_automatic_bone_assignment = False
    human_bones.filter_by_human_bone_hierarchy = False
    human_bones.allow_non_humanoid_rig = False
    return configured


def _configure_expressions(
    *,
    expressions: Any,
    scene_objects: Sequence[Any],
    expression_map: Mapping[str, object],
) -> list[str]:
    if not expression_map:
        raise RuntimeError("VrmBuildSpec expression_map cannot be empty.")

    shape_key_owners = _shape_key_owners(scene_objects)
    preset_by_name = dict(expressions.preset.name_to_expression_dict())
    for expression in preset_by_name.values():
        expression.morph_target_binds.clear()
    expressions.custom.clear()

    configured: list[str] = []
    for expression_name, raw_bindings in expression_map.items():
        bindings = _sequence(
            raw_bindings,
            f"Expression bindings for {expression_name}",
        )
        if not bindings:
            raise RuntimeError(
                f"Expression {expression_name!r} requires at least one binding."
            )
        expression = preset_by_name.get(expression_name)
        if expression is None:
            expression = expressions.custom.add()
            expression.custom_name = expression_name

        for index, raw_binding in enumerate(bindings):
            binding = _mapping(
                raw_binding,
                f"Expression binding {index} for {expression_name}",
            )
            shape_key = _string(
                binding.get("shape_key"),
                f"Shape key for expression {expression_name}",
            )
            owners = shape_key_owners.get(shape_key, [])
            if not owners:
                raise RuntimeError(
                    f"Expression {expression_name!r} references missing shape key "
                    f"{shape_key!r}."
                )
            if len(owners) != 1:
                raise RuntimeError(
                    f"Shape key {shape_key!r} exists on more than one mesh: "
                    f"{sorted(owners)}."
                )
            weight = _number(
                binding.get("weight"),
                f"Weight for expression {expression_name}",
            )
            if weight < 0.0 or weight > 1.0:
                raise RuntimeError(
                    f"Expression {expression_name!r} weight must be between 0 and 1."
                )
            morph_bind = expression.morph_target_binds.add()
            morph_bind.node.mesh_object_name = owners[0]
            morph_bind.index = shape_key
            morph_bind.weight = weight
        configured.append(expression_name)

    expressions.initial_automatic_expression_assignment = False
    return configured


def _shape_key_owners(scene_objects: Sequence[Any]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for obj in scene_objects:
        if getattr(obj, "type", None) != "MESH":
            continue
        shape_keys = getattr(getattr(obj, "data", None), "shape_keys", None)
        if shape_keys is None:
            continue
        for key_block in shape_keys.key_blocks:
            owners.setdefault(key_block.name, []).append(obj.name)
    return owners


def _configure_look_at(
    *,
    look_at: Any,
    armature: Any,
    bone_map: Mapping[str, object],
    specification: Mapping[str, object],
) -> None:
    required_slots = ("head", "leftEye", "rightEye")
    missing_slots = [slot for slot in required_slots if slot not in bone_map]
    if missing_slots:
        raise RuntimeError(
            f"Bone look-at requires VRM mappings for: {missing_slots}."
        )

    head = armature.data.bones[_string(bone_map["head"], "Head bone")]
    left_eye = armature.data.bones[_string(bone_map["leftEye"], "Left eye bone")]
    right_eye = armature.data.bones[_string(bone_map["rightEye"], "Right eye bone")]
    look_at.type = "bone"
    look_at.offset_from_head_bone = tuple(
        (
            float(left_eye.head_local[index]) + float(right_eye.head_local[index])
        )
        / 2.0
        - float(head.head_local[index])
        for index in range(3)
    )

    range_mappings = (
        (
            look_at.range_map_horizontal_inner,
            "horizontal_inner_degrees",
        ),
        (
            look_at.range_map_horizontal_outer,
            "horizontal_outer_degrees",
        ),
        (
            look_at.range_map_vertical_down,
            "vertical_down_degrees",
        ),
        (
            look_at.range_map_vertical_up,
            "vertical_up_degrees",
        ),
    )
    for range_map, field_name in range_mappings:
        output_scale = _number(
            specification.get(field_name),
            f"Look-at {field_name}",
        )
        if output_scale < 0:
            raise RuntimeError(f"Look-at {field_name} cannot be negative.")
        range_map.input_max_value = _LOOK_AT_INPUT_MAX_DEGREES
        range_map.output_scale = output_scale


def _configure_metadata(
    *,
    meta: Any,
    vrm_spec: Mapping[str, object],
    metadata: Mapping[str, object],
) -> None:
    display_name = _string(vrm_spec.get("display_name"), "VRM display_name")
    author = _string(metadata.get("author"), "VRM metadata author")
    license_name = _string(metadata.get("license"), "VRM metadata license")
    commercial_use = _boolean(
        metadata.get("commercial_use"),
        "VRM metadata commercial_use",
    )
    redistribution = _boolean(
        metadata.get("redistribution"),
        "VRM metadata redistribution",
    )

    meta.vrm_name = display_name
    meta.version = _string(vrm_spec.get("spec_version"), "VRM spec_version")
    meta.authors.clear()
    meta.authors.add().value = author
    contact_url = metadata.get("contact_url")
    meta.contact_information = "" if contact_url is None else str(contact_url)
    meta.avatar_permission = "everyone" if redistribution else "onlyAuthor"
    meta.allow_excessively_violent_usage = False
    meta.allow_excessively_sexual_usage = False
    meta.commercial_usage = (
        "corporation" if commercial_use else "personalNonProfit"
    )
    meta.allow_political_or_religious_usage = False
    meta.allow_antisocial_or_hate_usage = False
    meta.credit_notation = "required"
    meta.allow_redistribution = redistribution
    meta.modification = "prohibited"
    meta.other_license_url = (
        f"https://spdx.org/licenses/{quote(license_name, safe='-._~')}.html"
    )


def _mapping(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{label} must be an object.")
    if not all(isinstance(key, str) and key for key in value):
        raise ValueError(f"{label} keys must be non-empty strings.")
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


def _number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{label} must be a number.")
    return float(value)


def _boolean(value: object, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean.")
    return value
