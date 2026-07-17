# Provisional Juana Bust Tracer Bullet

This directory contains the deterministic GH-22 authoring and validation route
for the first concrete Juana 3D visual checkpoint.

The route is intentionally provisional. It produces an editable Blender file,
five fixed comparison renders, and a GLB for structural inspection. It does not
write `dist/juana/juana.vrm`, approve visual canon, or claim production VRM
parity.

## Inputs

- `toolchain-lock.json` pins Blender 4.2.0, MPFB 2.0.16, the MakeHuman hm08
  base and rig, and every CC0 system asset used by the checkpoint.
- `source-evidence.json` pins the approved Juana master reference, sealed
  character-design-package views, rights evidence, visible design facts, and
  reversible visual assumptions.
- `render-manifest.json` fixes the renderer, resolution, cameras, framing, and
  reference image for each review angle. It also records the deterministic PNG
  canonicalization that strips volatile Blender metadata and clears two
  insignificant RGB bits after rendering.
- `examples/juana-bust/base-adapter.json` maps the MPFB default rig and initial
  expression targets through the existing production adapter schema.

The anatomical left side is the close-cut side. The anatomical right side
carries the long hair and must obscure the right profile. This convention is
fixed in the evidence and render manifest; image-space left and right must not
be substituted for anatomical sides.

## Local Toolchain

The locked binaries and CC0 assets live under `build/local-toolchain/` and are
not committed. Every build verifies their byte lengths and SHA-256 digests
before Blender starts. The exact isolated MPFB installation is additionally
verified by a stable tree digest, excluding only generated Python bytecode. A
missing or modified artifact fails closed.

The authoritative source URLs, versions, licenses, and checksums are recorded
in `toolchain-lock.json`. The build performs no network access and MPFB online
access remains disabled.

## Build

From the repository root:

```powershell
python tools/juana_bust/build_preview.py
```

To rerun validation and comparisons without reauthoring the scene:

```powershell
python tools/juana_bust/build_preview.py --skip-authoring
```

The default route:

1. verifies all locked toolchain and approved reference inputs;
2. authors the human base and Juana-specific provisional changes in Blender;
3. saves the editable `.blend` and exports a provisional `.glb`;
4. renders five deterministic 1024-by-1024 views;
5. reopens the `.blend` and validates the rig, separate eyes, jaw action,
   complete base-adapter mapping, expression morphs, cameras, renders, and GLB
   container;
6. loads the GLB through Three.js `GLTFLoader` and validates its skin, bones,
   objects, morph targets, and exported base-adapter mapping;
7. writes fixed reference-versus-render comparisons and a checksummed build
   report.

## Outputs

All outputs remain under the ignored `build/juana-bust-preview/` directory:

```text
juana-bust-provisional.blend
juana-bust-provisional.glb
scene-report.json
blender-validation.json
three-inspection.json
build-report.json
renders/
comparisons/
```

`comparisons/review-board.png` is the visual-canon checkpoint for Kathy.
Provisional geometry must not be merged as approved canon until that review is
recorded.
