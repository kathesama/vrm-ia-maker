# Clean Juana Production Checkpoint

This directory contains the deterministic GH-22 route for building one clean,
rig-compatible Juana character from traceable, mutually exclusive donors.

The route is provisional. It produces an editable Blender file, topology and
transfer evidence, and a GLB inspected through Three.js. It does not write
`dist/juana/juana.vrm`, approve visual canon, or claim expression, garment, or
final VRM parity.

## Source Roles

- The existing provisional VRM supplies humanoid-contract, metadata, exporter,
  and validation evidence only. Its visible procedural meshes stay in
  `_DONOR_VRM` and never enter `_EXPORT`.
- `person_5.glb` supplies body shape and proportion evidence only. The
  preprocessing step retains the named `HumanMesh`, excludes 173 auxiliary
  meshes, normalizes it, and stores it in `_REFERENCE_SAM3D`.
- `Torso - busto.glb` supplies facial likeness, hair and outfit silhouette, and
  texture-bake evidence only. Its immutable 1,363,714-triangle mesh stays in
  `_REFERENCE_HIGHPOLY` and is never rigged or exported.
- The MPFB-derived production topology is the only visible and exportable
  character geometry.

The rejected donor overlay is preserved only at
`artifacts/debug/invalid-donor-overlay.blend`. It is not an authoring input.
Raw SAM 3D and high-poly donor copies are staged under the ignored
`build/local-donors/` directory so the active evidence contains no
machine-specific absolute paths. Their byte lengths and digests must match
`source-evidence.json` exactly.

## Scene Contract

Non-exportable collections:

```text
_REFERENCE_SAM3D
_REFERENCE_HIGHPOLY
_DONOR_VRM
```

Production collections:

```text
_PRODUCTION_BODY
_PRODUCTION_HEAD
_PRODUCTION_HAIR
_PRODUCTION_OUTFIT
_RIG
_EXPORT
```

The clean author starts from an empty Blender file, normalizes source
transforms, uses SAM 3D for height and band evidence, and constrains the
production body with the approved athletic hourglass profile. The production
head uses explicit eye landmarks, cage deformation, and a controlled masked
shrinkwrap. The high-poly texture is baked through a filtered face helper.
Because the fused donor has discontinuous skin, hair, and outfit UV fragments,
the bake remains evidence and the production material uses the checksummed
approved package skin reference instead.

The checkpoint contains one production body, one production head, two separate
eyes, one functional jaw, one humanoid rig, asymmetric hair, and outfit
blockouts. Expressions, spring bones, colliders, and clothing polish remain
deferred until Kathy approves the visual and topology checkpoint.

## Export Gate

`production_gate.py`, the Blender validator, and the Three.js inspector fail
closed when:

- a `_REFERENCE_*` or `_DONOR_*` object is exportable;
- more than one production body or head is renderable;
- production body and head do not bind to the same rig;
- donor names or procedural spike geometry survive the GLB;
- a production root transform is not applied;
- waist-to-hip silhouette ratios or the warm medium skin value regress outside
  the approved checkpoint bounds;
- required collections, eyes, jaw, renders, comparisons, or inventory evidence
  are missing.

## Build

From the repository root:

```powershell
python tools/juana_bust/build_preview.py
```

To rerun validation and comparison generation without reauthoring:

```powershell
python tools/juana_bust/build_preview.py --skip-authoring
```

The build verifies the pinned toolchain, approved references, all three raw
donors, and the normalized SAM reference before Blender starts. It then authors
the scene, reopens it for Blender validation, loads the GLB with Three.js
`GLTFLoader`, creates fixed comparison sheets, and writes a checksummed report.

## Outputs

All active outputs remain under the ignored
`build/juana-clean-production-preview/` directory:

```text
juana-clean-production-provisional.blend
juana-clean-production-provisional.glb
scene-report.json
production-fit-report.json
exported-mesh-inventory.json
blender-validation.json
three-inspection.json
build-report.json
renders/
comparisons/
textures/
```

Primary review evidence:

- `comparisons/review-board.png`
- `comparisons/sam3d-vs-production-body.png`
- `comparisons/highpoly-vs-production-head.png`
- `comparisons/front-landmark-overlay.png`
- `renders/wireframe.png`
- `exported-mesh-inventory.json`

The checkpoint must not be treated as approved visual canon or a final VRM
until Kathy records the visual and topology decision.
