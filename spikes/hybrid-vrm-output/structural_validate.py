"""Validate the binary and VRM 1.0 contracts produced by the hybrid spike."""

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


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: structural_validate.py <avatar.vrm> <report.json>")

    vrm_path = Path(sys.argv[1]).resolve()
    report_path = Path(sys.argv[2]).resolve()
    if not vrm_path.is_file():
        raise FileNotFoundError(vrm_path)

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

    payload = vrm_path.read_bytes()
    report = {
        "valid": True,
        "file": vrm_path.name,
        "byte_length": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "gltf_asset_version": document.get("asset", {}).get("version"),
        "vrm_spec_version": spec_version,
        "extensions_used": document.get("extensionsUsed", []),
        "humanoid_bones": sorted(human_bones),
        "preset_expressions": sorted(preset),
        "required_bones_present": True,
        "required_expressions_present": True,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Structural VRM validation passed: {vrm_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
