# Juana Pixel Talking Portrait Design

**Status:** Awaiting written specification review; visual and architecture direction approved  
**Date:** 2026-07-21  
**Design approver:** Kathy  
**Repository:** `kathesama/vrm-ia-maker`

## Decision Summary

Create a new, independently sealed two-dimensional character package named
`juana-talking-bust-v2-pixel` and a deterministic Three.js viewer that
renders the character as fine pixel art inside a balanced HD-2D diorama.

The new package uses the seven files in `juana-avatar-base-set` as the visible
identity authority for the 2D character. In particular, they define Juana's
younger facial appearance, screen-facing hair orientation, outfit treatment,
and presence states. The existing sealed package
`juana-talking-bust-v1` remains unchanged and continues to serve the future 3D
VRM path. Its approved references provide technical coverage for views,
facial mechanics, expressions, visemes, hair, body, outfit, and materials, but
they do not override the 2D identity.

Every required pixel-art panel is authored and approved individually. A review
sheet is then composed deterministically from the approved individual panels.
Both the individual panels and their composite sheets are retained and sealed.

## Approved Visual Direction

- Character style: fine pixel art, corresponding to the approved option A.
- Portrait density: a 512 by 512 PNG carrying a 256 by 256 logical pixel grid
  for runtime portrait panels. The approved neutral master establishes a face
  height target of 160 logical pixels; dependent portrait panels may vary by no
  more than two logical pixels unless their named pose requires an approved
  exception. Display scaling uses integer multiples and nearest-neighbor
  filtering.
- Environment style: balanced HD-2D diorama, corresponding to the approved
  option B.
- Screen-facing orientation: shaved hair on the viewer's left and long hair on
  the viewer's right, matching `juana-avatar-base-set`.
- Animation language: complete panels for state or emotion changes; localized
  pixel patches for eyes and mouth.
- Visual priority: the face and mouth remain readable and sharp. The diorama
  supplies depth without competing with the conversation.

## Goals

1. Produce a portable and traceable pixel-art package covering every reference
   family present in `juana-talking-bust-v1`.
2. Preserve the preferred younger Juana identity from `juana-avatar-base-set`
   across every generated panel.
3. Make each panel independently retryable, reviewable, approvable, and
   supersedable.
4. Produce deterministic composite sheets that expose cross-panel drift.
5. Compile a small runtime bundle for a layered talking portrait without
   loading the full authoring package.
6. Provide a local Three.js window that demonstrates state changes, blinking,
   five visemes, lighting, parallax, and depth.
7. Preserve provenance, rights declarations, approvals, hashes, and upstream
   package lineage throughout the process.

## Non-Goals

- Do not modify, replace, or reinterpret the sealed
  `juana-talking-bust-v1` package.
- Do not produce or modify `dist/juana/juana.vrm` in this work.
- Do not integrate with Juana's conversational runtime in another repository.
- Do not implement STT, TTS, phoneme inference, reasoning, authorization, or
  tool execution inside the viewer.
- Do not treat generated pixel panels as approved canon without an explicit
  human decision.
- Do not make the runtime load body turnarounds, material boards, or other
  authoring-only panels during a conversation.

## Source Authority and Conflict Resolution

### 2D creative canon

The following source set is authoritative for the visible 2D identity:

```text
C:/Users/kathe/Downloads/Juana Proyect/
  juana-presence-layer-package/juana-avatar-base-set/
```

The source set contains:

- `juana-avatar-character-sheet.png`;
- `juana-avatar-neutral.png`;
- `juana-avatar-thinking.png`;
- `juana-avatar-explaining.png`;
- `juana-avatar-approval.png`;
- `juana-avatar-doubt.png`;
- `juana-avatar-error.png`.

These files govern facial age, likeness, hair orientation, visible outfit,
color impression, and the six presence states. The `listening` runtime state
uses the neutral panel unless a separately approved listening panel is added in
a later revision.

### Technical reference source

The sealed package below is authoritative for technical coverage only:

```text
output/character-design-packages/juana-talking-bust-v1/
```

It supplies the expected panel inventory and the intended meaning of:

