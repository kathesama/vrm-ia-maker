# Retained Blender Seam Contracts

## Purpose

This document defines the observable behavior that must survive the migration
from the inherited `seidr_smidja` namespace into the future `vrm_ia_maker`
ports and adapters. It distinguishes intentional contracts from legacy coupling
that should not be carried forward.

The classifications are:

- `PRESERVE`: observable behavior relied on by retained build paths.
- `HARDENED`: inherited intent retained with a defect corrected and regression
  evidence added.
- `REPLACE_LATER`: temporary API or naming retained only until the new
  architecture owns the capability.
- `REMOVE_LATER`: behavior tied exclusively to an out-of-scope feature.
- `NOT_CHARACTERIZED`: deliberately outside the current migration slice.

## Shared Blender Executable Resolution

| Contract | Classification | Evidence |
|---|---|---|
| `SEIDR_BLENDER_PATH` is the highest-precedence executable override. | `PRESERVE` | `tests/characterization/test_blender_runner_contract.py` |
| Legacy `BLENDER_PATH` is accepted only when the primary variable is absent or invalid. | `REPLACE_LATER` | `tests/characterization/test_blender_runner_contract.py` |
| An explicit file path in `blender.executable` wins over `PATH`. | `PRESERVE` | `tests/characterization/test_blender_runner_contract.py` |
| The `blender` command on `PATH` wins over platform hints. | `PRESERVE` | `tests/characterization/test_blender_runner_contract.py` |
| Configured platform hints win over deprecated built-in hints. | `PRESERVE` | `tests/_internal/test_blender_runner.py` |
| Failure reports the attempted resolution mechanisms through `locations_checked`. | `PRESERVE` | `tests/characterization/test_blender_runner_contract.py` |
| Built-in platform path constants remain available during migration. | `REPLACE_LATER` | Removal trigger: new configuration contract owns all platform hints. |

## Shared Blender Subprocess Runner

| Contract | Classification | Evidence |
|---|---|---|
| Invocation shape is `blender --background --python <script> -- <args>`. | `PRESERVE` | Real-process characterization test. |
| Standard output is captured in order and optionally streamed line by line. | `PRESERVE` | Real-process characterization test. |
| A failing observation callback never terminates Blender or discards captured output. | `PRESERVE` | Callback regression test. |
| Standard output and standard error are drained concurrently. | `HARDENED` | Large-stderr regression test proves the pipe cannot deadlock the parent. |
| The configured timeout bounds total subprocess execution, including silent processes. | `HARDENED` | Real silent-process timeout test. |
| The timeout remains active after the process leader exits while descendants keep inherited output pipes open. | `HARDENED` | Leader-exit descendant regression test. |
| Timeout terminates the Blender process tree rather than only the direct process. | `HARDENED` | POSIX descendant-process regression test plus Windows branch unit coverage. |
| Partial output is retained after timeout or non-zero exit. | `PRESERVE` | Output-capture characterization tests. |
| Invalid UTF-8 is decoded with replacement instead of crashing the runner. | `PRESERVE` | Real invalid-byte regression test. |
| `RunnerResult` fields and `run_blender()` call signature remain stable for current callers. | `PRESERVE` | Full retained suite and type check. |
| The `seidr_smidja._internal` location is authoritative. | `REPLACE_LATER` | Removal trigger: callers switch to the new Blender infrastructure adapter. |

### Corrected inherited defects

The previous implementation read all standard output before reading standard
error and did not call a timed wait until standard output reached EOF. Two
observable failures followed:

1. a silent or long-running process could exceed the configured timeout;
2. a process that filled the standard-error pipe could deadlock indefinitely.

The retained public contract promised bounded execution and captured output, so
correcting these defects is classified as hardening rather than a new product
feature.

## Forge Orchestration

