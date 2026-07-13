# Interface Inventory

This inventory distinguishes observed implementation from historical interface
documents. The command and endpoint lists below come from the tracked code at the
pinned baseline.

## Python Distribution Interface

```toml
[project.scripts]
seidr = "seidr_smidja.bridges.runstafr.cli:main"
```

The package name, executable name, help text, and JSON fields are all inherited
and require a controlled compatibility decision during rebranding.

## CLI Surface

### Core commands

| Command | Principal input | Output / side effects | Observed exit behavior | Target decision |
|---|---|---|---|---|
| `seidr build <spec_path>` | Loom YAML/JSON spec; optional output/config/views/targets | VRM, preview renders, compliance report, Annáll session | `0` on full success, `1` on validation/build/compliance failure | Replace input contract; retain build semantics. |
| `seidr inspect <vrm_path>` | Existing `.vrm`; optional targets/config/JSON | Human or JSON compliance report | `0` when passed, `1` when violations fail, `3` on gate exception | Retain as `verify`/`inspect` with Three.js target. |
| `seidr bootstrap-hoard` | Configured catalog and base directory | Downloads/verifies configured bases | `0` if all entries succeed, else `1` | Keep only for licensed fixtures or make optional. |
| `seidr list-assets` | Optional type/tag filters | Human or JSON asset metadata | `0` on success, `1` on catalog error | Adapt to provenance-first catalog. |
| `seidr version` | None | Distribution version | `0` | Retain under new executable. |

`build` supports `--out`, `--config`, `--no-telemetry`, `--json`, `--views`, and
`--targets`. Its JSON response includes success, request ID, VRM path, render
paths, compliance status, session ID, elapsed time, and stage errors.

### Brúarhönd command group

| Command | Purpose | Target decision |
|---|---|---|
| `seidr brunhand health` | Query remote daemon health. | Remove. |
| `seidr brunhand capabilities` | Query GUI/runtime capabilities. | Remove. |
| `seidr brunhand screenshot` | Capture remote screen. | Remove. |
| `seidr brunhand click` | Send mouse click. | Remove. |
| `seidr brunhand type` | Type text remotely. | Remove. |
| `seidr brunhand hotkey` | Send key combination. | Remove. |
| `seidr brunhand vroid-open` | Open `.vroid` project in remote GUI. | Remove. |
| `seidr brunhand vroid-export` | Drive VRoid Studio export dialog. | Remove. |
| `seidr brunhand vroid-save` | Save remote VRoid project. | Remove. |

These commands are not part of the future character-sheet-to-VRM CLI. Their
presence is the main reason the current CLI module is 742 lines.

## REST Surface

The Straumur FastAPI application can run with:

```text
python -m seidr_smidja.bridges.straumur
uvicorn seidr_smidja.bridges.straumur.api:app
```

| Method | Route | Behavior | Target decision |
|---|---|---|---|
| `GET` | `/v1/health` | Static health/version response. | Remove with REST bridge. |
| `POST` | `/v1/avatars` | Executes full build dispatch. | Remove; CLI remains canonical. |
| `POST` | `/v1/inspect` | Runs Gate against an allowed `.vrm` path. | Remove transport; retain validation capability. |
| `GET` | `/v1/assets` | Lists Hoard assets. | Remove transport; retain CLI listing. |
| `GET` | `/v1/avatars/{session_id}` | Queries Annáll session history. | Remove unless a future product requirement reintroduces it. |
| `POST` | `/v1/brunhand/dispatch` | Executes remote GUI primitive. | Remove. |

The REST code contains useful path-containment hardening for inspect requests,
but the hosted surface itself is outside scope.

## MCP Surface

The Mjöll server exposes these observed tool names:

| MCP tool | Behavior | Target decision |
|---|---|---|
| `seidr.build_avatar` | Full build pipeline. | Remove transport. |
| `seidr.inspect_vrm` | Standalone Gate check. | Remove transport. |
| `seidr.brunhand_screenshot` | Remote screenshot. | Remove. |
| `seidr.brunhand_click` | Remote click. | Remove. |
| `seidr.brunhand_vroid_export` | Remote VRoid export. | Remove. |