- face turnarounds;
- facial mechanics;
- upper-body turnarounds;
- expressions;
- visemes;
- hair construction;
- outfit construction;
- material references.

When the two sources conflict in visible identity, the base set wins for the
2D package. When the base set lacks a technical view or articulation, the
sealed package defines the requested view or articulation, but the result must
be redrawn with the base-set identity.

### Source rights

The downloaded presence-layer folder contains design and implementation notes
but no explicit license or provenance manifest. The new authoring workspace
must therefore begin with a blocking `source-rights-incomplete` gap. Sealing is
forbidden until the owner records author, rights holder, license, commercial
use, modification permission, redistribution permission, and attribution for
the base set. This gate does not block contract or viewer development with
non-distributed fixtures.

### Filesystem isolation

The existing package is a read-only technical input:

```text
output/character-design-packages/juana-talking-bust-v1/
```

Raw provider results, rejected attempts, and provisional panels live only in
the ignored authoring workspace:

```text
output/authoring/juana-talking-bust-v2-pixel/
```

The new approved package is published only to its own no-clobber destination:

```text
output/character-design-packages/juana-talking-bust-v2-pixel/
```

No command in the pixel profile may use the V1 directory as a write target.
Regression validation records its existing seal inventory before and after the
workflow and fails if any V1 file changes.

## Architecture

The work is divided into three dependent slices.

### Slice 1: panel-first pixel package authoring

Add an independent panel-first profile beside the existing bounded sheet-first
workflow. The new profile reuses shared evidence and rights primitives but has
its own plan, state, service, workspace adapter, and CLI boundary so the sealed
talking-bust profile and its contracts remain unchanged.
Lock both source sets, approve one neutral master, author every required panel,
compose family review sheets, and seal the complete pixel package.

### Slice 2: runtime bundle compiler and validator

Compile approved front-facing panels into base states, eye patches, mouth
patches, and `portrait-manifest.json`. The compiler writes a separately sealed
derived bundle under `build/juana-pixel-portrait-runtime/`; it never modifies
the already sealed character package. Validate the bundle without requiring a
browser or WebGL context.

### Slice 3: Three.js HD-2D viewer

Load the runtime bundle in a local browser window. Render Juana on a sharp
focal plane surrounded by a balanced 3D diorama. Expose deterministic controls
for state, blink, wink, and viseme events.

## Panel-First Authoring Workflow

### Family inventory

The new profile contains these panel families:

1. `presence-states`;
2. `face-turnaround`;
3. `facial-mechanics`;
4. `upper-body-turnaround`;
5. `expressions`;
6. `visemes`;
7. `hair-construction`;
8. `outfit-construction`;
9. `material-reference`.

Every individual reference panel in the upstream sealed package receives a
corresponding pixel-art panel. The six base-set presence images also receive
individual pixel-art panels. The fixed first-revision inventory is:

- 43 technical panels: five face-turnaround, six facial-mechanics, four
  upper-body-turnaround, six expression, six viseme, six hair-construction,
  four outfit-construction, and six material-reference panels;
- six presence-state panels: neutral, thinking, explaining, approval, doubt,
  and error;
- nine deterministic family review sheets, one for each family above; and
- one deterministic master character sheet assembled from the nine approved
  family sheets.

The eight upstream approved sheets and upstream master character sheet are
layout and semantic references. They are not sent to a pixelation operation as
opaque images. Their replacements are assembled from the newly approved
individual panels so panel provenance and retries remain intact.

### Authoring sequence

1. Copy or lock every input with dimensions, byte length, SHA-256, source
   class, and rights metadata.
2. Author the neutral presence panel first.
3. Obtain explicit visual approval for the neutral master. Its face, age,
   palette, logical pixel density, hair orientation, and portrait anchors then
   become immutable for the package revision.
4. Create one `PixelPanelDefinition` per panel with a fixed family, canvas,
   source references, anchor contract, runtime role, prompt identifier, and
   prompt version.
5. Execute at most one provider request per explicit command and at most three
   recorded attempts per panel.
6. Validate each returned PNG before review.
7. Record an approve, reject, or supersede decision for the individual panel.
8. When all required panels in a family are approved, compose the family sheet
   deterministically from their exact hashes and fixed order.
