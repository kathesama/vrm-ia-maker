# Disposition Matrix

These are proposed migration decisions, not deletion authorization. `REMOVE_LATER`
requires the listed dependency and evidence gates.

## Product And Domain Components

| Component | Current role | Decision | Behavior to preserve / target | Prerequisite before retirement or migration |
|---|---|---|---|---|
| `loom/schema.py` | Parametric `AvatarSpec` | `REPLACE` | Introduce canonical `CharacterDesignPackage` and separate `CompiledCharacterSpec`. | New schemas validated with fixtures; no build path reads old spec directly. |
| `loom/loader.py` | Safe YAML/JSON loading | `ADAPT` | Preserve safe loading, path errors, and typed validation. | New package loader has characterization parity. |
| `loom/validator.py` | Semantic checks | `ADAPT` | Move relevant checks to design and compilation validators. | Acceptance/error mapping exists for new schemas. |
| `data/loom/known_blendshapes.yaml` | Known expression names | `ADAPT` | Become versioned runtime expression/viseme contract. | Three.js contract and base-adapter mapping defined. |
| `hoard/port.py` | Asset lookup abstraction | `RETAIN` concept | Narrow asset catalog port with mandatory provenance/checksum. | New metadata model implemented. |
| `hoard/local.py` | Local catalog, filtering, path security | `ADAPT` | Preserve containment and catalog validation. | Character/base catalog tests green. |
| `hoard/bootstrap.py` | Remote fixture download | `ADAPT` | Optional, checksum-pinned bootstrap for redistributable fixtures only. | Asset policy and trusted source list accepted. |
| `data/hoard/catalog.yaml` | Upstream asset registry | `REPLACE` | New catalog with owned/approved bases and complete provenance. | Every retained entry has source, license, checksum, and redistribution decision. |
| `_internal/blender_runner.py` | Shared subprocess boundary | `RETAIN` | Preserve executable precedence, timeout, termination, output streaming/capture. | Characterization tests copied to new namespace. |
| `forge/runner.py` | Spec serialization and Blender orchestration | `ADAPT` | Accept `CompiledCharacterSpec` through a Forge port. | Compiler output schema stable. |
| `forge/scripts/build_avatar.py` | Monolithic Blender converter/exporter | `ADAPT` | Split generic VRM export from base-specific operations. | Base adapter API and golden fixture exist. |
| `forge/scripts/tint_textures.py` | Standalone HSV texture manipulation | `ADAPT` | Move under explicit material operations if still needed. | Verify it is used by target base; otherwise delete. |
| `oracle_eye/eye.py` | Preview rendering | `ADAPT` | Rename and expand to body/head/expression/viseme render sets. | New render report and comparison contract. |
| `oracle_eye/scripts/render_avatar.py` | Blender-side renderer | `ADAPT` | Preserve deterministic camera/render invocation. | Reference-view tests and fixture outputs. |
| External render registration | Registers Brúarhönd screenshots | `REMOVE_LATER` | No target equivalent. | Brúarhönd detached from renderer. |
| `gate/vrm_reader.py` | GLB/VRM metadata extraction | `RETAIN`/`ADAPT` | Preserve Blender-free parsing; extend VRM 1.0 fields needed by Three.js. | Regression fixtures for VRM 0.x and 1.0. |
| `gate/gate.py` and models | Compliance engine/report | `ADAPT` | Three.js/web target becomes primary; violations remain structured data. | New rule profile and Node validation cross-check. |
| VRChat rule pack | Platform-specific compliance | `OUT_OF_SCOPE` by default | Optional legacy profile only if useful. | Default CLI no longer assumes VRChat. |
| VTube Studio rule pack | Platform-specific compliance | `OUT_OF_SCOPE` by default | Optional legacy profile only if useful. | Default CLI no longer assumes VTube Studio. |

## Application And Interface Components

| Component | Current role | Decision | Behavior to preserve / target | Prerequisite |
|---|---|---|---|---|
| `bridges/core/dispatch.py` build flow | Fixed five-stage orchestration | `ADAPT` | New application service with explicit stage results and deterministic artifact manifest. | New design/compiler/ports exist. |
| `bridges/core` Brúarhönd dispatch | Remote primitive orchestration | `REMOVE_LATER` | None. | Split from build use case; zero imports from retained path. |
| `bridges/runstafr/cli.py` core commands | Click CLI | `ADAPT` | Retain thin CLI and JSON-capable reporting under new executable. | New application use cases ready. |
| `bridges/runstafr/cli.py` Brúarhönd commands | Remote GUI CLI | `REMOVE_LATER` | None. | New CLI module no longer imports Brúarhönd. |
| `bridges/straumur` | REST API | `REMOVE_LATER` | Preserve no hosted transport. | CLI parity confirmed; dependencies removed. |
| `bridges/mjoll` | MCP server | `REMOVE_LATER` | None. | Build/inspect available through CLI; MCP dependency removed. |
| `bridges/skills` | Upstream agent manifests | `REMOVE_LATER` | Use project-local SDD skills from `.sdd-kit`. | Confirm no release packaging expects manifests. |
| Package name `seidr-smidja` | Distribution identity | `REPLACE` | `vrm-ia-maker` and chosen CLI name. | License/NOTICE update and compatibility decision. |
| `config.py` | Config merge and paths | `ADAPT` | Retain defaults/user/env precedence for needed settings only. | New typed config schema. |

