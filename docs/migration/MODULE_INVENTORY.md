# Module Inventory

## Source Footprint

| Domain | Python files | LOC | Share of source LOC | Current responsibility |
|---|---:|---:|---:|---|
| `_internal` | 2 | 320 | 2.3% | Shared Blender executable resolution and subprocess runner. |
| `annall` | 7 | 896 | 6.3% | Build/session telemetry port plus null, file, and SQLite adapters. |
| `bridges` | 10 | 2,419 | 17.0% | Core dispatch and CLI, REST, MCP, and agent-facing bridges. |
| `brunhand` | 19 | 5,340 | 37.6% | Remote VRoid Studio GUI automation client and daemon. |
| `config.py` | 1 | 152 | 1.1% | Defaults, user overrides, environment overrides, and path resolution. |
| `forge` | 5 | 2,074 | 14.6% | Blender build orchestration, VRM conversion, texture work, and export. |
| `gate` | 4 | 845 | 5.9% | VRM parsing and platform compliance reports. |
| `hoard` | 5 | 768 | 5.4% | Asset catalog, path security, resolution, and bootstrap download. |
| `loom` | 5 | 718 | 5.0% | Parametric avatar schema, loading, and semantic validation. |
| `oracle_eye` | 3 | 670 | 4.7% | Headless preview rendering and external render registration. |
| package root | 1 | 16 | 0.1% | Version/package initialization. |
| **Total** | **62** | **14,218** | **100%** | |

## Core Build Domains

### Loom — `src/seidr_smidja/loom`

**Observed responsibility**

- Pydantic `AvatarSpec` and nested body, face, hair, outfit, expression, and
  metadata models.
- YAML/JSON loading.
- Structural and semantic validation.
- Known blendshape validation using `data/loom/known_blendshapes.yaml`.
- Optional Annáll event emission.

**Useful behavior**

- Frozen models and bounded validation ranges.
- Safe YAML loading and filesystem error translation.
- Clear schema/loader/validator split.

**Mismatch with target**

`AvatarSpec` describes a parametrized variant of one base asset. It cannot
represent a canonical multiview character package with image references,
measurements, landmarks, material definitions, hair construction, outfit
construction, expression sheets, viseme sheets, and provenance.

**Preliminary disposition:** `REPLACE`, while reusing validation patterns.

### Hoard — `src/seidr_smidja/hoard`

**Observed responsibility**

- `HoardPort`, `AssetMeta`, and filtering types.
- Local YAML catalog resolution.
- Containment/path traversal checks.
- Optional download/bootstrap with checksum verification.
- Asset listing and optional Annáll events.

**Useful behavior**

- Explicit asset IDs rather than arbitrary paths.
- Catalog validation and path containment.
- Checksum-aware bootstrap flow.

**Gaps**

- Catalog entries may claim `cached: true` while binaries are absent from Git.
- Several checksums are null.
- Asset provenance is not complete enough for Juana.
- Catalog scope mixes test samples and character-specific upstream assets.

**Preliminary disposition:** `ADAPT` into a provenance-first base-asset catalog.

### Forge — `src/seidr_smidja/forge`

**Observed responsibility**

- Serialize a validated spec to temporary JSON.
- Run Blender headlessly through the shared runner.
- Import VRM, FBX, OBJ, or glTF bases.
- Modify selected textures/materials and height.
- Configure VRM 1.0 humanoid mappings, expressions, metadata, first-person,
  look-at, and export.
- Validate that export produced a readable VRM container.

**Useful behavior**

- Real headless VRM export path.
- Explicit exit codes and captured process output.
- Guaranteed temporary-directory cleanup.
- Existing expression, viseme, blink, and look-at mappings.

**Risks**

- `build_avatar.py` is 1,462 lines and combines import, material processing,
  base-specific rig mappings, expression mappings, metadata, export, and
  validation.
- TurboSquid-specific bone and shape-key knowledge is hardcoded globally.
- Only a subset of schema parameters is applied.
- Blender/Python dependencies are partly environment-provided rather than
  represented by a precise adapter contract.

**Preliminary disposition:** `ADAPT` heavily behind base-model adapters.

### Shared Blender runner — `src/seidr_smidja/_internal/blender_runner.py`

**Observed responsibility**

- Resolve Blender from explicit config, environment, PATH, and platform hints.
- Invoke Blender with a Python script and `--` arguments.
- Stream/capture output, enforce timeout, terminate process groups, and return a
  typed result.

**Preliminary disposition:** `RETAIN` after characterization and rename.

### Oracle Eye — `src/seidr_smidja/oracle_eye`

**Observed responsibility**

- Invoke Blender in a separate process to render standard views.
- Return per-view PNG paths and structured errors.
- Support registration of externally captured renders for Brúarhönd.

**Useful behavior**

- Build and render are separate subprocesses.
- Rendering failure is represented explicitly.
- Standard view enumeration exists.

**Target change**

Expand and rename the renderer around body, head, expression, and viseme
reference comparisons. External GUI render registration is unnecessary after
Brúarhönd removal.

**Preliminary disposition:** `ADAPT` and rename.

### Gate — `src/seidr_smidja/gate`

**Observed responsibility**

- Parse GLB/VRM container JSON without Blender.
- Extract compliance data.
- Load rule files and produce structured per-target violations.
- Evaluate VRChat and VTube Studio targets.

**Useful behavior**

- Lightweight post-export validation.
- Typed reports and violations.
- Runtime-loaded rule data.

**Target change**

Add a first-class Three.js/web target and make VRChat/VTube rules optional rather
than default product requirements.

**Preliminary disposition:** `ADAPT`.

## Orchestration And Interfaces

### Core dispatch — `src/seidr_smidja/bridges/core`

