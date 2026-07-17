# Character Design Package Authoring Workflow

## Purpose

This document defines how an approved visual design becomes a measurable, versioned,
traceable input for `vrm-ia-maker`.

The target product is a reproducible build that produces:

```text
dist/juana/juana.vrm
```

The final VRM must be valid VRM 1.0, load through `@pixiv/three-vrm`, and preserve the
approved identity, proportions, expressions, visemes, materials, hair, outfit, and
runtime behavior of Juana.

## Product invariant

> A master character sheet is creative canon, not executable geometry.

A character sheet may define identity, silhouette, styling, palette, mood, outfit,
and intended proportions. It must not be treated as a metrically exact 3D source when
it contains perspective, inconsistent poses, changing proportions, stylized anatomy,
or missing views.

No production geometry, morph target, attachment, or material may be treated as
measured fact unless the package contains an explicit approved source for it.

When required information is missing, the pipeline must report a gap. It must never
invent dimensions, landmarks, hidden geometry, or legal provenance.

## Source classes

Every input must be assigned one of the following source classes.

### 1. Creative canon

Creative canon defines what the character must look and feel like.

Examples:

- master character sheet;
- approved portrait;
- approved outfit concept;
- approved palette;
- atmosphere and presentation references;
- narrative character notes.

Creative canon is authoritative for identity and art direction. It is not automatically
a geometric source of truth.

### 2. Technical reference

Technical reference is prepared for measurement and reconstruction.

Examples:

- orthographic front, side, and back views;
- A-pose or T-pose body turnaround;
- neutral face front and profile;
- aligned facial landmarks;
- body measurement table;
- material swatches with numeric values;
- expression and viseme sheets;
- hair construction diagrams;
- outfit seam and layer diagrams.

Technical references must declare units, camera assumptions, alignment rules, and
approval status.

### 3. Production asset

A production asset is an executable 3D or material input.

Examples:

- base body GLB;
- head mesh;
- hair mesh;
- skinned outfit mesh;
- accessory mesh;
- texture maps;
- Blender source file;
- validated morph-target source.

Every production asset must have provenance, license, checksum, and compatibility
metadata before it enters a build.

## Minimum package

A package is minimally usable for a non-final prototype when it contains:

```text
- one approved master character sheet;
- one approved neutral face front view;
- one approved face profile view;
- one approved body front view;
- one approved body side view;
- one approved body back view;
- one A-pose or T-pose reference;
- declared character height;
- approved palette;
- approved outfit reference;
- approved hair reference;
- required expression list;
- required viseme list;
- provenance and license metadata for every file.
```

A minimally usable package may still produce explicit warnings and may be restricted
to a bust milestone rather than a full-body production build.

## Recommended package

A production-ready package should contain:

```text
body
  - orthographic front
  - orthographic left side
  - orthographic right side
  - orthographic back
  - A-pose front and back
  - T-pose front and back when arm deformation is in scope
  - body measurements
  - body landmarks

face
  - neutral front
  - neutral left profile
  - neutral right profile
  - left and right three-quarter views
  - eyes open
  - eyes closed
  - jaw open
  - brow and eyelid reference
  - facial landmarks
  - facial measurements

expressions
  - neutral
  - happy
  - sad
  - angry
  - surprised
  - relaxed
  - approved project-specific expressions

visemes
  - aa
  - ih
  - ou
  - ee
  - oh
  - neutral mouth

hair
  - silhouette front, side, and back
  - hairline
  - parting direction
  - rigid and dynamic sections
  - expected spring-bone groups
  - collision expectations

outfit
  - front, side, and back
  - layer order
  - seams and closures
  - rigid versus deforming regions
  - attachment points
  - material assignments

materials
  - numeric base colors
  - metallic values
  - roughness values
  - normal-map policy
  - transparency policy
  - emission policy
  - texture color-space declarations
```

## Reference image rules

### Orthographic views

Orthographic references should:

- use a neutral camera without perspective exaggeration;
- preserve the same character proportions across views;
- use the same scale and canvas alignment;
- place the character on the same baseline;
- show the complete silhouette;
- avoid foreshortening;
- avoid pose changes between views;
- identify left and right explicitly.

