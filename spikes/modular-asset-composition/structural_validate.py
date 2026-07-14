"""Validate structural and modular contracts of a generated VRM 1.x file."""

from __future__ import annotations

import hashlib
import json
import struct
import sys
from pathlib import Path


REQUIRED_BONES = {
    "hips",
    "spine",
    "chest",
    "neck",
    "head",
    "leftUpperArm",
    "leftLowerArm",
    "leftHand",
    "rightUpperArm",
    "rightLowerArm",
    "rightHand",
    "leftUpperLeg",
    "leftLowerLeg",
    "leftFoot",
    "rightUpperLeg",
    "rightLowerLeg",
    "rightFoot",
}
REQUIRED_EXPRESSIONS = {"blink", "aa", "ih", "ou", "ee", "oh"}


def _read_glb_json(path: Path) -> dict:
    payload = path.read_bytes()
    if len(payload) < 20:
        raise ValueError("The VRM file is too short to be a GLB container.")

    magic, version, total_length = struct.unpack_from("<III", payload, 0)
    if magic != 0x46546C67:
        raise ValueError("The output does not have the glTF binary magic header.")
    if version != 2:
        raise ValueError(f"Expected glTF 2.0, found version {version}.")
    if total_length != len(payload):
        raise ValueError(
            f"GLB length mismatch: header={total_length}, actual={len(payload)}."
        )

    json_length, json_type = struct.unpack_from("<II", payload, 12)
    if json_type != 0x4E4F534A:
        raise ValueError("The first GLB chunk is not JSON.")
    raw_json = payload[20 : 20 + json_length].rstrip(b"\x00 \t\r\n")
    return json.loads(raw_json.decode("utf-8"))


def _node_index_by_name(nodes: list[dict], name: str) -> int:
    matches = [index for index, node in enumerate(nodes) if node.get("name") == name]
    if len(matches) != 1:
        raise ValueError(f"Expected one node named {name!r}, found {len(matches)}.")
    return matches[0]


def _parent_map(nodes: list[dict]) -> dict[int, int]:
    parents: dict[int, int] = {}
    for parent_index, node in enumerate(nodes):
        for child_index in node.get("children", []):
            parents[child_index] = parent_index
    return parents


def _has_ancestor(nodes: list[dict], parents: dict[int, int], node_index: int, name: str) -> bool:
    current = node_index
    visited = set()
    while current in parents and current not in visited:
        visited.add(current)
        current = parents[current]
        if nodes[current].get("name") == name:
            return True
    return False


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: structural_validate.py <avatar.vrm> <compiled-spec.json> <report.json>"
        )

    vrm_path = Path(sys.argv[1]).resolve()
    compiled_path = Path(sys.argv[2]).resolve()
    report_path = Path(sys.argv[3]).resolve()
    compiled = json.loads(compiled_path.read_text(encoding="utf-8"))
    document = _read_glb_json(vrm_path)

    extension = document.get("extensions", {}).get("VRMC_vrm")
    if not isinstance(extension, dict):
        raise ValueError("The output does not contain the VRMC_vrm extension.")
    spec_version = extension.get("specVersion")
    if not isinstance(spec_version, str) or not spec_version.startswith("1."):
        raise ValueError(f"Expected VRM 1.x, found {spec_version!r}.")

    human_bones = extension.get("humanoid", {}).get("humanBones", {})
    if not isinstance(human_bones, dict):
        raise ValueError("VRM humanoid humanBones must be an object.")
    missing_bones = sorted(REQUIRED_BONES.difference(human_bones))
    if missing_bones:
        raise ValueError(f"Missing required humanoid bones: {missing_bones}")

    preset = extension.get("expressions", {}).get("preset", {})
    if not isinstance(preset, dict):
        raise ValueError("VRM preset expressions must be an object.")
    missing_expressions = sorted(REQUIRED_EXPRESSIONS.difference(preset))
    if missing_expressions:
        raise ValueError(f"Missing required expressions: {missing_expressions}")

    nodes = document.get("nodes", [])
    if not isinstance(nodes, list):
        raise ValueError("glTF nodes must be an array.")
    node_names = {node.get("name") for node in nodes if node.get("name")}

    selected_components = compiled.get("components", [])
    disabled_components = compiled.get("disabled_components", [])
    selected_names = [component["object_name"] for component in selected_components]
    disabled_names = [component["object_name"] for component in disabled_components]
    missing_selected = sorted(name for name in selected_names if name not in node_names)
    present_disabled = sorted(name for name in disabled_names if name in node_names)
    if missing_selected:
        raise ValueError(f"Selected component nodes are missing: {missing_selected}")
    if present_disabled:
        raise ValueError(f"Disabled component nodes leaked into the VRM: {present_disabled}")

    skins = document.get("skins", [])
    if len(skins) != 1:
        raise ValueError(f"Expected one shared skin, found {len(skins)}.")

    body_index = _node_index_by_name(nodes, "Body")
    outfit_component = next(
        component for component in selected_components if component["slot"] == "outfit"
    )
    outfit_index = _node_index_by_name(nodes, outfit_component["object_name"])
    body_skin = nodes[body_index].get("skin")
    outfit_skin = nodes[outfit_index].get("skin")
    if body_skin is None or outfit_skin is None:
        raise ValueError("Body and outfit must both be skinned meshes.")
    if body_skin != outfit_skin:
        raise ValueError(
            f"Body and outfit must share one skin, found {body_skin} and {outfit_skin}."
        )

    hair_component = next(
        component for component in selected_components if component["slot"] == "hair"
    )
    hair_index = _node_index_by_name(nodes, hair_component["object_name"])
    parents = _parent_map(nodes)
    if not _has_ancestor(nodes, parents, hair_index, hair_component["attachment_bone"]):
        raise ValueError(
            f"Hair node is not attached below bone {hair_component['attachment_bone']}."
        )

    payload = vrm_path.read_bytes()
    report = {
        "valid": True,
        "file": vrm_path.name,
        "character_id": compiled["character_id"],
        "byte_length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "gltf_asset_version": document.get("asset", {}).get("version"),
        "vrm_spec_version": spec_version,
        "extensions_used": document.get("extensionsUsed", []),
        "humanoid_bones": sorted(human_bones),
        "preset_expressions": sorted(preset),
        "selected_component_nodes": sorted(selected_names),
        "disabled_component_nodes": sorted(disabled_names),
        "shared_skin_index": body_skin,
        "hair_attachment_bone": hair_component["attachment_bone"],
        "single_skin": True,
        "required_bones_present": True,
        "required_expressions_present": True,
        "selected_components_present": True,
        "disabled_components_absent": True,
        "body_and_outfit_share_skin": True,
        "hair_is_bone_attached": True,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Structural modular VRM validation passed: {vrm_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