| Contract | Classification | Evidence |
|---|---|---|
| The validated avatar specification is serialized to a temporary JSON file. | `PRESERVE` | `tests/characterization/test_forge_contract.py` |
| Blender receives `--spec`, `--base`, and `--output` in that order. | `PRESERVE` | Exact-argument characterization test. |
| Output is expected at `<output_dir>/<avatar_id>.vrm`. | `PRESERVE` | Characterization test. |
| The output directory is created before Blender is invoked. | `PRESERVE` | Characterization test. |
| Temporary specification files are removed after success and launch failures. | `PRESERVE` | Cleanup characterization tests and inherited hardening tests. |
| Exit code zero without the expected VRM is a structured failed result. | `PRESERVE` | Characterization test. |
| A partial VRM created by a non-zero process remains visible in `vrm_path`, while `success` remains false. | `PRESERVE` | Partial-output characterization test. |
| Blender discovery and launch errors are wrapped as `ForgeBuildError`. | `PRESERVE` | Characterization test. |
| Telemetry failure never changes the build outcome. | `REPLACE_LATER` | Current behavior is characterized; Annáll will be replaced by build reports. |
| Forge accepts `AvatarSpec` as its input contract. | `REPLACE_LATER` | Removal trigger: `CompiledCharacterSpec` becomes authoritative. |

The Blender build script itself is not characterized by this slice. Base-specific
mesh, bone, material, expression, and export behavior remains
`NOT_CHARACTERIZED` until the compiler and base-model adapter contracts exist.

## Preview Render Orchestration

| Contract | Classification | Evidence |
|---|---|---|
| `views=None` requests every current standard view. | `PRESERVE` | `tests/characterization/test_oracle_eye_contract.py` |
| Explicit subsets accept enum values and strings. | `PRESERVE` | Characterization test. |
| Resolution is read from `oracle_eye.resolution` and passed as width and height arguments. | `PRESERVE` | Characterization test. |
| Exit zero with every requested PNG is success. | `PRESERVE` | Corrected success regression test. |
| Missing PNGs are a soft failure and successfully rendered paths remain available. | `PRESERVE` | Partial-render characterization test. |
| Non-zero exit and timeout are soft failures represented in `RenderResult.errors`. | `PRESERVE` | Failure characterization tests. |
| Blender discovery or launch failure is a hard `RenderError`. | `PRESERVE` | Infrastructure-failure characterization tests. |
| Telemetry failure never changes the render result. | `REPLACE_LATER` | Annáll removal trigger matches Forge. |
| Brúarhönd external screenshot registration remains part of the retained renderer. | `REMOVE_LATER` | Removal trigger: Brúarhönd integration is deleted after retained callers are absent. |

The Blender render script, camera composition, materials, lighting, and image
quality are `NOT_CHARACTERIZED` in this slice. They require visual fixtures and
Blender integration evidence in a later phase.

## Migration Rules

1. New adapters may wrap these contracts before moving implementation.
2. A contract marked `PRESERVE` must have equivalent automated evidence before
   the legacy caller is removed.
3. A contract marked `HARDENED` must not regress to the inherited unsafe
   behavior.
4. A `REPLACE_LATER` seam must name its removal trigger in the implementation
   ticket that introduces its replacement.
5. `REMOVE_LATER` behavior must not be copied into the new namespace.
6. Items marked `NOT_CHARACTERIZED` cannot be treated as stable requirements.

## Current Validation Commands

```sh
ruff check \
  src/seidr_smidja/_internal/blender_runner.py \
  tests/characterization/ \
  tests/_internal/test_blender_runner.py \
  tests/test_hardening_h001_h002_h006.py \
  tests/test_hardening_h017_forge_oracle_nobler.py

mypy src/seidr_smidja/_internal/blender_runner.py

pytest -q tests/characterization/
pytest -q tests/_internal/test_blender_runner.py
pytest -q tests/test_hardening_h001_h002_h006.py
pytest -q tests/test_hardening_h017_forge_oracle_nobler.py
```