9. Review the composite sheet for cross-panel drift. A drift finding reopens
   only the affected panel or panels.
10. After all nine family sheets are current, compose the package master sheet
    deterministically from their exact hashes and fixed order.
11. Seal only after every required panel, family sheet, and the package master
    sheet passes its gates.

### Consistency guards

- Portrait panels share a fixed 512 by 512 file canvas and 256 by 256 logical
  grid.
- Dependent portrait panels preserve the neutral master's 160-logical-pixel
  face height within a two-pixel tolerance, except for an explicitly approved
  pose-specific exception recorded in the panel approval.
- Technical panels within a family share one fixed canvas and logical scale,
  recorded in their panel definitions.
- Portrait families share face, eye, mouth, shoulder, and pivot anchors.
- Full-body and construction families use their own family-specific alignment
  contracts rather than forcing portrait anchors onto unrelated views.
- No runtime texture uses smooth interpolation.
- A new attempt may change only the named panel and must repeat all identity
  invariants in its prompt or deterministic transformation.
- Composite sheets never become the source from which panels are cropped.

## Contract Evolution

The existing `CandidateRecord` represents a generated sheet plus deterministic
previews. It remains valid for the already sealed sheet-first profile and is
not redefined retroactively.

The panel-first profile adds these contracts:

### `PixelPanelDefinition`

Required fields:

- `panel_id` and `family_id`;
- package destination path;
- source artifact references;
- file canvas and logical pixel dimensions;
- pivot, eye, mouth, shoulder, and family-specific anchors as applicable;
- runtime role: `authoring_only`, `state`, `eye_patch`, or `mouth_patch`;
- prompt identifier and version;
- ordered position in the composite review sheet.

### `PixelPanelCandidate`

Required fields:

- candidate and panel identifiers;
- attempt number from one through three;
- pending, approved, rejected, or superseded status;
- provider, model, prompt identifier, and prompt version;
- all input artifact evidence;
- one primary PNG artifact;
- validation report artifact;
- creation timestamp.

### `PixelPanelApproval`

Required fields:

- approval identifier;
- candidate and panel identifiers;
- approve, reject, or supersede decision;
- approver, timestamp, reviewed artifact paths, and notes.

### `CompositeReviewSheet`

Required fields:

- sheet identifier and scope: `family` or `package_master`;
- family identifier for a family sheet, or the ordered family-sheet identifiers
  for the package master;
- ordered panel identifiers and their approved hashes for a family sheet;
- sheet artifact evidence;
- deterministic composition version;
- creation timestamp.

The composite contract is invalid if any included panel is not the active
approved candidate or any included family sheet is stale. Superseding a panel
invalidates and rebuilds its family sheet and the package master without
rewriting prior evidence.

### Package schema boundary

The pixel package is a backward-compatible `CharacterDesignPackage` revision
using schema version `1.1` and profile `pixel-talking-portrait`. It retains all
canonical version-1.0 directories and metadata while adding source locks and
panel-authoring metadata. Existing version-1.0 talking-bust packages continue
to validate without migration.

The generated package master sheet at
`references/master/master-character-sheet.png` is the sole
`package.json.master_reference`. It is a deterministic composition of the nine
current family sheets. The approved neutral panel is the identity and anchor
lock for dependent portrait panels, but it is not the package master reference.
Provenance connects the seven base-set inputs and the sealed technical source
package to each approved panel, each family sheet, and the package master.

## Package Layout

```text
juana-talking-bust-v2-pixel/
|-- package.json
|-- provenance.json
|-- approvals.json
|-- gaps.json
|-- seal.json
|-- sources/
|   |-- base-set/
|   `-- talking-bust-v1/
|-- references/
|   |-- master/
|   |   |-- master-character-sheet.png
|   |   `-- approved-sheets/
|   |-- presence-states/
|   |-- body/
|   |-- face/
|   |-- expressions/
|   |-- visemes/
|   |-- hair/
|   |-- outfit/
|   `-- materials/
|-- measurements/
|-- landmarks/
|-- palette/
|-- materials/
|-- expressions/
|-- visemes/
|-- hair/
|-- outfit/
|-- assets/
|-- adapters/
`-- authoring/
    |-- pixel-style.json
    |-- panel-definitions.json
    |-- anchor-profiles.json
    `-- composite-sheets.json
