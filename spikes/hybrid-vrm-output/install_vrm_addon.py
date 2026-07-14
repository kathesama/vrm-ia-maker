"""Install and enable the VRM Add-on for Blender in a headless Blender profile."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import addon_utils
import bpy


def _arguments() -> list[str]:
    try:
        separator = sys.argv.index("--")
    except ValueError as exc:
        raise SystemExit("Expected '-- <addon.zip>'") from exc
    return sys.argv[separator + 1 :]


def main() -> None:
    arguments = _arguments()
    if len(arguments) != 1:
        raise SystemExit("Usage: blender --background --python install_vrm_addon.py -- <addon.zip>")

    archive = Path(arguments[0]).resolve()
    if not archive.is_file():
        raise FileNotFoundError(archive)

    install_result = bpy.ops.preferences.addon_install(
        filepath=str(archive),
        overwrite=True,
    )
    if "FINISHED" not in install_result:
        raise RuntimeError(f"VRM add-on installation failed: {install_result}")

    addon_utils.modules(refresh=True)
    candidates = []
    for module in addon_utils.modules():
        module_name = getattr(module, "__name__", "")
        display_name = str(getattr(module, "bl_info", {}).get("name", ""))
        if module_name == "io_scene_vrm" or "VRM" in display_name.upper():
            candidates.append(module_name)

    if "io_scene_vrm" not in candidates:
        candidates.insert(0, "io_scene_vrm")

    enabled = None
    errors = []
    for module_name in dict.fromkeys(candidates):
        try:
            addon_utils.enable(module_name, default_set=True, persistent=True)
            importlib.import_module(module_name)
            enabled = module_name
            break
        except Exception as exc:  # noqa: BLE001 - Blender reports heterogeneous add-on errors.
            errors.append(f"{module_name}: {exc}")

    if enabled is None:
        raise RuntimeError("Could not enable the VRM add-on. " + " | ".join(errors))

    bpy.ops.wm.save_userpref()
    print(f"Installed and enabled VRM add-on module: {enabled}")


if __name__ == "__main__":
    main()