The canonical `dispatch()` path validates the spec, resolves the base, builds the
VRM, renders previews, checks compliance, logs outcomes, and always returns a
structured `BuildResponse`.

This is a useful application-flow skeleton, but the same module also contains
Brúarhönd dispatch and imports nearly every domain directly. It should be split
into a narrow build application service and separate optional operations.

**Preliminary disposition:** `ADAPT`.

### CLI bridge — `src/seidr_smidja/bridges/runstafr`

The Click CLI is the only target interface that remains directly relevant. It
also currently contains all Brúarhönd subcommands and legacy naming.

**Preliminary disposition:** `ADAPT`; preserve CLI UX patterns, replace command
surface and package naming.

### REST bridge — `src/seidr_smidja/bridges/straumur`

FastAPI exposes build, inspect, asset listing, session lookup, and Brúarhönd
dispatch. The target product is a local build-time CLI and does not require a
hosted API.

**Preliminary disposition:** `REMOVE_LATER` after the CLI no longer imports or
tests REST concerns.

### MCP bridge — `src/seidr_smidja/bridges/mjoll`

The MCP server exposes build/inspect plus Brúarhönd tools. Juana's avatar runtime
must contain zero MCP or AI control behavior.

**Preliminary disposition:** `REMOVE_LATER`.

### Agent skill manifests — `src/seidr_smidja/bridges/skills`

Upstream Claude Code, Hermes, and OpenClaw manifests are superseded by the pinned
`kathy-sdd-kit` and project-local entrypoints.

**Preliminary disposition:** `REMOVE_LATER`.

## Cross-Cutting Domains

### Annáll — `src/seidr_smidja/annall`

Annáll supplies a clean port but is used across Loom, Hoard, Forge, Oracle Eye,
Gate, bridges, and Brúarhönd. It records sessions and events to null, JSONL/file,
or SQLite adapters.

For a one-off reproducible CLI, durable queryable session storage is not a core
requirement. A build manifest and report are required. Keep the null seam during
migration; replace the wider telemetry subsystem after output-manifest behavior
exists.

**Preliminary disposition:** `ADAPT/REPLACE`.

### Configuration — `src/seidr_smidja/config.py`

The loader merges defaults, optional user YAML, and environment overrides. This
pattern is useful, but the current schema contains substantial Brúarhönd, REST,
VRChat, VTube, and Annáll configuration.

**Preliminary disposition:** `ADAPT` to the narrower CLI.

### Brúarhönd — `src/seidr_smidja/brunhand`

Brúarhönd is a complete remote GUI automation product:

- HTTP client and session abstraction;
- screenshot/oracle channel;
- FastAPI daemon;
- bearer-token middleware;
- capability probing;
- mouse, keyboard, window, and VRoid operations;
- platform-specific runtime shims.

It accounts for 5,340 source LOC and 203 collected tests. It is functionally
substantial but outside the approved Juana pipeline. Remove it only after core
dispatch, CLI, config, Annáll, and Oracle Eye no longer import it.

**Preliminary disposition:** `REMOVE_LATER`.

## Supporting Repository Areas

| Area | Current role | Preliminary disposition |
|---|---|---|
| `config/` | Process defaults and documentation. | `ADAPT` |
| `data/loom/` | Known expression/blendshape names. | `ADAPT` into expression contract data. |
| `data/hoard/` | Base asset catalog. | `ADAPT`; provenance and checksums mandatory. |
| `data/gate/` | VRChat/VTube rule packs. | `ADAPT`; optional legacy targets. |
| `examples/` | Parametric AvatarSpec samples. | `REPLACE` with character-package fixtures. |
| `tools/bootstrap_hoard.py` | Asset bootstrap wrapper. | `ADAPT` or retain as optional fixture bootstrap. |
| `tools/verify_install.py` | Environment verification. | `ADAPT` for Blender, add-on, Node, and package checks. |
| `tools/brunhand_daemon.py` | Remote GUI daemon launcher. | `REMOVE_LATER` |
| `tools/verify_brunhand.py` | Remote GUI verification. | `REMOVE_LATER` |
| `scripts/fix_memory_thread_safety.py` | Patches files under `~/.hermes`; unrelated to VRM creation. | `REMOVE_LATER` with no replacement. |
| `docs/DECISIONS/` | Historical upstream ADR-like decisions. | Archive relevant provenance; supersede product decisions with new ADRs. |
| `logs/` and task documents | Upstream process memory and narrative history. | Archive externally or remove after extracting facts. |
| Root images | Upstream branding/illustration assets. | `UNKNOWN` pending provenance; not required by CLI. |

## Test Distribution

| Test area | Collected tests | Migration meaning |
|---|---:|---|
| Brúarhönd | 203 | Delete with feature only after unrelated characterization is preserved. |
| Loom | 62 | Replace with CharacterDesignPackage and compiler contract tests. |
| Bridges | 52 | Preserve CLI/core behavior; retire MCP/REST tests with those bridges. |
| Annáll | 48 | Keep only output/report behavior needed by new build pipeline. |
| Root hardening/smoke | 45 | Reclassify by retained behavior before deleting old namespace. |
| Hoard | 43 | Preserve path security, catalog validation, and checksum behavior. |
| Gate | 33 | Preserve VRM parsing/reporting; add Three.js target tests. |
| Blender runner | 5 | Preserve as direct characterization coverage. |
| **Total** | **491** | |

## Structural Conclusion

The repository does not require a big-bang rewrite. The reusable center is
small enough to migrate through explicit seams, while the largest out-of-scope
feature is lateral. The safe strategy is to build a new canonical design and
compiler layer, migrate the Blender/asset/render/validation capabilities behind
new ports, switch the CLI, and only then delete the inherited bridges and
Brúarhönd tree.