## Cross-Cutting And Out-Of-Scope Components

| Component | Current role | Decision | Rationale / target | Prerequisite |
|---|---|---|---|---|
| `annall/port.py` | Telemetry abstraction | `ADAPT` temporarily | Keep Null adapter seam during migration. | Build report model exists. |
| Annáll SQLite/file adapters | Queryable historical sessions | `REPLACE`/`REMOVE_LATER` | One build should emit manifest/report files instead. | New artifact evidence covers required diagnostics. |
| Entire `brunhand/` tree | Remote VRoid GUI automation | `REMOVE_LATER` | Outside build-time CLI and Three.js runtime. | Core, CLI, config, Annáll, Oracle Eye imports detached. |
| `tools/brunhand_daemon.py` | Daemon launcher | `REMOVE_LATER` | Removed with Brúarhönd. | Brúarhönd deletion gate. |
| `tools/verify_brunhand.py` | Remote verification | `REMOVE_LATER` | Removed with Brúarhönd. | Brúarhönd deletion gate. |
| `scripts/fix_memory_thread_safety.py` | Patches `~/.hermes` files | `REMOVE_LATER` | Unrelated to VRM creation and unsafe as product utility. | None beyond attribution/history check. |
| `tools/verify_install.py` | Environment diagnostics | `ADAPT` | Verify Python, Blender, VRM add-on, Node validator, and asset catalog. | Target dependency list stable. |
| `tools/bootstrap_hoard.py` | Bootstrap wrapper | `ADAPT` | Rename and limit to approved fixture assets. | New catalog. |

## Documentation And Repository Material

| Component | Decision | Notes |
|---|---|---|
| `docs/DECISIONS/` | `ADAPT/ARCHIVE` | Keep provenance for reusable subprocess/port choices; supersede product architecture with new ADRs. |
| `docs/features/brunhand/` | `REMOVE_LATER` | Archive outside the active product docs if historical retention is desired. |
| Mythic philosophy/system vision documents | `OUT_OF_SCOPE` | Not an engineering source of truth for Juana avatar maker. Preserve attribution before removal. |
| Root task files and `logs/` | `REMOVE_LATER` | Historical process evidence, not active product documentation. |
| Five root JPEG/JPEG assets | `UNKNOWN` | Provenance and product relevance not explicit; do not reuse until resolved. |
| `README.md` | `REPLACE` | New product scope, setup, CLI, licensing, and artifact contract. |
| `NOTICE`, `LICENSE`, `LEGAL-NOTICE.md` | `ADAPT` | Preserve Apache attribution; update project identity without erasing upstream notices. |
| `pyproject.toml` | `REPLACE/ADAPT` | Rename package, correct license, minimize dependencies, update entrypoint. |

## Test Disposition

| Tests | Decision | Required action |
|---|---|---|
| `_internal/test_blender_runner.py` | `RETAIN` | Move with runner; add timeout/process/output cases if missing. |
| Loom tests | `REPLACE/ADAPT` | Convert valuable validation cases to design/compiler schemas. |
| Hoard tests | `RETAIN/ADAPT` | Preserve path, checksum, catalog, and trusted-source behavior. |
| Forge/Oracle root hardening tests | `RETAIN/ADAPT` | Repoint to ports and compiled spec. |
| Gate tests | `RETAIN/ADAPT` | Add Three.js/VRM 1.0 fixture expectations. |
| Core/CLI tests | `RETAIN/ADAPT` | Preserve selected exit/JSON behavior; drop old names deliberately. |
| REST and MCP tests | `REMOVE_LATER` | Delete with interfaces after CLI cutover. |
| Brúarhönd tests | `REMOVE_LATER` | Delete as one bounded feature after import graph is clean. |
| Annáll adapter tests | `REPLACE/REMOVE_LATER` | Preserve only build-report evidence requirements. |

## Deletion Gate

A component marked `REMOVE_LATER` may be deleted only when:

1. no retained source imports it;
2. no target CLI command exposes it;
3. its required behavior is either explicitly out of scope or covered by a
   replacement;
4. relevant characterization evidence has been migrated;
5. dependency and configuration entries are removed in the same change;
6. documentation and license attribution are updated;
7. the retained suite passes without skip inflation or broad exclusions.