```

`sources/base-set` contains immutable copies of the seven creative-canon PNGs.
`sources/talking-bust-v1` contains a source lock and the sealed technical
references required to verify every `derived_from_sha256` relationship. The
original upstream package remains unchanged.

## Runtime Bundle Contract

The derived bundle is written separately from the sealed package:

```text
build/juana-pixel-portrait-runtime/juana-talking-bust-v2-pixel/
|-- portrait-manifest.json
|-- bundle-seal.json
|-- states/
`-- patches/
    |-- eyes/
    `-- mouth/
```

`portrait-manifest.json` contains:

- schema and character identifiers;
- canvas, logical pixel grid, pivot, and integer scale policy;
- texture filtering and alpha mode;
- state definitions and transitions;
- eye and mouth patch definitions;
- per-state anchor rectangles;
- speaking capability per state;
- required and optional asset hashes;
- fallback rules;
- reduced-motion behavior.

The manifest supports these presentation states:

- `neutral`;
- `listening`, mapped to neutral art;
- `thinking`;
- `explaining`;
- `approval`;
- `doubt`;
- `error`.

This state vocabulary preserves compatibility with the existing presence-layer
design. The viewer consumes explicit state events; it does not infer planner,
tool, authorization, or policy state.

The six expression-family panels are `authoring_only` in revision one. Only
the six presence-state panels compile into runtime states; `listening` aliases
the neutral state. Promoting an expression to a runtime state requires a new
approved package revision and an explicit manifest change.

## Layer and Animation Model

### Complete state panels

Presence states and approved emotions are complete pixel-art panels. This
preserves hands, head angle, hair silhouette, and outfit changes. A transition
uses a 120 to 160 millisecond ordered-dither dissolve without texture smoothing.

### Eye patches

Eye patches include enough surrounding skin pixels to replace the underlying
region without ghosting. Required frames are eyes open, eyes closed, blink
left, and blink right. Normal blinking uses discrete open and closed frames.
Asymmetric winks occur only in response to explicit viewer commands.

### Mouth patches

Mouth patches include enough surrounding skin pixels to replace the underlying
region without ghosting. Required frames are neutral, `aa`, `ih`, `ou`, `ee`,
and `oh`. The viewer accepts named viseme events and never invents missing
phonemes.

Each state declares whether it supports eye and mouth patches. Before audio
starts in a state without approved visemes, the viewer changes to `neutral` or
`explaining` according to the manifest fallback.

## Three.js Viewer

The viewer uses an orthographic camera and three depth regions:

1. a lit rear diorama containing environment planes, props, shadows, particles,
   and parallax;
2. a sharp portrait group containing the complete state panel, eye patch,
   mouth patch, and a palette-safe lighting shader;
3. restrained foreground props and shadows that never occlude the face or
   mouth.

The portrait uses nearest-neighbor sampling. A quantized shader applies a small
number of lighting steps so Three.js can integrate Juana with the environment
without blurring or replacing approved pixel colors. Depth of field applies to
the diorama, while the portrait remains on the focal plane.

The initial viewer is a local standalone demo inside this repository. It
provides controls for every state, blink mode, and viseme, along with an
automatic deterministic demonstration sequence. Integration with a production
UI remains a later cross-repository task.

## Error Handling and Recovery

- A failed or rejected panel does not invalidate other approved panels.
- Each provider request and moderation failure remains recorded as an attempt.
- The system never retries provider calls transparently.
- A panel that exhausts three attempts becomes an explicit blocking gap.
- A family sheet cannot be created while a required panel lacks an active
  approval.
- Superseding a panel preserves all historical candidates and invalidates the
  current composite sheet for that family.
- Package sealing fails for changed source hashes, incomplete rights,
  unapproved panels, stale composite sheets, unsafe paths, missing artifacts,
  or digest mismatches.
- Runtime validation fails for a missing manifest, neutral state, required
  texture, invalid anchor, or hash mismatch.
- Missing optional states degrade to neutral and emit a structured diagnostic.
- The viewer never replaces required missing assets with invented graphics.

## Validation and Testing

### Automated authoring gates

- Validate every input and output byte length, dimension, and SHA-256.
- Validate panel paths and containment.
- Validate family canvas, logical scale, and anchor contracts.
- Validate that every required panel has one active approved candidate.
- Validate that every review sheet references the active panel hashes exactly
  once and in fixed order.
- Validate alpha coverage and patch bounds for eye and mouth assets.
- Validate package provenance and rights chains.
- Validate the final seal offline.

### Human visual gates

- Approve the neutral master before any dependent panel becomes eligible for
  approval.
- Verify the younger base-set identity, viewer-left shave, viewer-right long
  hair, facial proportions, eye color, nose jewelry, and outfit treatment.
- Verify that every panel communicates its named view, expression, viseme, or
  material purpose.
- Verify that visemes remain distinct without changing eyes, brows, hairstyle,
  or apparent age.
- Review every family sheet for cross-panel identity and alignment drift.
- Review fixed Three.js captures to ensure the diorama does not reduce facial
  or mouth readability.

### Runtime tests

- Unit-test manifest parsing, fallbacks, state transitions, viseme mapping, and
  a fake-clock blink schedule.
- Integration-test texture loading, nearest filtering, state swaps, patch
  placement, and structured failures.
- Capture deterministic scenes at a fixed viewport and seed for neutral,
  closed eyes, `aa`, explaining, and optional-state fallback.
- Record frame-time evidence on the reference development machine. The target
  is 60 frames per second. A reduced-effects mode disables depth of field and
  particles while preserving the portrait, blinking, and lip sync.

WebGL captures are review evidence rather than a claim of byte-identical output
across different GPUs.

CI uses generated synthetic PNG fixtures and never depends on the personal
downloads path. Real authoring initialization copies and hashes the approved
source files into the ignored workspace before any provider call. Structural
manifest, hash, anchor, fallback, and sequencing assertions are gating;
WebGL captures and the 60-frames-per-second reference-machine measurement are
non-gating review evidence.

## Accessibility and Reduced Motion

- The host page exposes the current state as accessible text.
- Critical status remains available in the conversation UI and never depends
  only on animation or color.
- The viewer honors reduced-motion preferences by disabling ambient parallax,
  particles, pulse effects, and dither transitions.
- Necessary discrete mouth and eye frames remain available because they convey
  speech and character state rather than decorative camera motion.

## Delivery Order

### Slice 1 completion

- Panel-first contracts and tests are green.
- Base-set rights are complete.
- Every required pixel panel is approved.
- Every family sheet is composed and reviewed.
- The package master sheet is composed and reviewed.
- `juana-talking-bust-v2-pixel` is sealed and validates offline.

### Slice 2 completion

- Runtime assets and patches are compiled from approved panels.
- `portrait-manifest.json` is complete and hash-valid.
- The derived bundle records the sealed source package digest and leaves that
  package byte-for-byte unchanged.
- Structural, anchor, alpha, fallback, and loading tests are green.

### Slice 3 completion

- The local Three.js window loads the sealed runtime bundle.
- Every presence state, blink mode, and required viseme is demonstrable.
- The balanced HD-2D diorama and reduced-effects mode both work.
- Fixed captures and frame-time evidence are produced.

## Definition of Done

This design is delivered when the new pixel package contains all 49 approved
individual panels, nine deterministic family sheets, and one deterministic
master character sheet; the package and runtime bundle validate from their
recorded hashes; the local Three.js viewer demonstrates deterministic states,
blinking, and five visemes inside the approved balanced diorama; visual review
evidence exists; and the sealed 3D package remains byte-for-byte unchanged.

## Design Approval Record

Kathy approved the following decisions on 2026-07-21:

- balanced HD-2D diorama;
- fine pixel-art density;
- base-set identity and screen-facing orientation;
- complete pixelization of all technical reference panels;
- a separate new 2D package while retaining the existing package for VRM work;
- panel-first authoring plus deterministic composite sheets;
- complete state panels with localized eye and mouth patches;
- additive contracts, runtime manifest, validation strategy, and three-slice
  delivery order.
