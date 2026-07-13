# Upstream Baseline

## Snapshot Identity

| Item | Value |
|---|---|
| Current repository | `kathesama/vrm-ia-maker` |
| Current default branch | `development` |
| Baseline after SDD-kit adoption | `7b9a2a704e8f8ddc3c7ec7acbd32b9eb1fe0a17d` |
| Upstream repository | `hrabanazviking/Seidr-Smidja` |
| Imported upstream branch | `development` |
| Imported upstream commit | `16cda2e7e65d383c0022b52b461aa2d86b07ee33` |
| SDD framework | `kathesama/kathy-sdd-kit` `0.6.0` |
| Pinned SDD-kit commit | `2164c5e83a70d88fbb7933a433193a019d8e4cf2` |
| Inventory ticket | `BOOTSTRAP-2` |
| Inventory date | 2026-07-13 |

The repository was detached from its original GitHub fork network before this
inventory. Git history and attribution remain present; detachment does not alter
license obligations.

## Package Metadata At Baseline

| Field | Observed value |
|---|---|
| Distribution name | `seidr-smidja` |
| Distribution version | `0.1.0.dev0` |
| Python requirement | `>=3.10` |
| Console entrypoint | `seidr = seidr_smidja.bridges.runstafr.cli:main` |
| Declared product description | Agent-only headless VRM avatar forge |
| Declared license in `pyproject.toml` | MIT |
| Repository `LICENSE` | Apache License 2.0 |
| Repository `NOTICE` | Apache-2.0 notice and upstream project attribution |

The license metadata is contradictory. Until corrected, derived source must be
handled conservatively under Apache-2.0 while preserving `LICENSE`, `NOTICE`, and
relevant attribution.

## Tracked Footprint

The clean snapshot was produced with `git archive origin/development`, not by
copying a working tree after installation or tests.

| Metric | Value |
|---|---:|
| Tracked entries | 218, including the `.sdd-kit` gitlink |
| Files materialized by `git archive` | 217 |
| Materialized tracked size | 3,585,117 bytes |
| Python source files under `src/seidr_smidja` | 62 |
| Python source LOC | 14,218 |
| Nonblank/non-comment source lines | 11,296 |
| Pytest files | 41 |
| Tests collected | 491 |
| Root image files | 5 |
| Root image bytes | 1,890,487 |
| Markdown files | 74 |

The repository is documentation- and history-heavy. Root images alone account for
more than half of the materialized tracked bytes. That is not inherently wrong,
but those files are not required by the target CLI and need provenance review
before reuse.

## Snapshot Method

The baseline evidence was captured in an ephemeral GitHub Actions workflow that:

1. fetched `origin/development`;
2. recorded `git ls-tree -r --name-only origin/development`;
3. created `git archive --format=tar.gz origin/development`;
4. installed the package with development dependencies on Python 3.11;
5. ran Ruff, mypy, pytest collection, and pytest execution independently;
6. uploaded structured evidence as a short-lived workflow artifact.

The diagnostic PR was closed without merge and its temporary branch was reset to
the baseline. The workflow itself is not part of this migration diff.

## Confirmed Contradictions And Drift

### 1. License metadata

- `LICENSE` and `NOTICE` state Apache-2.0.
- `LEGAL-NOTICE.md` also says Apache-2.0.
- `pyproject.toml` says MIT.

This must be corrected before rebranding or distributing a repackaged tool.

### 2. Interface documentation versus implementation

Historical interface documents describe a smaller Phase-0/Genesis surface. The
current code includes additional CLI commands, versioned REST endpoints,
Brúarhönd dispatch, external render registration, and hardening behavior. Current
implementation and tests take precedence over older conceptual signatures.

### 3. Parametric schema versus builder support

The schema declares parameters such as:

- head, upper-body, lower-body, arm, and leg scaling;
- eye size, nose scale, and mouth width;
- hair style, length, and physics;
- outfit layers, meshes, colors, and visibility.

The Blender build script clearly consumes height, material colors, expression
weights, metadata, humanoid mappings, first-person data, look-at data, and texture
limits. The remaining declared parameters are not visibly applied by the builder
at this baseline. They must not be advertised as functioning until implemented
and tested through base adapters.

### 4. Optional-interface narrative versus package dependencies

Code comments describe FastAPI and MCP as optional or gracefully degradable, but
`pyproject.toml` installs FastAPI, Uvicorn, MCP, and HTTPX as base dependencies.
The target CLI should move non-CLI surfaces to extras or remove them.

### 5. CI status versus test status

The standard CI job stops on Ruff before mypy or pytest. Fresh independent
execution proves that pytest is green while lint and strict typing are not. A red
CI badge therefore does not mean the 491-test suite fails.

### 6. Target mismatch

Gate rules are centered on VRChat and VTube Studio. Juana needs a web/Three.js
contract: VRM 1.0 loadability, required humanoid bones, expression manager,
visemes, look-at, spring bones, texture budgets, and browser-safe assets. Existing
rules are reusable references but not the future default target.

## Frozen Baseline Rule

The commits above are historical anchors. Future migration documents may refine
interpretation, but they must not silently rewrite the facts recorded here. If a
new observation contradicts this inventory, add a dated amendment with fresh
evidence.
