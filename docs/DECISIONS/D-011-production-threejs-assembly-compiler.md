# D-011 - Production Three.js Assembly Compiler Boundary
**Status:** Accepted
**Date:** 2026-07-15
**Deciders:** Kathy Aguirre, repository owner
**Phase:** Production modular composition

## Context

SPIKE-2 proved that Three.js can select modular assets, inspect GLB structure,
and hand a compiled specification to Blender. Its compiler cannot become a
production boundary unchanged: it consumes an obsolete array-shaped selection
document and hardcodes humanoid bones, expressions, and look-at limits for one
procedural base.

The production contracts now represent asset catalogs, assembly selections,
and Blender-facing compiled specifications. A separate source of base-specific
mapping knowledge is required so the compiler can support future approved base
models without embedding their names in code or coupling them to provenance.

## Decision

- Pydantic remains the authoritative manifest and compiled-spec contract layer.
- A standalone, versioned `BaseModelAdapterManifest` owns the humanoid bone,
  expression, and look-at mappings for one base asset.
- `packages/three-assembly-compiler` owns deterministic singular-slot selection,
  local asset integrity checks, and GLB structural inspection.
- The compilation use case accepts plain validated documents and an injected
  inspection function. `GLTFLoader` remains isolated in the inspection adapter.
- The production compiler emits `CompiledAssemblySpec` schema 1.1 and records the
  adapter identifier and version. Existing schema 1.0 compiled documents remain
  loadable but cannot claim adapter traceability.
- The internal Node CLI refuses existing output targets and publishes compiled
  and inspection documents only after compilation succeeds.
- Three.js does not write the distributed VRM. Blender remains the final writer,
  and Three.js remains responsible for later preview and consumer validation.
- The retained SPIKE-2 compiler and Blender finalizer remain executable evidence
  until the production Blender path reaches equivalent behavior.

## Consequences

### Enabled

- Base-model mappings can change through a versioned data document without a
  compiler code change.
- Selection and compatibility policy can be tested without loading Three.js.
- Node output is checked against the Python contracts before it becomes a Blender
  handoff.
- Every catalog asset is hash- and size-checked, while structural parsing is
  limited to the base and selected components.

### Constrained

- The Node CLI is an internal build boundary. Its caller must first validate the
  three input documents with the production Pydantic loaders.
- Absolute local asset paths remain allowed for licensed assets stored outside
  the repository. Relative paths must remain inside the asset-pack directory.
- GLB inspection reads each file into memory. Streaming and explicit file-size
  limits are deferred until production asset constraints are known.
- Node dependencies are installed separately from the Python package; unified
  distribution belongs to the future application CLI slice.

### Revisit Later

- Integrate the compiler behind the production `vrm-maker` application use case.
- Promote the Blender modular finalizer and VRM validation path into production.
- Define file-size limits or streaming inspection if approved assets require it.
- Replace temporary procedural adapters with an adapter for a licensed,
  human-approved Juana base model.

## References

- GitHub issue GH-14.
- `docs/research/SPIKE-2-MODULAR-ASSET-COMPOSITION.md`.
- `docs/research/CHARACTERSTUDIO_CONCEPT_MAP.md`.
- `docs/migration/DEPENDENCY_MAP.md`.
- `src/vrm_ia_maker/contracts.py`.
- `packages/three-assembly-compiler/`.
