# D-013 - Bounded Reference Authoring
**Status:** Accepted
**Date:** 2026-07-16
**Deciders:** Katherine E. Aguirre
**Phase:** CharacterDesignPackage visual authoring

## Context

A master character sheet is creative canon, but it does not contain executable
geometry or reliable facts for every hidden view. The talking-bust milestone needs
consistent face, body, expression, viseme, hair, outfit, and material references
before Blender authoring can begin. Producing those references may use an online
image provider, but the repository must retain deterministic orchestration,
traceability, bounded cost, and explicit human control.

The provider boundary must not make the sealed package, the Blender build, the
Three.js consumer, or the avatar runtime dependent on an LLM or remote service.

## Decision

Reference authoring is a build-time-only workflow with a fixed, versioned DAG of
eight tasks. The workflow is not a general planner and the provider does not choose
the next task, dependencies, output paths, attempt count, or approval state.

Each explicit `run` invocation makes at most one provider request. A task receives
no more than three recorded attempts, and the provider SDK has automatic retries
disabled. An interrupted request is recorded as a consumed failed attempt before a
later explicit retry can start.

Every provider request contains:

- the immutable master character sheet;
- only the approved predecessor sheets declared by the fixed DAG;
- the selected task's versioned English prompt;
- the exact PNG size and output settings.

No measurements, landmarks, production assets, unrelated repository files, secrets,
or rejected candidates are sent. The OpenAI adapter reads `OPENAI_API_KEY` from the
process environment, uses a configurable model and explicit timeout, and sanitizes
provider errors. The credential is never written, echoed, hashed, or included in
authoring state.

The adapter requests high input fidelity only when the configured model exposes that
option. For `gpt-image-2`, it omits `input_fidelity` because that model processes every
image input at high fidelity and rejects the explicit parameter.

Generated sheets and deterministic panel crops remain candidates until human approval
covers both the sheet and every preview. Rejected, malformed, failed, and interrupted
attempts remain auditable in the authoring workspace and are excluded from the sealed
package. A human decision never converts perspective art into metric truth.

A named reviewer may supersede an active approval when later canonical direction
invalidates it. Supersession is allowed only after downstream candidates are resolved,
retains the original approval, files, hashes, and provenance, and reopens the task only
within its existing attempt bound. The superseded candidate is excluded from sealing.

Pillow is a required local dependency for PNG validation, dimensions, and exact panel
crops. The OpenAI Python SDK is an optional `authoring-openai` dependency. Core
contracts, planning, state transitions, sealing, validation, Blender builds, and
Three.js consumption do not import the provider SDK.

Sealing requires all eight tasks to be approved, all recorded hashes to match, a
complete rights basis, and no visual-seal blocking gap. The sealed
CharacterDesignPackage contains approved sheets, approved crops, provenance,
approvals, gaps, and seal evidence. It performs no provider calls, and every
downstream build and runtime remains offline with respect to image generation.
An incomplete master-source rights record may be completed once on an existing
workspace; complete rights are immutable for that package revision.

## Failure Policy

- Configuration, timeout, provider, payload, PNG, path, integrity, and no-clobber
  failures are explicit and non-retrying.
- Moderation failures expose only the provider's public code and allowlisted coarse
  stage/category labels. Remote messages and unrecognized labels remain sanitized.
- State is written atomically before a provider request and after each outcome.
- A workspace lock prevents concurrent writers from duplicating an expensive call.
- Existing workspaces, candidate attempts, accepted package paths, and sealed package
  destinations are never overwritten.
- Missing legal metadata or unresolved visual gaps block sealing instead of being
  inferred or silently accepted.

## Consequences

- One approved source image can drive a reproducible sequence of visual candidates
  without claiming automatic 3D reconstruction.
- Provider access is optional and isolated, while local validation and downstream
  production remain provider-neutral.
- Visual quality and identity consistency require human review after every task.
- Measurements, landmarks, numeric materials, traceable 3D assets, and adapters remain
  explicit later-stage gaps.
- Supporting another milestone or task graph requires a new reviewed plan version; it
  is not discovered dynamically by a model.

## Rejected Alternatives

- A free-running agent or model-selected task graph was rejected because it would make
  cost, inputs, output coverage, and retries nondeterministic.
- Automatic visual approval was rejected because similarity heuristics cannot authorize
  identity changes or legal use.
- Provider calls in Blender, Three.js, or the avatar runtime were rejected because they
  violate the offline build and deterministic runtime boundaries.
- Rebuilding PNG validation and cropping without Pillow was rejected as unnecessary
  custom image-processing risk.

## References

- `docs/CHARACTER_DESIGN_PACKAGE.md`
- `ASSET_POLICY.md`
- `docs/DECISIONS/D-011-production-threejs-assembly-compiler.md`
- GitHub issue `GH-19`
