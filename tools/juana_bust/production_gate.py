"""Fail-closed inventory checks for the clean GH-22 production scene."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

REQUIRED_REFERENCE_COLLECTIONS = (
    "_REFERENCE_SAM3D",
    "_REFERENCE_HIGHPOLY",
    "_DONOR_VRM",
)
REQUIRED_PRODUCTION_COLLECTIONS = (
    "_PRODUCTION_BODY",
    "_PRODUCTION_HEAD",
    "_PRODUCTION_HAIR",
    "_PRODUCTION_OUTFIT",
    "_RIG",
    "_EXPORT",
)

_DONOR_COLLECTION_PREFIXES = ("_REFERENCE_", "_DONOR_")
_DONOR_ROLE_PREFIXES = ("reference_", "donor_")
_SPIKE_OBJECT_NAMES = {
    "Body",
    "Head",
    "Hair_Rigid",
    "OutfitMesh",
    "LeftEyeMesh",
    "RightEyeMesh",
    "Cube",
}
_SPIKE_MESH_SIGNATURES = {
    (1104, 528),
    (2124, 960),
    (1108, 528),
    (1116, 528),
    (494, 224),
    (500, 224),
    (8, 12),
}
_WAIST_TO_HIP_WIDTH_RANGE = (0.60, 0.74)
_WAIST_TO_HIP_DEPTH_RANGE = (0.60, 0.80)
_SKIN_LINEAR_CHANNEL_RANGES = (
    (0.24, 0.48),
    (0.08, 0.26),
    (0.035, 0.18),
)


class ExportGateError(ValueError):
    """Raised when a scene inventory violates the clean export contract."""


def _objects(inventory: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    objects = inventory.get("objects")
    if not isinstance(objects, Sequence) or isinstance(objects, str | bytes):
        raise ExportGateError("Scene inventory objects must be a list.")
    if not all(isinstance(item, Mapping) for item in objects):
        raise ExportGateError("Every scene inventory object must be a mapping.")
    return list(objects)


def _collections(obj: Mapping[str, Any]) -> set[str]:
    collections = obj.get("collections", [])
    if not isinstance(collections, Sequence) or isinstance(collections, str | bytes):
        raise ExportGateError(
            f"Object {obj.get('name', '<unnamed>')} has invalid collection metadata."
        )
    return {str(name) for name in collections}


def _has_donor_role(obj: Mapping[str, Any]) -> bool:
    role = str(obj.get("role", ""))
    return role.startswith(_DONOR_ROLE_PREFIXES) or any(
        collection.startswith(_DONOR_COLLECTION_PREFIXES)
        for collection in _collections(obj)
    )


def _production_candidates(
    objects: Sequence[Mapping[str, Any]], role: str
) -> list[Mapping[str, Any]]:
    return [
        obj
        for obj in objects
        if obj.get("role") == role
        and bool(obj.get("renderable"))
        and bool(obj.get("exportable"))
    ]


def _single_candidate(
    objects: Sequence[Mapping[str, Any]], role: str
) -> Mapping[str, Any]:
    candidates = _production_candidates(objects, role)
    if len(candidates) != 1:
        raise ExportGateError(
            f"Expected exactly one renderable {role}; found {len(candidates)}."
        )
    return candidates[0]


def _positive_metric(
    report: Mapping[str, Any],
    *,
    band: str,
    metric: str,
) -> float:
    try:
        value = float(report["body_fit"]["bands"][band][metric])
    except (KeyError, TypeError, ValueError) as error:
        raise ExportGateError(
            f"Visual profile is missing numeric {band} {metric} evidence."
        ) from error
    if value <= 0.0:
        raise ExportGateError(f"Visual profile {band} {metric} must be positive.")
    return value


def validate_visual_profile(report: Mapping[str, Any]) -> dict[str, Any]:
    """Reject the broad-body and dark-skin regressions from the first clean pass."""
    try:
        profile_name = str(report["body_fit"]["profile"])
    except (KeyError, TypeError) as error:
        raise ExportGateError("Visual profile name is missing.") from error
    if profile_name != "approved_athletic_hourglass":
        raise ExportGateError(f"Unexpected production body profile: {profile_name}.")

    hip_width = _positive_metric(
        report,
        band="hips",
        metric="production_width_after",
    )
    hip_depth = _positive_metric(
        report,
        band="hips",
        metric="production_depth_after",
    )
    waist_width = _positive_metric(
        report,
        band="waist",
        metric="production_width_after",
    )
    waist_depth = _positive_metric(
        report,
        band="waist",
        metric="production_depth_after",
    )
    width_ratio = waist_width / hip_width
    depth_ratio = waist_depth / hip_depth
    if not _WAIST_TO_HIP_WIDTH_RANGE[0] <= width_ratio <= _WAIST_TO_HIP_WIDTH_RANGE[1]:
        raise ExportGateError(
            "Production waist-to-hip width ratio is outside the approved "
            f"range: {width_ratio:.4f}."
        )
    if not _WAIST_TO_HIP_DEPTH_RANGE[0] <= depth_ratio <= _WAIST_TO_HIP_DEPTH_RANGE[1]:
        raise ExportGateError(
            "Production waist-to-hip depth ratio is outside the approved "
            f"range: {depth_ratio:.4f}."
        )

    skin = report.get("skin_material")
    if not isinstance(skin, Mapping):
        raise ExportGateError("Production skin material evidence is missing.")
    if skin.get("application") != "approved_master_reference_skin_tone":
        raise ExportGateError("Production skin does not use the approved reference tone.")
    color = skin.get("base_color_linear")
    if (
        not isinstance(color, Sequence)
        or isinstance(color, str | bytes)
        or len(color) != 3
    ):
        raise ExportGateError("Production skin base color must contain three channels.")
    try:
        channels = [float(channel) for channel in color]
    except (TypeError, ValueError) as error:
        raise ExportGateError("Production skin base color must be numeric.") from error
    if not all(
        minimum <= channel <= maximum
        for channel, (minimum, maximum) in zip(
            channels,
            _SKIN_LINEAR_CHANNEL_RANGES,
            strict=True,
        )
    ) or not (channels[0] > channels[1] > channels[2]):
        raise ExportGateError(
            f"Production skin base color is outside the approved warm medium range: {channels}."
        )

    return {
        "profile": profile_name,
        "waist_to_hip_width": width_ratio,
        "waist_to_hip_depth": depth_ratio,
        "skin_base_color_linear": channels,
    }


def validate_scene_inventory(inventory: Mapping[str, Any]) -> dict[str, Any]:
    """Validate one clean production character and return its primary inventory."""
    declared_collections = inventory.get("collections")
    if not isinstance(declared_collections, Sequence) or isinstance(
        declared_collections, str | bytes
    ):
        raise ExportGateError("Scene inventory collections must be a list.")
    required = {
        *REQUIRED_REFERENCE_COLLECTIONS,
        *REQUIRED_PRODUCTION_COLLECTIONS,
    }
    missing = sorted(required - {str(name) for name in declared_collections})
    if missing:
        raise ExportGateError(f"Scene is missing required collections: {missing}.")

    objects = _objects(inventory)
    exportable = [obj for obj in objects if bool(obj.get("exportable"))]

    for obj in objects:
        name = str(obj.get("name", "<unnamed>"))
        collections = _collections(obj)
        if _has_donor_role(obj):
            if bool(obj.get("exportable")) or "_EXPORT" in collections:
                raise ExportGateError(
                    f"A donor or reference object is exportable: {name}."
                )
            if bool(obj.get("renderable")):
                raise ExportGateError(
                    f"A donor or reference object is renderable: {name}."
                )

        if bool(obj.get("exportable")) and "_EXPORT" not in collections:
            raise ExportGateError(
                f"Exportable object {name} is not whitelisted in _EXPORT."
            )
        if bool(obj.get("exportable")) and not str(obj.get("role", "")).startswith(
            "production_"
        ):
            raise ExportGateError(f"Non-production object is exportable: {name}.")
        if bool(obj.get("exportable")) and not bool(
            obj.get("root_transform_applied")
        ):
            raise ExportGateError(
                f"Exportable object {name} has an unapplied root transform."
            )

        signature = (obj.get("vertices"), obj.get("triangles"))
        if bool(obj.get("exportable")) and (
            name in _SPIKE_OBJECT_NAMES or signature in _SPIKE_MESH_SIGNATURES
        ):
            raise ExportGateError(
                f"Export contains a procedural spike mannequin signature: {name}."
            )

    body = _single_candidate(objects, "production_body")
    head = _single_candidate(objects, "production_head")
    rigs = [
        obj
        for obj in exportable
        if obj.get("role") == "production_rig" and obj.get("type") == "ARMATURE"
    ]
    if len(rigs) != 1:
        raise ExportGateError(
            f"Expected exactly one exportable production rig; found {len(rigs)}."
        )
    rig_name = str(rigs[0].get("name"))
    for candidate in (body, head):
        if candidate.get("skinned_to") != rig_name:
            raise ExportGateError(
                f"{candidate.get('name')} is not skinned to {rig_name}."
            )

    return {
        "production_body": body["name"],
        "production_head": head["name"],
        "production_rig": rig_name,
        "exportable_object_count": len(exportable),
        "exportable_objects": sorted(str(obj.get("name")) for obj in exportable),
    }
