# Juana Baked Diorama Visual Target Design

**Status:** Awaiting written specification review; visual target approved  
**Date:** 2026-07-23  
**Design approver:** Kathy  
**Repository:** `kathesama/vrm-ia-maker`

## Decision Summary

Use the approved baked diorama composition as the visual target for Juana's
pixel talking portrait. The character, environment, foreground occlusion,
shadows, and color grade must appear to come from one authored scene.

Three.js must not independently relight Juana's already shaded body or white
jacket. The rejected relighting experiments produced unstable colored regions
because they applied new simulated light over an image that already contained
baked shading. The runtime will instead preserve baked character lighting and
limit live composition to deterministic state selection, facial animation, and
restrained scene effects that do not recolor the portrait.

This design refines the viewer section of
`2026-07-21-juana-pixel-talking-portrait-design.md`. It does not replace that
document's identity, panel-first authoring, review, provenance, or package
boundaries.

## Approved Evidence

The approved visual reference is stored outside the V2 authoring package:

```text
output/experiments/juana-baked-diorama-v1/
  README.md
  juana-baked-diorama-approved.png
```

The PNG is 1032 by 1523 pixels with SHA-256:

```text
15e45d57ffeb32cfc09e242c622d3ef862b7579c3195ffaf4dd2406f3047eda4
```

The visual approval covers:

- Juana facing forward with relaxed, gently clasped hands;
- the shaved side on the viewer's left and long hair on the viewer's right;
- Juana's apparent scale and placement in the rear-middle of the room;
- the foreground platform naturally occluding the lower body;
- broad warm light from the hanging lamp;
- restrained cool environmental bounce;
- coherent contact and cast shadows;
- shared atmosphere, contrast, black levels, pixel density, and color grade;
- natural jacket shading without colored patches, outline glow, or chroma
  fringes.

The approval does not promote the PNG into the sealed package, approve the
remaining 48 provisional catalog panels, or close source-rights gates.

## Chosen Approach

### Rejected approach: live portrait relighting

Do not generate pseudo-normal maps from the portrait silhouette and do not
apply per-region red, amber, cyan, or gray lighting masks to the jacket. Those
techniques create double-lighting artifacts and unstable color islands.

### Approved approach: baked scene plate with co-registered facial animation

The first production milestone uses one full-scene neutral plate as the stable
visual base. The room, Juana's body, neutral face, projected shadows, contact
shadows, and foreground occlusion are baked together.

Eyes and mouth are the only live facial regions in the initial talking state.
Their frames must be authored from the same lit neutral source, at the same
coordinates, pixel scale, palette, and color grade. They are replacement
plates, not independently shaded stickers.

Complete pose or presence-state changes remain complete panels. A future state
is eligible for runtime use only after it has its own approved scene-integrated
plate or an equivalently validated baked character plate. The viewer must not
invent missing state art.

## Runtime Architecture

The runtime has three bounded responsibilities:

1. **Scene plate renderer**
   - Loads the approved full-scene neutral plate.
   - Uses nearest-neighbor sampling and deterministic framing.
   - Preserves the baked lighting exactly.

2. **Facial plate compositor**
   - Replaces fixed eye and mouth rectangles using co-registered frames.
   - Keeps all facial plates coplanar with the scene image.
   - Applies no per-layer parallax, dynamic lighting, blur, or independent
     color correction.
   - Falls back to the neutral frame when a requested plate is missing or
     invalid.

3. **Restrained environment effects**
   - May add low-amplitude particles, subtle whole-scene breathing, or a shared
     final color transform when explicitly enabled.
   - Must not alter the jacket, face, or hair independently.
   - Must respect reduced-motion and reduced-effects modes.

When production UI integration occurs, it should consume a small deterministic
Three.js module or library. A microfrontend is unnecessary for this rendering
boundary. The module receives state, blink, and viseme commands and emits
readiness and structured error events; it owns no conversational, TTS, STT,
agent, or decision logic.

## Data and Asset Flow

1. Keep the 49-panel authoring catalog and its approvals unchanged.
2. Select only approved panels for runtime derivation.
3. Produce a scene-integrated neutral plate using the approved composition as
   the visual target.
4. Derive eye and mouth replacement plates from that same lit source.
5. Validate dimensions, coordinates, alpha coverage, palette continuity, and
   hashes.
6. Compile only the validated runtime plates and manifest into the preview
   bundle.
7. Render them without portrait-specific relighting.

The experimental PNG remains reference evidence until a production ticket
explicitly promotes or reproduces it through the repository's provenance,
rights, and sealing workflow.

## Failure Behavior

- A missing or hash-invalid scene plate prevents the viewer from entering the
  ready state.
- A missing eye or mouth frame falls back to the neutral frame and emits a
  structured diagnostic.
- A plate with wrong dimensions, coordinates, pixel scale, or source identity
  is rejected before rendering.
- A facial plate that creates a visible palette seam or color discontinuity
  fails the visual review gate.
- Unsupported presence states remain unavailable; the viewer never fabricates
  or silently substitutes a complete pose.

## Validation

### Automated checks

- Verify the scene plate and every facial plate by SHA-256.
- Verify identical canvas dimensions and fixed eye and mouth rectangles.
- Verify nearest-neighbor texture settings and coplanar layer placement.
- Verify that no portrait-specific lighting shader or clothing color mask is
  active.
- Verify neutral fallbacks for missing optional facial frames.
- Capture deterministic neutral, closed-eye, and required-viseme frames.

### Human visual checks

- Compare fixed captures with
  `juana-baked-diorama-approved.png`.
- Confirm that Juana appears positioned inside the room rather than pasted over
  it.
- Confirm the approved hair orientation, youthful identity, pose, and scale.
- Confirm natural foreground occlusion and coherent shadow direction.
- Confirm that the white jacket has continuous warm/cool modeling with no
  colored patches, halos, or chroma fringes.
- Confirm that eye and mouth changes introduce no visible rectangular seams,
  palette jumps, or face drift.

## Scope Boundaries

### In scope for the next implementation plan

- Preserve the approved experiment as immutable visual evidence.
- Define the production scene-plate and facial-plate manifest contract.
- Remove portrait-specific relighting from the viewer path.
- Compile and demonstrate the neutral scene with blinking and required visemes.
- Add deterministic capture and validation evidence.

### Out of scope

- Modifying `juana-talking-bust-v1` or the future VRM.
- Claiming approval for the other 48 provisional panels.
- Regenerating every complete presence state in this first integration slice.
- Integrating the viewer into Juana's production UI before the standalone
  runtime contract is validated.
- Adding conversational, voice, or autonomous behavior to the renderer.

## Definition of Done

The refinement is complete when the standalone viewer reproduces the approved
scene-integrated direction for the neutral talking state; blinking and visemes
use co-registered plates without seams or color changes; no runtime operation
relights the jacket or body independently; deterministic captures pass
automated and human review; and the V1 package plus the 49-panel authoring
catalog remain unchanged.

## Approval Record

On 2026-07-23, Kathy approved the baked diorama result as the required visual
target and described it as perfect. This approval selects the visual direction.
The written specification and any later production promotion remain subject to
their separate review and repository gates.
