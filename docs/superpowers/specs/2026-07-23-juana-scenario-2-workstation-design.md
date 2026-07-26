# Juana Scenario 2 Workstation Design

**Status:** Awaiting written specification review; visual direction approved  
**Date:** 2026-07-23  
**Design approver:** Kathy  
**Repository:** `kathesama/vrm-ia-maker`

## Decision Summary

Add a second visual scenario for Juana: a clean pixel-art workstation derived
from Kathy's real desk arrangement. Juana sits front-facing in the gamer chair
while the three monitors, lamp, books, and white computer case establish the
setting behind her.

Scenario 2 follows the baked-scene decision in
`2026-07-23-juana-baked-diorama-visual-target-design.md`. Juana, chair,
environment, shadows, and color grade are authored as one coherent neutral
scene plate. Three.js does not independently relight the body, jacket, chair,
or facial animation plates.

Scenario 1 remains unchanged. Scenario 2 is a separate visual target and later
runtime entry, not a replacement background for Scenario 1.

## Approved Evidence

The approved evidence is stored outside the V2 authoring package:

```text
output/experiments/juana-scenario-2-workstation-v1/
  README.md
  juana-scenario-2-environment-concept-v3-close.png
  juana-scenario-2-seated-concept-v1.png
```

| Evidence | Dimensions | SHA-256 |
|---|---:|---|
| Empty close environment | 1024 by 1536 | `07c32b9aa5f67c533b809683b2d56f21aec7afb3323249b041b1d1afc8462460` |
| Seated neutral scene | 1024 by 1536 | `0b1307e4fbbd7cab0469e6139409c73c213f0657cc46bc0b7a971df285dff110` |

The original workstation photograph remains a user-supplied layout reference.
It is not copied into the experiment directory or proposed as a runtime asset.

The approval selects composition and appearance. It does not promote either
PNG into the sealed package, approve the remaining provisional catalog panels,
or close provenance and rights gates.

## Environment Contract

- Use a vertical close composition with a slightly elevated diagonal view.
- Keep the gamer chair centered and front-facing.
- Keep exactly three monitors behind the chair.
- Show only abstract blue and cyan interface shapes; no readable or private
  screen content.
- Keep the articulated lamp behind the left monitor.
- Keep a tidy group of books on the upper shelf to the left of the white
  computer case.
- Keep the computer case prominent, physically plausible, and subtly cyan-lit.
  It represents the place where Juana inhabits without becoming
  anthropomorphic.
- Keep the wall supporting the shelf smooth, plain, and white.
- Keep the wooden desk, managed cables, restrained tiled floor, and compact
  room scale.
- Do not restore the clutter or unrelated objects from the source photograph.

The close framing intentionally sacrifices peripheral room detail. The seated
character, not the workstation, owns the visual hierarchy.

## Character Contract

- Juana sits naturally inside the chair and faces the viewer.
- The chair headrest and side wings remain visible behind her head and
  shoulders.
- The armrests remain visible beside her forearms.
- Her back is upright, shoulders relaxed, and knees together.
- One relaxed hand rests over the other at the center of her lap. Fingers stay
  together and naturally curved; they are not interlaced, clasped, praying, or
  floating.
- The lap and upper legs remain visible so the seated pose is unambiguous.
- Preserve the younger base-set identity, nose jewelry, viewer-left shaved
  side, viewer-right long black hair, fitted white high-collar jacket, and
  coordinated white trousers.
- Do not change apparent age, face proportions, body type, hairstyle
  orientation, or neutral-friendly expression.

## Lighting Contract

- The lamp behind the left monitor provides the broad warm amber key.
- The monitors provide restrained blue and cyan fill.
- The white computer case contributes only weak cool ambience.
- Juana receives continuous lighting across face, hair, jacket, hands, and
  trousers.
- Contact shadows bind Juana to the backrest, seat, lap, and armrest region.
- The scene uses shared contrast, haze, black levels, pixel clusters, and
  cinematic color grading.
- No portrait-specific relighting shader, colored clothing masks, outline
  glow, chroma fringe, or independent facial color correction is allowed.

## Runtime Architecture

### Scenario registry

The runtime manifest identifies each environment with a stable scenario ID.
The implementation plan should preserve the existing Scenario 1 ID and add a
new Scenario 2 workstation ID without changing existing consumer defaults.

Each scenario entry owns:

- one approved neutral scene plate;
- scenario-specific eye replacement plates;
- scenario-specific mouth and viseme replacement plates;
- fixed eye and mouth rectangles;
- source hashes, dimensions, palette evidence, and visual approval status;
- optional restrained whole-scene effects.

### Scene plate renderer

The renderer loads one complete neutral scene plate using nearest-neighbor
sampling and deterministic framing. The seated neutral plate includes Juana,
the chair, environment lighting, contact shadows, and workstation occlusion.

The empty environment plate remains authoring and review evidence. It is not
silently displayed as a replacement when the seated neutral plate fails.

### Facial plate compositor

