# D-015 - Panel-First Pixel Portrait Authoring
**Status:** Accepted
**Date:** 2026-07-21
**Deciders:** Kathy Aguirre, repository owner
**Phase:** Pixel talking-portrait authoring

## Context

D-013 established a bounded, human-gated, sheet-first reference-authoring
workflow. GH-23 needs a different review unit: each pixel-art panel must be
retryable and approvable independently before any family or package-wide sheet
can be trusted. Retrofitting that history into the existing sheet-level
contracts would change the already sealed talking-bust workflow and its V1
package.

The pixel profile also has two sources with different authority. The approved
base set defines Juana's visible two-dimensional identity, while the sealed
`juana-talking-bust-v1` package supplies technical coverage for named views and
articulations. Neither source provides permission to invent measurements,
occluded geometry, legal rights, or human approval.

The authoring package must remain independent of any later portrait runtime.
Three.js may eventually consume a separately compiled bundle, but runtime
assets and behavior do not belong inside a sealed `CharacterDesignPackage`.

## Decision

- Add `vrm_ia_maker.design.pixel_portrait` as an additive sibling bounded
  context. It may reuse generic evidence, rights, generation-request, and image
  provider primitives from `vrm_ia_maker.design`, but it owns its fixed plan,
  state, service, filesystem adapter, and internal module CLI. The existing
  sheet-first contracts and workflow remain unchanged.
- Fix revision one at exactly 49 individual panels in nine ordered families:
  `presence-states`, `face-turnaround`, `facial-mechanics`,
  `upper-body-turnaround`, `expressions`, `visemes`, `hair-construction`,
  `outfit-construction`, and `material-reference`.
- Treat the seven base-set PNGs as creative identity authority. Treat the
  sealed `juana-talking-bust-v1` package as read-only technical coverage. When
  visible identity conflicts, the base set wins. The V1 package remains
  byte-for-byte unchanged, retains its existing contract, and remains the
  package for the VRM-only production path; GH-23 neither republishes it as a
  pixel package nor writes pixel or runtime artifacts into it.
- One explicit `run` invocation performs at most one provider call for one
  panel. Every provider outcome, including failure or interruption, consumes a
  recorded attempt, and no panel may exceed three attempts. The workflow never
  retries a provider call transparently.
- Approval of the neutral presence panel records an immutable
  `PortraitIdentityLock`. The lock freezes the approved palette, logical pixel
  grid, screen-facing hair orientation, portrait anchors, and face-height
  tolerance for dependent panels in that package revision. These are
  pixel-layout constraints, not real-world measurements or executable
  geometry.
- Preserve provider output as candidate evidence and produce the review panel
  through deterministic local pixel normalization. Individual panels remain
  the provenance and retry units; a composite sheet is never a source from
  which panels are cropped.
- Compose one deterministic review sheet for each family from the current
  approved panel hashes in fixed order. Compose one deterministic package
  master from the nine current approved family sheets. Superseding a panel
  preserves history and invalidates only its dependent family sheet and the
  package master.
- Publish the additive package with schema version `1.1` and profile
  `pixel-talking-portrait`. It retains the canonical CharacterDesignPackage
  directories and adds immutable `sources/` locks and `authoring/` metadata.
  The sole `package.json.master_reference` is
  `references/master/master-character-sheet.png`; the neutral panel is the
  identity lock, not the package master.
- Keep all six `expressions` family panels `authoring_only` in revision one.
  Presence-state, eye-patch, and mouth-patch roles describe eligibility for a
  later compiler; they do not place runtime assets or behavior in the sealed
  package.
- Compile any portrait runtime and Three.js bundle only in a later issue as a
  separately sealed derived artifact outside the CharacterDesignPackage. The
  derived bundle must identify the sealed source-package digest and must not
  modify that package.
- Fail closed on incomplete source rights, provenance, changed hashes,
  unapproved panels, stale or unreviewed composites, and missing human visual
  approval. Provider generation, deterministic normalization, or structural
  validation cannot grant identity or legal approval.

## Consequences

### Enabled

- A failed or drifting panel can be retried and reviewed without regenerating
  unrelated approved panels.
- Deterministic family sheets expose cross-panel drift while preserving each
  panel's exact source and attempt lineage.
- Schema-1.0 talking-bust packages and the sealed V1 source remain compatible
  without migration.
- A later runtime compiler can consume a sealed, hash-addressed input without
  coupling authoring to Three.js or an image provider.

### Constrained

- No dependent panel is eligible before explicit neutral approval establishes
  the active identity lock.
- No family sheet, package master, or seal may bypass its current human review
  and integrity gates.
- The package contains no `runtime/` directory, viewer, animation policy, or
  conversational-runtime integration.
- GH-23 defines and validates the authoring workflow; it does not claim that 49
  final Juana panels, a production pixel package, a viewer, or a VRM have been
  produced.

### Revisit Later

- Define the separately derived portrait-manifest and Three.js bundle in a
  dependent issue after a pixel package has passed rights, provenance, and
  visual approval gates.
- Promote an expression panel to a runtime role only through a new approved
  package revision and explicit runtime-manifest change.

## Rejected Alternatives

- Extending the sheet-first `CandidateRecord` and task state was rejected
  because it would retrofit panel-level history into the sealed V1 workflow.
- Using generated family sheets as crop sources was rejected because it would
  erase individual-panel provenance and retry boundaries.
- Automatic visual approval was rejected because deterministic checks cannot
  authorize identity changes.
- Embedding a runtime bundle or Three.js viewer in the package was rejected
  because authoring evidence and runtime delivery have different contracts and
  lifecycles.

## References

- GitHub issue GH-23.
- `docs/CHARACTER_DESIGN_PACKAGE.md`.
- `docs/superpowers/specs/2026-07-21-juana-pixel-talking-portrait-design.md`.
- `docs/DECISIONS/D-013-bounded-reference-authoring.md`.
- `docs/DECISIONS/D-014-production-blender-forge-boundary.md`.
- `ASSET_POLICY.md`.
