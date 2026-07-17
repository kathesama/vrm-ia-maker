# Safe Pruning Sequence

## Strategy

Use a strangler-style migration, not a big-bang rewrite:

```text
character package + new compiler
        -> adapted asset/Blender/render/validation capabilities
        -> new CLI cutover
        -> removal of legacy transports and remote GUI feature
        -> deletion of old namespace
```

Each phase must leave a runnable, reviewable repository. Deletion follows
replacement and evidence, never the other way around.

## Phase 0 — Freeze And Inventory

**Status:** this document set.

Deliverables:

- pinned baseline and provenance;
- source/interface/dependency inventories;
- fresh quality evidence;
- component disposition;
- asset/license gaps.

Exit gate: documentation-only diff; no behavior changed.

## Phase 1 — Repository Identity, Licensing, And Quality Baseline

### Work

- rename distribution/project metadata to `vrm-ia-maker`;
- correct `pyproject.toml` from MIT to Apache-2.0;
- preserve and extend `NOTICE`;
- create `THIRD_PARTY_NOTICES.md` and asset policy;
- replace the active README with target product scope;
- make Ruff, mypy, and pytest report independently in CI;
- fix lint only in retained bootstrap/CLI infrastructure when needed for green
  gates; defer deletion-bound code.

### Exit gate

- package installs under the new identity;
- source attribution is intact;
- CI exposes all quality results independently;
- no target behavior yet depends on old marketing documents.

### Rollback

Distribution rename and metadata changes remain one focused PR and can be
reverted without touching Forge behavior.

## Phase 2 — Characterize Retained Seams

This phase is deliberately split so subprocess hardening is not mixed with asset
integrity, binary parsing, and CLI compatibility work.

### Phase 2A — Blender execution seams

Status: implemented in the current migration slice.

- characterize Blender executable resolution and precedence;
- enforce bounded subprocess execution and process-tree termination;
- drain stdout and stderr concurrently;
- preserve partial output and callback behavior;
- characterize Forge temporary files, arguments, outputs, and error wrapping;
- characterize preview render views and soft-failure semantics;
- document retained, hardened, temporary, and removal-bound contracts in
  `RETAINED_SEAM_CONTRACTS.md`.

### Phase 2B — Asset, VRM, and selected CLI seams

Status: pending.

- characterize Hoard path containment and checksum validation;
- verify cached assets against pinned checksums;
- characterize VRM reader behavior for 0.x and 1.0 fixtures;
- characterize selected CLI JSON and exit behavior.

### Exit gate

Every `RETAIN` or `ADAPT` component has explicit behavior-to-preserve evidence
(`WELC-01` ) before it moves or receives a replacement.

## Phase 3 — Introduce The New Namespace And Ports

### Work

Create `src/vrm_ia_maker/` with no imports from Blender, FastAPI, MCP, or
Brúarhönd in domain/application layers:

```text
vrm_ia_maker/
  design/
  compilation/
  assets/
  forge/
  rendering/
  validation/
  reports/
  application/
  cli/
```

Define ports for assets, base adapters, forge, renderer, and validation. Keep
legacy implementations behind temporary compatibility adapters.

### Exit gate

- new package imports cleanly;
- dependency-direction tests pass;
- compatibility wrappers have explicit removal triggers (`WELC-03`).

## Phase 4 — CharacterDesignPackage

### Work

Implement the canonical directory package:

```text
character.yaml
measurements.yaml
palette.yaml
materials.yaml
views/
face/
expressions/
visemes/
hair/
outfit/
LICENSE.md
```

Add validation for required views, alignment metadata, dimensions, paths,
measurements, landmarks, materials, expressions, visemes, provenance, and hashes.
Add CLI commands:

```text
vrm-maker design validate
vrm-maker design normalize
```

### Exit gate

- one complete fixture validates;
- invalid/path-traversal/provenance cases fail deterministically;
- Loom is no longer the future source of truth (`TPP-01`).

## Phase 5 — Compiler And Base-Model Adapters

### Work

Create:

```text
CharacterDesignPackage
    + BaseModelAdapter capabilities
    -> CompiledCharacterSpec
```

Move base-specific bone, morph, material, expression, and viseme knowledge out of
`build_avatar.py`. Implement the first versioned adapter for the selected legal
base fixture.

### Exit gate

- compiler rejects unsupported requested features;
- compiled operations are explicit and serializable;
- adapter contains no general pipeline orchestration;
- golden compiled-spec fixture is reproducible.

## Phase 6 — Migrate The Useful Build Capabilities

### Work

1. move the shared Blender runner;
2. adapt Forge runner to `CompiledAssemblySpec`;
3. split generic VRM setup/export from adapter operations;
4. adapt the renderer and standard views;
5. adapt the VRM reader and compliance reports;
6. introduce a Three.js/web target;
7. replace Annáll requirements with manifest/build-report output, using Null
   telemetry during transition.

