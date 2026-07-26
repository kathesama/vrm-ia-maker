# Juana Pixel Portrait Runtime Contract

## Purpose

The Juana pixel portrait runtime is a framework-neutral, build-time asset
bundle. It supplies deterministic scenario, presence-state, eye, and mouth
plates to a host UI. It does not own conversational behavior, voice processing,
scenario selection policy, or autonomous decisions.

The GH-24 build is generated locally at:

```text
build/juana-pixel-portrait-runtime/juana-talking-bust-v2-pixel-ui-ready/
```

The versioned release source consumed by downstream automation is:

```text
packages/juana-pixel-runtime/v2/runtime/
```

`portrait-manifest.json` is the canonical registry and `bundle-seal.json`
contains the SHA-256 digest of every other runtime file.

The sibling `juana-pixel-runtime-v2.lock.json` identifies the deterministic ZIP
and records the verified runtime inventory. The release source contains 55
files, including all 51 runtime PNG assets. The 352-image authoring catalog is
not part of this contract.

## Stable IDs

| Type | IDs |
|---|---|
| Scenario | `juana-diorama-room`, `juana-workstation` |
| Eye | `open`, `closed`, `blink-left`, `blink-right` |
| Mouth | `neutral`, `aa`, `ih`, `ou`, `ee`, `oh` |

The manifest keeps `juana-diorama-room` as both the default and
`recommended_ui_scenario`. `juana-workstation` remains available as the
separate Scenario 2.

## Host Library Boundary

The later Juana UI adapter should expose one small controller:

```ts
interface JuanaPixelPortraitController {
  setScenario(id: string): Promise<boolean>;
  setState(id: string): Promise<boolean>;
  setEye(id: "open" | "closed" | "blink-left" | "blink-right"): boolean;
  setMouth(id: "neutral" | "aa" | "ih" | "ou" | "ee" | "oh"): boolean;
  destroy(): void;
}

interface JuanaPixelPortraitOptions {
  container: HTMLElement;
  runtimeBaseUrl: string;
  initialScenario?: string;
  reducedMotion?: boolean;
}
```

The adapter belongs in the production UI repository as an ordinary library or
UI component. A microfrontend is unnecessary because the runtime has no
independent deployment, routing, authentication, or domain state.

## Loading And Integrity

1. Load `portrait-manifest.json` and `bundle-seal.json` from the same immutable
   runtime base URL.
2. Verify the manifest SHA-256 against the seal.
3. Resolve only relative paths declared by the selected manifest scenario.
4. Verify every asset before creating its texture.
5. Preload all target-scenario assets before committing a scenario change.
6. If an ID is unknown, a request fails, or a hash differs, retain the current
   valid scenario and report a recoverable error to the host.

The standalone viewer implements this transaction in `loadScenarioAssets` and
`setScenario`.

## Rendering

- Use sRGB color space, nearest-neighbor magnification and minification, no
  mipmaps, and clamp-to-edge wrapping.
- Keep eye and mouth plates coplanar with the base portrait and use the same
  shader and color path.
- `portrait-over-environment` renders the portrait above its declared static
  environment.
- `baked-scene` renders the approved full-canvas scene without additional
  relighting, color correction, scanlines, parallax, or ambient bob.
- Baked non-neutral states must preserve the neutral scene byte for byte outside
  the scenario's declared `facial_state_rect`; state changes must not shift the
  camera, crop, body, lighting, or background.
- Mouth and viseme masks must cover the complete upper and lower lip silhouette;
  a mask boundary must not truncate either lip edge or overwrite the neutral
  chin region.
- Respect `prefers-reduced-motion`; state, eye, and mouth commands remain
  available while decorative motion is disabled.

## Ownership

The host UI owns the mapping from application events to controller commands.
For example, the voice layer may map phonemes to viseme IDs, but the pixel
runtime neither receives audio nor interprets speech. Three.js owns only
deterministic loading, state changes, blinking, visemes, and rendering.

The avatar repository owns the canonical sealed runtime and deterministic
release lock. Jira story JAP-1131 owns the generated deployment copy under
`juana-pwd-ui/public/assets/juana/pixel-v2`. That copy must be refreshed through
hash-verifying automation and must not become an independent visual source of
truth.

## Approval Boundary

Scenario 2 is an approved runtime slice with explicit provenance. The broader
49-panel authoring catalog remains review-gated, and this runtime does not seal
or replace the V1 CharacterDesignPackage or the future VRM.
