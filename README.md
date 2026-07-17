# VRM IA Maker

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue)](pyproject.toml)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-blue)](LICENSE)

VRM IA Maker is a build-time command-line tool for turning a canonical character design package into a validated VRM avatar that can be loaded and controlled deterministically from Three.js.

The project is being migrated from the Seiðr-Smiðja codebase. The useful Blender, VRM, rendering, asset, and validation capabilities are being retained behind narrower interfaces while agent transports and remote GUI automation are removed.

## Product boundary

VRM IA Maker participates in avatar creation and release. It is not part of Juana's conversational runtime.

```text
Character Design Package
        |
        v
validation and normalization
        |
        v
Base Model Adapter
        |
        v
Compiled Character Specification
        |
        v
Blender Headless Forge
        |
        v
VRM 1.0 + renders + manifest + reports
        |
        v
Three.js compatibility validation
```

Three.js owns runtime behavior such as loading, blinking, look-at, expressions, visemes, lip sync, animation, and rendering. No LLM, MCP server, planner, or autonomous decision logic belongs in the avatar runtime layer.

## Canonical input

The target input is a versioned character design package, not a single reference image.

```text
characters/juana/
├── character.yaml
├── measurements.yaml
├── palette.yaml
├── materials.yaml
├── LICENSE.md
├── views/
├── face/
├── expressions/
├── visemes/
├── hair/
├── outfit/
└── landmarks/
```

A complete package describes multiview references, measurements, landmarks, materials, expressions, visemes, hair, outfit, and provenance. The package is the source of truth. Compiled specifications, Blender scenes, renders, manifests, and VRM files are generated artifacts.

## Expected outputs

A successful build is expected to produce:

```text
dist/juana/
├── juana.vrm
├── manifest.json
├── build-report.json
├── compliance-report.json
├── visual-comparison-report.json
└── renders/
```

The project does not currently promise automatic high-quality 3D reconstruction from a single illustration. A supported, legally usable base model and a versioned adapter remain necessary for reproducible builds.

## Current status

The repository is in an evidence-driven migration phase.

Already established:

- the inherited baseline and its upstream provenance;
- the reusable build path: Loom to Hoard to Forge to renderer to validation;
- the Blender subprocess runner as a retained seam;
- a safe, replacement-before-deletion pruning sequence;
- the separation between tool licensing and generated-avatar licensing;
- a pinned SDD workflow through `kathy-sdd-kit`.

### Provisional Juana 3D checkpoint

GH-22 adds the first concrete human Juana bust tracer bullet. It pins Blender,
MPFB, the MakeHuman base, and every CC0 asset; authors an editable scene with a
rig, separate eyes, a functional jaw, expression morphs, asymmetric hair, and
the visible outfit; exports a provisional GLB; and produces five deterministic
reference comparisons.

Run the offline route from the repository root:

```bash
python tools/juana_bust/build_preview.py
```

The outputs remain under ignored `build/juana-bust-preview/` paths and are
explicitly not the final VRM. See
[`tools/juana_bust/README.md`](tools/juana_bust/README.md) for the input lock,
validation sequence, outputs, and visual-review boundary.

Planned next:

1. characterize retained Blender, asset, render, VRM-reader, and CLI behavior;
2. introduce the `vrm_ia_maker` namespace and explicit ports;
3. implement `CharacterDesignPackage` validation and normalization;
4. add versioned base-model adapters and `CompiledCharacterSpec`;
5. migrate useful forge, render, and validation capabilities;
6. cut over to the final `vrm-maker` CLI;
7. remove MCP, REST, Brúarhönd, and the old namespace after their callers are gone.

See [`docs/migration/README.md`](docs/migration/README.md) for the migration evidence and [`docs/migration/PRUNING_SEQUENCE.md`](docs/migration/PRUNING_SEQUENCE.md) for the dependency-aware sequence.

## Development setup

Clone with submodules and initialize the local SDD workspace:

```bash
git clone --recurse-submodules https://github.com/kathesama/vrm-ia-maker.git
cd vrm-ia-maker
git checkout development
sh tools/setup_sdd_workspace.sh
sh tools/check_sdd_workspace.sh
```

Install the Python project with development dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run the fast functional suite:

```bash
python -m pytest --tb=short -q
```

Blender integration tests and live VRoid-host tests remain separate opt-in suites.

## Temporary legacy CLI

The installed distribution is named `vrm-ia-maker`, but the executable remains `seidr` while behavior is characterized and migrated.

```bash
seidr --version
seidr version
seidr build examples/spec_minimal.yaml --out ./out/
seidr inspect ./out/avatar.vrm
seidr list-assets
```

The final command surface will use `vrm-maker`. The legacy command is a compatibility surface, not the target product identity.

## Quality baseline

The inherited baseline has a green non-Blender functional suite but known lint and type debt. CI runs Ruff, mypy, pytest, and coverage independently so one category cannot hide the result of another.

The migration policy is:

- inherited debt remains visible;
- new or modified code must not add debt;
- cleanup is focused on retained code;
- code scheduled for deletion is not polished merely to improve vanity metrics.

## Asset policy

Every model, texture, garment, hairstyle, font, accessory, and reference package must carry explicit source, author, license, redistribution terms, and checksum before it can participate in a releasable build.

See [`ASSET_POLICY.md`](ASSET_POLICY.md). Third-party software notices are recorded in [`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md).

## Licensing

The source code in this repository is distributed under the Apache License 2.0. It contains code derived from Seiðr-Smiðja; the original attribution is preserved in [`NOTICE`](NOTICE).

The license of the tool does not automatically apply to generated avatars. The license of a generated `.vrm` depends on the character design and every model, mesh, texture, garment, hairstyle, and accessory used to produce it.

## Upstream provenance

This project contains software derived from:

```text
Project: Seiðr-Smiðja
Upstream: https://github.com/hrabanazviking/Seidr-Smidja
Imported baseline: 16cda2e7e65d383c0022b52b461aa2d86b07ee33
License: Apache-2.0
```

The current project is independent and is not affiliated with or endorsed by the original author.

## Development workflow

Repository changes follow the specification-driven workflow documented in
[`docs/development/sdd-workflow.md`](docs/development/sdd-workflow.md). Ticket
evidence remains local under `.ai-specs/changes/{TICKET}/`. The standing
approval rules and closed escalation conditions are recorded in
[`docs/DELEGATED_EXECUTION_POLICY.md`](docs/DELEGATED_EXECUTION_POLICY.md).
