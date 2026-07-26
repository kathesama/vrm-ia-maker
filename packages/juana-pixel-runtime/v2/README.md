# Juana Pixel Runtime V2

This directory is the canonical release source for Juana's V2 pixel portrait
runtime. The UI copy is generated from this directory; it is not an independent
visual source of truth.

## Contents

```text
v2/
├── runtime/                              # sealed browser runtime
├── juana-pixel-runtime-v2.lock.json      # derived release identity
└── README.md
```

The runtime contains 55 files:

- 51 PNG assets;
- `portrait-manifest.json`;
- `bundle-seal.json`;
- one provenance record for each of the two scenarios.

The 352-image authoring catalog under `output/authoring/` is deliberately
excluded. It is review and generation material, not a browser dependency.

Open `gallery.html` to inspect all 51 PNG files grouped into both current
scenarios and the legacy compatibility set. Scenario eye and mouth plates are
composited over their matching neutral scene for easier review. The gallery is
outside `runtime/`, so it does not alter the sealed delivery inventory. Its
WebP previews are embedded so the file can be opened directly through `file:///`
without a local web server.

Refresh the embedded previews after changing a sealed PNG:

```powershell
python tools/build_pixel_runtime_gallery.py
```

## Storage

Runtime PNG files use the path-scoped Git LFS rule in `.gitattributes`. JSON,
documentation, source code, and tests remain ordinary Git content. The local
ZIP is a reproducible build artifact under the ignored `build/` root and is not
committed.

## Verification and packaging

From the repository root:

```powershell
$env:PYTHONPATH='src'; python -m vrm_ia_maker.design.pixel_portrait.cli package-runtime --source packages/juana-pixel-runtime/v2/runtime --output build/releases/juana-pixel-runtime-v2.zip --lock packages/juana-pixel-runtime/v2/juana-pixel-runtime-v2.lock.json --version 2.0.0
```

The command verifies every file against `bundle-seal.json` before writing the
archive. ZIP paths are sorted and use fixed timestamps, permissions, and
compression settings. Repeating the command with unchanged inputs produces the
same archive SHA-256.

To refresh the canonical directory from a separately restored, sealed build:

```powershell
$env:PYTHONPATH='src'; python -m vrm_ia_maker.design.pixel_portrait.cli sync-runtime --source build/juana-pixel-portrait-runtime/juana-talking-bust-v2-pixel-ui-ready --destination packages/juana-pixel-runtime/v2/runtime
```

The source is fully verified before the destination can be replaced.

## Consumer boundary

Jira story JAP-1131 owns the verified synchronization into
`juana-pwd-ui/public/assets/juana/pixel-v2`. The UI must pin
`juana-pixel-runtime-v2.lock.json`, verify the runtime seal, and keep its
existing six static portraits as a recoverable fallback.

The future React/Three.js library, event-to-state mapping, audio clock, and
viseme scheduling are separate delivery slices.

## Rights and approval

Scenario-specific provenance and rights attestations are stored inside each
`runtime/scenarios/<scenario-id>/provenance.json`. Packaging preserves all
visual and approval metadata exactly; it does not promote review-gated
expressions or modify the approved image bytes.
