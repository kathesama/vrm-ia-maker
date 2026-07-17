# D-014 - Production Blender Forge Boundary
**Status:** Accepted
**Date:** 2026-07-17
**Deciders:** Kathy Aguirre, repository owner
**Phase:** Production modular finalization

## Context

SPIKE-2 proved modular Blender assembly and VRM export, while D-011 promoted
the Three.js compiler and its schema 1.1 handoff. The retained Blender
finalizer still combines schema interpretation, base-specific VRM setup,
assembly, export, and validation by importing the inherited build script. That
coupling cannot become the production boundary because it allows hardcoded base
knowledge to override the versioned adapter and makes successful subprocess
exit look equivalent to a validated, publishable artifact.

The shared retained Blender runner also serves preview rendering. Moving or
duplicating it before every caller has migrated would either break preserved
behavior or create two sources of subprocess policy.

## Decision

- `vrm_ia_maker.forge.finalize_compiled_assembly` is the production application
  use case for schema 1.1 modular finalization.
- The use case depends on `BlenderExecutionPort`. Subprocess discovery,
  invocation, timeout, process-tree termination, and output capture remain
  infrastructure concerns.
- Production policy modules do not import `bpy`, the VRM Add-on, spike modules,
  or the retained namespace. Blender-specific APIs stay in
  `vrm_ia_maker.forge.blender`.
- VrmBuildSpec is the only source for humanoid bone assignments, expression
  binds, look-at ranges, and embedded avatar metadata. The production Blender
  adapter has no fallback base map.
- Blender is the final writer of every distributed VRM. Three.js compiles and
  inspects compositions and later validates consumer loading; it does not write
  the `.vrm`.
- Blender writes only staged VRM and scene-evidence files. Host Python validates
  the process result, strict evidence contract, and staged VRM before it creates
  the build report and publishes the VRM/report pair without overwriting an
  existing target.
- `RetainedBlenderRunnerAdapter` is the sole temporary dependency on
  `seidr_smidja._internal.blender_runner`.
- The retained seam deletion trigger is satisfied only when preview rendering
  and every other retained Blender caller use `BlenderExecutionPort`, runner
  characterization remains green after relocation, and the production
  schema 1.1 workflow has equivalent Blender, structural, and Three.js evidence.
- SPIKE-1 and SPIKE-2 files and schema 1.0 workflow steps remain preserved until
  production parity is demonstrated with approved production assets. This ADR
  does not authorize their deletion.

## Consequences

### Enabled

- Forge orchestration and failure-safe publication can be tested without a
  local Blender installation.
- Blender receives one self-contained standard-library JSON handoff and does
  not require Pydantic in its embedded Python environment.
- Base-model mappings remain traceable to a versioned adapter and cannot be
  silently replaced by inherited defaults.
- Both retained schema 1.0 and production schema 1.1 paths can run against the
  same procedural assets in one workflow.

### Constrained

- The retained runner cannot move yet because preview rendering has not
  migrated to the production port.
- Unit tests cannot claim Blender or VRM Add-on compatibility. The pinned
  Blender workflow remains required runtime evidence.
- Publication is a validated pair operation implemented with exclusive file
  creation and explicit rollback; existing or competing targets are never
  overwritten.
- This boundary produces procedural parity evidence only. It does not produce
  or claim `dist/juana/juana.vrm`.

### Revisit Later

- Move the shared runner into production infrastructure after the deletion
  trigger is met.
- Adapt preview rendering and standard views to `BlenderExecutionPort`.
- Replace procedural fixtures with licensed, human-approved Juana assets and a
  corresponding production base adapter.
- Expose the final compile/build/validate sequence through the public CLI.

## References

- GitHub issue GH-16.
- D-007, Blender subprocess pattern.
- D-011, production Three.js assembly compiler boundary.
- `docs/migration/RETAINED_SEAM_CONTRACTS.md`.
- `docs/migration/PRUNING_SEQUENCE.md`.
- `src/vrm_ia_maker/forge/`.
- `.github/workflows/modular-vrm-output-spike.yml`.