MCP is not needed to generate Juana's asset and must not appear in Three.js avatar
runtime.

## Brúarhönd Daemon HTTP Surface

The remote daemon exposes:

```text
GET  /v1/brunhand/health
GET  /v1/brunhand/capabilities
POST /v1/brunhand/screenshot
POST /v1/brunhand/click
POST /v1/brunhand/move
POST /v1/brunhand/drag
POST /v1/brunhand/scroll
POST /v1/brunhand/type
POST /v1/brunhand/hotkey
POST /v1/brunhand/find_window
POST /v1/brunhand/wait_for_window
POST /v1/brunhand/vroid/export_vrm
POST /v1/brunhand/vroid/save_project
POST /v1/brunhand/vroid/open_project
```

This is an independent remote-control product with authentication, capability
probing, concurrency control, filesystem restrictions, and platform shims. It
should be removed as one bounded feature after imports are detached, not peeled
away endpoint by endpoint.

## File And Data Interfaces

| Interface | Current format/location | Current source of truth | Migration direction |
|---|---|---|---|
| Avatar input | Loom YAML or JSON | `AvatarSpec` | Replace with directory-based `CharacterDesignPackage`. |
| Base asset ID | String in spec | `data/hoard/catalog.yaml` | Retain ID indirection; strengthen provenance. |
| Process config | `config/defaults.yaml`, optional `config/user.yaml`, env | `config.py` merge rules | Narrow to build-time CLI. |
| Blendshape names | `data/loom/known_blendshapes.yaml` | Loom validator | Adapt into expression/viseme contract. |
| Compliance rules | `data/gate/*.yaml` | Gate | Add Three.js/web rules; legacy targets optional. |
| Blender input | Temporary JSON + base path + CLI args | Forge runner | Replace JSON schema with `CompiledCharacterSpec`. |
| Build output | `<avatar_id>.vrm` | Forge | Retain. |
| Preview output | `renders/*.png` | Oracle Eye | Expand to design-comparison views. |
| Telemetry | SQLite, JSONL/file, or null adapter | Annáll | Replace with build manifest/report unless durable history is required. |

## Environment Interface

Observed environment variables include:

```text
SEIDR_BLENDER_PATH
BLENDER_PATH
SEIDR_STRAUMUR_HOST
SEIDR_STRAUMUR_PORT
BRUNHAND_TOKEN
BRUNHAND_HOST
BRUNHAND_PORT
BRUNHAND_ALLOW_REMOTE_BIND
BRUNHAND_TLS_ENABLED
BRUNHAND_TLS_CERT_PATH
BRUNHAND_TLS_KEY_PATH
WAYLAND_DISPLAY
XDG_SESSION_TYPE
```

Only Blender location and future deterministic build settings are expected to
survive. REST, daemon, TLS, remote host, GUI-session, and bearer-token variables
should disappear with their features.

## Generated Artifact Contract At Baseline

A successful build can produce:

- a `.vrm` file;
- a set of PNG preview renders;
- a compliance report in memory or serialized by the calling bridge;
- Annáll session/event records;
- stdout/stderr and elapsed-time metadata.

The target contract should make the generated artifact set explicit and stable:

```text
<output>/
  <character-id>.vrm
  manifest.json
  build-report.json
  compliance-report.json
  visual-comparison-report.json
  renders/
```

## Interface Drift To Resolve

1. Historical docs use conceptual or earlier signatures that no longer match the
   concrete CLI and REST surface.
2. Comments call FastAPI/MCP optional while package metadata installs them by
   default.
3. The CLI exposes build and remote GUI operations in one module.
4. `BuildRequest.base_asset_id` duplicates data already present in the spec.
5. Platform compliance targets are transport options rather than a target profile
   owned by a stable product contract.
6. The future CLI needs distinct commands for design validation, normalization,
   compilation, build, rendering, and Three.js verification.

No compatibility promise should be made for the inherited REST, MCP, or
Brúarhönd interfaces.