### Current production boundary

GH-16 establishes the production Forge boundary for steps 2 and 3 without
prematurely performing step 1. `RetainedBlenderRunnerAdapter` preserves the
characterized subprocess behavior while schema 1.1 assembly, VRM setup,
staged validation, and build-report publication live under `vrm_ia_maker`.

Phase 6 is not complete. The renderer, standard views, production reader,
public command surface, and licensed Juana assets still require migration.
The retained runner and spike finalizers remain until the D-014 deletion trigger
is satisfied; procedural workflow parity alone is insufficient.

### Exit gate

A tracer-bullet fixture completes:

```text
design validate
-> compile
-> Blender build
-> render
-> VRM structural validation
-> manifest/report
```

The artifact must load in a Node/Three.js validator before broader feature work.

## Phase 7 — CLI Cutover

### Work

Introduce the final command surface, for example:

```text
vrm-maker design validate <package>
vrm-maker design normalize <package>
vrm-maker compile <package> --base <id>
vrm-maker build <package> --base <id> --out <dir>
vrm-maker inspect <vrm>
vrm-maker verify-threejs <vrm>
vrm-maker assets list
```

Make the new application services authoritative. Decide explicitly whether any
legacy `seidr` command receives a short compatibility wrapper.

### Exit gate

- documented end-to-end CLI works without importing REST, MCP, or Brúarhönd;
- selected JSON/exit contracts are tested;
- old build dispatch has no production caller.

## Phase 8 — Remove Lateral Features

Remove in this order:

1. upstream agent skill manifests;
2. MCP bridge and dependency;
3. REST bridge and FastAPI/Uvicorn dependency;
4. Brúarhönd dispatch from Core;
5. Brúarhönd CLI commands;
6. Brúarhönd client/daemon tree and GUI dependencies;
7. external-render registration used only by Brúarhönd;
8. Brúarhönd tools, config, docs, and tests.

### Deletion gate for each step

- zero retained imports;
- zero target CLI exposure;
- dependency removed from package metadata where applicable;
- test count reduction explained by deleted scope, not broad skip markers;
- retained suite stays green.

Brúarhönd should be removed as a bounded set, not through partial runtime stubs.

## Phase 9 — Retire Legacy Core And Repository Narrative

### Work

- remove old Loom after all fixtures use CharacterDesignPackage;
- remove old dispatch after new application service is authoritative;
- remove or reduce Annáll adapters after reports replace them;
- remove `src/seidr_smidja` when no import remains;
- replace examples;
- archive or remove upstream mythic/task/log documents;
- remove unrelated `scripts/fix_memory_thread_safety.py`;
- remove root media after provenance/retention decision;
- prune obsolete dependencies and config keys.

### Exit gate

```sh
rg "seidr_smidja|brunhand|straumur|mjoll" src tests pyproject.toml config data
```

returns only intentional migration/attribution references, and the full new suite
passes without legacy namespace configuration.

## Phase 10 — Juana Production Asset

### Work

- approve the canonical Juana character sheet and measurements;
- select or author a base with verified commercial/derivative/redistribution
  rights;
- build the Juana-specific adapter/assets;
- iterate through deterministic renders and visual comparison;
- produce `juana-v1.vrm`, manifests, reports, and previews;
- validate in Three.js with blink, look-at, expressions, visemes, and spring bones.

### Exit gate

The VRM is traceable to design, base asset, adapter, tool commit, Blender version,
VRM add-on version, and every incorporated asset hash/license.

## Proposed Ticket Boundaries

Create separate GitHub issues after Issues are enabled:

1. repository identity/license correction;
2. CI baseline and retained-code lint policy;
3. retained seam characterization;
4. new namespace and ports;
5. CharacterDesignPackage schema/validator;
6. normalization pipeline;
7. base adapter and compiler;
8. Blender runner/Forge migration;
9. renderer/comparison migration;
10. Three.js validation target;
11. CLI cutover;
12. MCP/REST removal;
13. Brúarhönd removal;
14. legacy namespace/document cleanup;
15. Juana base and production build.

Do not collapse these into one mega-PR.

## Migration Safety Checklist

Before every pruning PR:

- [ ] Current behavior to preserve is named (`WELC-01`).
- [ ] Change point and seam are explicit (`WELC-02`).
- [ ] Temporary compatibility code has a cleanup trigger (`WELC-03`).
- [ ] One source of truth is identified (`TPP-01`).
- [ ] The decision can be rolled back or has a stated mitigation (`TPP-02`).
- [ ] A close feedback/diagnostic command exists (`TPP-03`).
- [ ] Asset and license impact is reviewed.
- [ ] No unrelated cleanup is bundled.
- [ ] Ruff, mypy, pytest, and relevant integration checks report independently.
