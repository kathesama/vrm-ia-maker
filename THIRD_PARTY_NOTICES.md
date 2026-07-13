# Third-Party Notices

This document records third-party software and development material relevant to VRM IA Maker. It does not replace the license text shipped by any dependency or asset.

## Derived source code

### Seiðr-Smiðja

- Purpose: inherited VRM forge, Blender runner, rendering, validation, asset, CLI, and related migration source
- Copyright: 2026 Volmarr Wyrd
- License: Apache License 2.0
- Repository: `https://github.com/hrabanazviking/Seidr-Smidja`
- Imported baseline: `16cda2e7e65d383c0022b52b461aa2d86b07ee33`

The relevant upstream attribution is preserved in `NOTICE`. Modified files remain subject to the Apache License 2.0 redistribution conditions.

## Development submodule

### kathy-sdd-kit

- Purpose: specification-driven planning, approval, QA, review, and PR workflow
- Repository: `https://github.com/kathesama/kathy-sdd-kit`
- Pinned revision: `2164c5e83a70d88fbb7933a433193a019d8e4cf2`
- Runtime status: development-only; not imported into the Python runtime package

The submodule retains its own files, notices, and per-file source attributions. VRM IA Maker does not relicense the submodule or any material referenced by it.

## External build tools

The following tools are not vendored in this repository and retain their own licenses:

- Blender
- VRM Add-on for Blender
- Git
- GitHub Actions

Operators are responsible for installing compatible versions and complying with the terms distributed by each project.

## Python dependencies

Runtime and development dependencies are installed from package indexes and are not vendored in this repository. The authoritative license for each dependency is the license shipped with that dependency's distribution.

Current direct dependencies include:

- Pydantic
- PyYAML
- Click
- FastAPI
- Uvicorn
- MCP Python SDK
- HTTPX
- pytest
- pytest-asyncio
- pytest-cov
- Ruff
- mypy
- respx

Several dependencies support inherited features that are scheduled for removal or conversion to optional extras. Their presence in the current package metadata does not make them part of the target architecture.

## Three.js validation dependencies

Three.js and `@pixiv/three-vrm` are planned for the future compatibility validator. They are not yet vendored or part of the current Python runtime. Their notices must be added when the Node-based validator is introduced.

## Models, textures, and generated avatars

Model and media assets are governed separately from software source code. A marketplace listing, a `free` label, or a catalog entry is not sufficient evidence of redistribution rights.

No model, texture, garment, hairstyle, font, accessory, or generated VRM may be treated as releasable until it satisfies `ASSET_POLICY.md`.