### Pose

The preferred body construction pose is an A-pose because it provides useful shoulder
and armpit topology while staying close to a natural resting pose.

A T-pose may be required when:

- arm deformation must be inspected independently;
- outfit sleeve topology needs a clear neutral state;
- a source rig or adapter expects a T-pose;
- retargeting compatibility requires it.

The package must state which pose is canonical for modeling, rigging, and adapter
validation. Codex must not silently switch between A-pose and T-pose assumptions.

### Perspective and stylization

When a source contains perspective or stylized anatomy:

- preserve it as creative canon;
- mark it as non-metric;
- do not derive hidden measurements from it;
- use it only to constrain identity, silhouette, and art direction;
- require a technical reference or explicit approved measurement before converting it
  into production geometry.

## Measurement model

All measurements must use SI units.

Canonical units:

```text
length: meters in production contracts
human-readable authoring: centimeters allowed
angles: degrees in authoring, converted explicitly when required
color: linear or sRGB must be declared
weights: normalized 0.0 to 1.0
```

At minimum, body measurements should include:

```text
height
shoulder width
chest circumference
waist circumference
hip circumference
inseam
arm length
upper-arm circumference
thigh circumference
head height
head width
neck circumference
```

At minimum, facial measurements should include:

```text
interpupillary distance
face height
face width
jaw width
nose length
mouth width
eye width
eye opening height
brow-to-eye distance
chin-to-mouth distance
```

Every measurement must declare:

```text
name
value
unit
source file or source record
approval state
confidence
notes
```

## Landmark model

Landmarks must use stable canonical names and normalized image coordinates when they
refer to 2D references.

Recommended facial landmark groups:

```text
pupils
inner and outer eye corners
upper and lower eyelid centers
brow inner, center, and outer points
nose bridge
nose tip
nostril outer points
mouth corners
upper-lip center
lower-lip center
chin
jaw angles
cheek maxima
hairline center and temples
```

Recommended body landmark groups:

```text
crown
chin
shoulder joints
elbows
wrists
sternum
navel
waist left and right
hip joints
knees
ankles
heels
toe tips
```

A landmark must never be inferred from an occluded region without an approved source.

## Package layout

The canonical package layout is:

```text
character-design-package/
├── package.json
├── provenance.json
├── approvals.json
├── gaps.json
├── references/
│   ├── master/
│   │   └── master-character-sheet.png
│   ├── body/
│   │   ├── front.png
│   │   ├── left.png
│   │   ├── right.png
│   │   ├── back.png
│   │   ├── a-pose-front.png
│   │   └── a-pose-back.png
│   ├── face/
│   │   ├── neutral-front.png
│   │   ├── left-profile.png
│   │   ├── right-profile.png
│   │   ├── left-three-quarter.png
│   │   └── right-three-quarter.png
│   ├── expressions/
│   │   ├── neutral.png
│   │   ├── happy.png
│   │   ├── sad.png
│   │   ├── angry.png
│   │   ├── surprised.png
│   │   └── relaxed.png
│   ├── visemes/
│   │   ├── aa.png
│   │   ├── ih.png
│   │   ├── ou.png
│   │   ├── ee.png
│   │   └── oh.png
│   ├── hair/
│   ├── outfit/
│   └── materials/
├── measurements/
│   ├── body.json
│   └── face.json
├── landmarks/
│   ├── body.json
│   └── face.json
├── palette/
│   └── palette.json
├── materials/
│   └── materials.json
├── expressions/
│   └── expressions.json
├── visemes/
│   └── visemes.json
├── hair/
│   └── hair.json
├── outfit/
│   └── outfit.json
├── assets/
│   ├── base/
│   ├── hair/
│   ├── outfit/
│   └── accessories/
└── adapters/
    └── base-model-adapter.json
```

The package manifest must be versioned. Paths must be relative to the package root.
Every referenced file must have a SHA-256 digest and provenance record.

## Required metadata

`package.json` must define at least:

```text
schema_version
package_id
character_id
display_name
revision
created_at
updated_at
canonical_pose
height_meters
master_reference
required_expressions
required_visemes
asset_pack_manifest
assembly_manifest
base_model_adapter
```

