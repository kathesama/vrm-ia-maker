"""Seal a generated asset pack with content hashes and byte lengths."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


REQUIRED_PROVENANCE_FIELDS = {
    "author",
    "source",
    "license",
    "commercial_use",
    "modification_allowed",
    "redistribution_allowed",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _seal_asset(entry: dict, output_root: Path) -> None:
    relative_path = Path(entry["path"])
    asset_path = (output_root / relative_path).resolve()
    if output_root.resolve() not in asset_path.parents:
        raise ValueError(f"Asset path escapes the build root: {relative_path}")
    if not asset_path.is_file():
        raise FileNotFoundError(asset_path)
    entry["sha256"] = _sha256(asset_path)
    entry["byte_length"] = asset_path.stat().st_size


def main() -> int:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: seal_manifests.py <asset-pack.template.json> <build-root> <output.json>"
        )

    template_path = Path(sys.argv[1]).resolve()
    build_root = Path(sys.argv[2]).resolve()
    output_path = Path(sys.argv[3]).resolve()
    document = json.loads(template_path.read_text(encoding="utf-8"))

    if document.get("schema_version") != "1.0":
        raise ValueError("AssetPackManifest schema_version must be 1.0.")
    provenance = document.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("AssetPackManifest provenance must be an object.")
    missing_provenance = sorted(REQUIRED_PROVENANCE_FIELDS.difference(provenance))
    if missing_provenance:
        raise ValueError(f"AssetPackManifest provenance is incomplete: {missing_provenance}")

    base_asset = document.get("base_asset")
    components = document.get("components")
    if not isinstance(base_asset, dict) or not isinstance(components, list):
        raise ValueError("AssetPackManifest requires base_asset and components.")

    _seal_asset(base_asset, build_root)
    for component in components:
        if not isinstance(component, dict):
            raise ValueError("Each component must be an object.")
        _seal_asset(component, build_root)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    print(f"Sealed asset pack manifest: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