Scenario 2 requires its own eye and mouth plates. Scenario 1 patches must not be
reused directly because Scenario 2 changes face position, scale, surrounding
lighting, and palette.

Scenario 2 facial plates must:

- derive from the same lit seated neutral source;
- use the same 1024 by 1536 canvas and fixed coordinates;
- remain coplanar with the neutral scene;
- include enough surrounding skin pixels to avoid rectangular seams;
- receive no independent lighting, parallax, blur, or color transform.

### Scenario control

The future library API may expose a deterministic command such as
`setScenario(scenarioId)`. Scenario selection changes only rendering assets. It
does not own conversational state, user preference decisions, TTS, STT, agent
behavior, or autonomous scene selection.

Production UI integration remains a later cross-repository task. A
microfrontend is unnecessary for this boundary.

## Data and Asset Flow

1. Preserve the approved experiment hashes as immutable visual evidence.
2. Resolve a canonical implementation ticket before promoting or reproducing
   any experiment asset.
3. Complete provenance and rights review for every production input.
4. Produce or promote a production Scenario 2 seated neutral plate.
5. Derive Scenario 2 eye and mouth plates from the same lit neutral source.
6. Validate canvas, coordinates, hashes, alpha coverage, palette continuity,
   and approval links.
7. Compile the validated Scenario 2 entry into the preview runtime bundle.
8. Render Scenario 1 and Scenario 2 without portrait-specific relighting.

The 49-panel authoring catalog remains the character design source. Scenario
plates are derived runtime artifacts and do not replace catalog approvals.

## Failure Behavior

- A missing, unapproved, or hash-invalid Scenario 2 neutral plate prevents the
  scenario switch and leaves the currently valid scenario unchanged.
- A missing eye or mouth frame falls back to Scenario 2's own neutral facial
  frame and emits a structured diagnostic.
- The runtime never substitutes Scenario 1 facial patches into Scenario 2.
- A plate with incorrect dimensions, coordinates, identity, or source hash is
  rejected before rendering.
- A visible rectangular seam, palette jump, face drift, or clothing color
  island fails the visual review gate.
- The runtime never fabricates a missing pose, expression, or complete scene.

## Validation

### Automated checks

- Verify the neutral scene and every Scenario 2 facial plate by SHA-256.
- Verify the 1024 by 1536 canvas and fixed eye and mouth rectangles.
- Verify nearest-neighbor sampling and coplanar facial plates.
- Verify that Scenario 1 and Scenario 2 reference distinct facial assets.
- Verify the scenario switch leaves the current scene unchanged on failure.
- Verify no portrait-specific lighting shader or clothing color mask is active.
- Capture deterministic Scenario 2 neutral, closed-eye, and required-viseme
  frames.

### Human visual checks

- Compare the empty environment with
  `juana-scenario-2-environment-concept-v3-close.png`.
- Compare the seated neutral scene with
  `juana-scenario-2-seated-concept-v1.png`.
- Confirm the exact three-monitor layout, chair orientation, lamp position,
  books, white case, and smooth white wall.
- Confirm Juana dominates the composition and is visibly seated inside the
  chair.
- Confirm the approved identity, hair orientation, outfit, knees-together
  posture, and hands resting one over the other on the lap.
- Confirm coherent warm/cool illumination with no cutout halo or clothing
  patches.
- Confirm facial animation introduces no seams, palette jumps, or face drift.

## Scope Boundaries

### In scope for the next implementation plan

- Preserve the two approved Scenario 2 experiment images as visual evidence.
- Define the scenario registry and Scenario 2 manifest contract.
- Produce or promote the Scenario 2 neutral runtime plate.
- Author Scenario 2-specific blink and required-viseme plates.
- Demonstrate deterministic Scenario 1 and Scenario 2 switching in the
  standalone viewer.
- Add structural, failure-path, capture, and human visual validation evidence.

### Out of scope

- Modifying `juana-talking-bust-v1` or the future VRM.
- Claiming approval for the other provisional authoring panels.
- Generating every complete pose, presence state, or expression for Scenario 2.
- Integrating scenario selection into Juana's production UI.
- Adding voice, conversational, preference, agent, or autonomous decision
  logic to the renderer.

## Definition of Done

Scenario 2 is complete when the standalone viewer can select a validated
workstation scenario without changing Scenario 1; the seated neutral scene
matches the approved evidence; blinking and required visemes use
Scenario-2-specific co-registered plates without seams or color changes; no
runtime operation relights Juana or the chair independently; deterministic
captures pass automated and human review; and the V1 package plus the 49-panel
authoring catalog remain unchanged.

## Approval Record

On 2026-07-23, Kathy approved:

- the close environment composition in
  `juana-scenario-2-environment-concept-v3-close.png`;
- Juana's front-facing seated scale and placement;
- the knees-together posture;
- the hands resting one over the other on the lap;
- the integrated warm and cool lighting in
  `juana-scenario-2-seated-concept-v1.png`.

This approval selects the visual direction. The written specification and any
later production promotion remain subject to separate review and repository
gates.