`provenance.json` must define, for every source and asset:

```text
path
sha256
byte_length
author
source
license
commercial_use
modification_allowed
redistribution_allowed
created_at or acquired_at
```

`approvals.json` must identify:

```text
approved item
approval state
approver
approval timestamp
scope of approval
notes
```

`gaps.json` must identify unresolved information explicitly:

```text
gap_id
category
required_for
severity
known information
missing information
blocking state
resolution owner
```

## Quality gates

### Gate 1: Package integrity

Before visual analysis:

- package schema is supported;
- all paths are contained within the package root;
- all files exist;
- all hashes match;
- all provenance records are complete;
- all licenses satisfy `ASSET_POLICY.md`;
- no unapproved source is marked as production-ready.

### Gate 2: Reference completeness

Before geometric planning:

- required views exist;
- canonical pose is declared;
- height and units are declared;
- left and right are unambiguous;
- measurement and landmark gaps are recorded;
- creative references are classified as metric or non-metric.

### Gate 3: Cross-view consistency

Before base adaptation or modeling:

- proportions are consistent across technical views;
- baseline and scale are consistent;
- landmark correspondence is valid;
- outfit and hair silhouettes do not contradict the body references;
- unresolved contradictions are blocking gaps.

### Gate 4: Base-model compatibility

Before Blender modification:

- the base asset passes `BaseModelAdapter` validation;
- required bones are mapped;
- required morph-target sources are available or explicitly scheduled;
- body proportions can be reached without destructive topology assumptions;
- outfit and hair strategies are declared;
- licensing permits the intended output.

### Gate 5: Authoring readiness

Before Blender writes production geometry:

- approved technical references are frozen for the revision;
- target measurements are complete enough for the active milestone;
- the active milestone is declared as bust or full body;
- required expressions and visemes have source references;
- material inputs have numeric values;
- all unresolved blocking gaps are closed.

## Milestone profiles

### Talking bust milestone

The first useful Juana milestone requires:

```text
head
neck
upper torso
eyes
jaw
hair
visible outfit
blink
blinkLeft
blinkRight
aa
ih
ou
ee
oh
approved emotional expressions
look-at
required hair spring bones and colliders
```

For this milestone, lower-body references may remain non-blocking, but they must still
be recorded as gaps for the full-body milestone.

### Full-body milestone

The full-body milestone additionally requires:

```text
complete humanoid body
hands and feet
full outfit deformation
full-body measurements
full-body landmarks
complete collision strategy
full-body motion validation
```

## Production workflow

The authoritative workflow is:

```text
approved creative canon
        -> technical reference preparation
        -> package integrity validation
        -> cross-view consistency validation
        -> measurement and landmark approval
        -> base-model compatibility analysis
        -> Blender base adaptation and modeling
        -> Blender rigging and skinning
        -> Blender morph-target authoring
        -> modular asset assembly
        -> Three.js composition inspection
        -> Blender VRM 1.0 finalization
        -> structural VRM validation
        -> @pixiv/three-vrm consumer validation
        -> renders and approval review
        -> dist/juana/juana.vrm
```

## Bounded talking-bust reference authoring

The initial production authoring profile can start from one approved master character
sheet, including a composite sheet such as
`examples/Juana-full-concept-white.png`. The master remains creative canon. Generated
views are technical reference candidates and never become measurements, landmarks, or
hidden geometry merely because an image provider produced them.

The profile runs these fixed tasks in order:

1. face turnaround;
2. facial mechanics;
3. upper-body turnaround;
4. expressions;
5. visemes;
6. hair construction;
7. outfit construction;
8. material reference.

Each task has its own versioned prompt, exact PNG size, grid, dependencies, and panel
destinations. Every request includes only approved predecessor sheets and the master
character sheet. One explicit `run` command makes at most one provider request, and
each task allows no more than three recorded attempts. A generated sheet cannot unlock
its dependents until a named human reviewer approves both the sheet and every
deterministic panel preview.

