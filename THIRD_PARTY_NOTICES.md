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

The following tools retain their own licenses:

- Blender
- VRM Add-on for Blender
- Git
- GitHub Actions

Operators are responsible for installing compatible versions and complying with
the terms distributed by each project.

### GH-22 provisional human-base toolchain

The reproducible GH-22 visual checkpoint uses local, ignored copies of:

- Blender 4.2.0, GPL-3.0-or-later;
- MPFB 2.0.16, GPL-3.0-or-later;
- MakeHuman system assets, CC0-1.0.

The MakeHuman material used by this checkpoint includes the hm08 base mesh,
default rig and weights, young African female skin, eye placement, long01 and
short01 hair, eyebrow002, eyelashes03, female_elegantsuit01, and
female_casualsuit02. Repository-authored edits remain provisional and do not
change the source asset licenses.

The exact upstream URLs, versions, local paths, byte lengths, SHA-256 digests,
and per-artifact licenses are recorded in
`tools/juana_bust/toolchain-lock.json`. These binary and media inputs remain
under ignored `build/local-toolchain/` paths and are not redistributed by the
repository.

## Python dependencies

Runtime and development dependencies are installed from package indexes and are not vendored in this repository. The authoritative license for each dependency is the license shipped with that dependency's distribution.

Current direct dependencies include:

- Pydantic
- PyYAML
- Pillow
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

Pillow is a direct local dependency used to validate PNG dimensions and extract exact
reference panels. It is not used for artistic or identity decisions.

The OpenAI Python SDK is available only through the optional `authoring-openai` extra.
It supports explicit build-time image-authoring requests and is not imported by sealed
package validation, Blender production, Three.js consumption, or avatar runtime code.
The SDK, hosted service, and generated outputs remain subject to their applicable
third-party terms; this notice does not grant rights to any input or output image.

Several dependencies support inherited features that are scheduled for removal or conversion to optional extras. Their presence in the current package metadata does not make them part of the target architecture.

## Three.js validation dependencies

The production assembly compiler pins Three.js 0.183.2 under the MIT License.
GH-22 uses its `GLTFLoader` from Node to inspect the provisional GLB structure.
The dependency is installed from npm and is not vendored into the Python
runtime.

The retained SPIKE-1 and SPIKE-2 evidence pins `@pixiv/three-vrm` 3.5.1 and
Three.js 0.183.2 in the respective spike packages. GH-22 exports a provisional
GLB rather than a VRM and therefore does not claim production
`@pixiv/three-vrm` validation.

## Models, textures, and generated avatars

Model and media assets are governed separately from software source code. A marketplace listing, a `free` label, or a catalog entry is not sufficient evidence of redistribution rights.

No model, texture, garment, hairstyle, font, accessory, or generated VRM may be treated as releasable until it satisfies `ASSET_POLICY.md`.