If later human direction contradicts an active approval, the reviewer may supersede it
after every dependent candidate is resolved. Superseding retains the original approval,
candidate files, hashes, and provenance, marks that candidate as historical, and reopens
the task within its existing attempt bound. Only the current active approval can enter a
sealed package. No approval or attempt history is deleted or rewritten.

The internal command surface is:

```text
python -m vrm_ia_maker.design.cli init ...
python -m vrm_ia_maker.design.cli set-rights ...
python -m vrm_ia_maker.design.cli run ...
python -m vrm_ia_maker.design.cli status ...
python -m vrm_ia_maker.design.cli approve ...
python -m vrm_ia_maker.design.cli reject ...
python -m vrm_ia_maker.design.cli supersede ...
python -m vrm_ia_maker.design.cli validate ...
python -m vrm_ia_maker.design.cli seal ...
```

`set-rights` completes every required master-source rights field on an existing
workspace and removes only the corresponding blocking gap. Complete rights are
immutable for that package revision; correcting them requires a new revision rather
than overwriting legal evidence.

The ignored authoring workspace retains raw and rejected candidates, malformed provider
output when bytes are returned, candidate prompt identifiers and versions, hashes, error
details, and decisions for audit. Sealing copies only approved sheets and approved crops
to a new CharacterDesignPackage destination. It refuses incomplete source rights,
unresolved visual-seal gaps, changed hashes, unsafe paths, or an existing destination.

Online image generation is optional authoring infrastructure. It is not automatic
artistic approval, automatic legal clearance, 3D reconstruction, or avatar runtime
behavior. Once the visual package is sealed, all downstream validation, Three.js work,
Blender work, and VRM runtime behavior contain no image-provider calls.

Provider moderation failures remain recorded attempts and are never retried
transparently. A garment-construction candidate may isolate the visible garment on an
opaque technical mannequin when a realistic worn rendering is rejected, while the
master remains authoritative for the final worn appearance. That isolation does not
authorize hidden closures, unseen surfaces, anatomy, or production geometry.

## Responsibility map

### CharacterDesignPackage

Owns:

- approved visual intent;
- measurable references;
- package revision;
- provenance;
- licenses;
- approvals;
- explicit gaps.

Does not own:

- Blender implementation details;
- runtime animation state;
- inferred hidden geometry.

### Three.js

Owns:

- asset inspection;
- composition selection;
- manifest compilation;
- preview composition;
- final consumer validation.

Does not own:

- final geometry authoring;
- rigging;
- skinning;
- final VRM export.

### Blender

Owns:

- geometry creation and adaptation;
- rigging;
- skinning;
- morph targets;
- hair and outfit authoring;
- spring bones and colliders;
- final VRM 1.0 export.

Blender remains the last writer of the distributed `.vrm` file.

## Codex execution rules

Codex must follow these rules when implementing package support:

1. Read this document before naming or implementing `CharacterDesignPackage`
   contracts.
2. Treat the master character sheet as creative canon unless a file is explicitly
   marked as metric technical reference.
3. Never derive hidden dimensions from perspective art.
4. Never silently normalize contradictions between views.
5. Record missing or contradictory information in `gaps.json`.
6. Fail before Blender when a blocking gap affects the active milestone.
7. Preserve hashes, provenance, approvals, and license metadata through every
   compiled handoff.
8. Keep Three.js responsible for selection and consumer validation.
9. Keep Blender responsible for geometry and final VRM export.
10. Do not claim `juana.vrm` exists unless a real file was produced and validated.

## Explicit non-goals

The package does not promise:

- automatic professional 3D reconstruction from one image;
- automatic recovery of hidden anatomy;
- automatic legal clearance of source images or assets;
- automatic approval of artistic deviations;
- runtime AI control inside the avatar;
- replacement of human visual review for the final Juana identity.

## Definition of done

A `CharacterDesignPackage` revision is ready for production authoring only when:

- its schema is valid;
- its references are classified;
- its required files are present;
- its hashes match;
- its provenance and licenses are complete;
- its active milestone is declared;
- its measurements and landmarks are sufficient for that milestone;
- its contradictions and missing data are captured;
- it has no unresolved blocking gaps;
- its approved revision is immutable for the duration of the build.
