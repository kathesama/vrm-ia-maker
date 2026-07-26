# Juana Pixel Panel Authoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement GH-23 as an independent, bounded panel-first pixel-art authoring workflow that can later produce a sealed 49-panel Juana CharacterDesignPackage without changing the existing sheet-first workflow.

**Architecture:** Add `vrm_ia_maker.design.pixel_portrait` as a sibling bounded context. Reuse generic evidence, rights, provider request/result, and generator-port contracts from `vrm_ia_maker.design`; keep profile state, orchestration, filesystem storage, pixel normalization, composition, and sealing inside the new package. Publish a schema-1.1 CharacterDesignPackage that retains the canonical directory contract and never contains the later derived runtime bundle.

**Tech Stack:** Python 3.11+, Pydantic 2, Pillow, pytest, Ruff, argparse, SHA-256, existing optional OpenAI image adapter.

---

## Execution Constraints

- Follow `.ai-specs/changes/GH-23/GH-23-implementation-spec.md`.
- Approval source: standing delegated execution authority (GH-20).
- Do not modify or revert the active GH-22 files shown by `git status`.
- Do not create branches, commits, or pull requests; root repository rules
  override the generic commit cadence.
- Use synthetic PNGs and fake generators for all gating tests.
- Stop before live canon approval, final 49-panel generation, or package sealing
  with incomplete rights.
- Read technical inputs only from
  `output/character-design-packages/juana-talking-bust-v1/`, retain candidates
  only under `output/authoring/juana-talking-bust-v2-pixel/`, and publish only
  to `output/character-design-packages/juana-talking-bust-v2-pixel/`.

## File Map

- Create `src/vrm_ia_maker/design/pixel_portrait/__init__.py`.
- Create `src/vrm_ia_maker/design/pixel_portrait/contracts.py`.
- Create `src/vrm_ia_maker/design/pixel_portrait/plan.py`.
- Create `src/vrm_ia_maker/design/pixel_portrait/ports.py`.
- Create `src/vrm_ia_maker/design/pixel_portrait/service.py`.
- Create `src/vrm_ia_maker/design/pixel_portrait/cli.py`.
- Create `src/vrm_ia_maker/design/pixel_portrait/adapters/__init__.py`.
- Create `src/vrm_ia_maker/design/pixel_portrait/adapters/filesystem.py`.
- Create matching tests under
  `tests/unit/vrm_ia_maker/design/pixel_portrait/`.
- Create `docs/DECISIONS/D-015-panel-first-pixel-portrait-authoring.md`.
- Modify `docs/DECISIONS/README.md` and
  `docs/CHARACTER_DESIGN_PACKAGE.md`.

### Task 1: Strict panel-first contracts

**Files:**
- Create: `src/vrm_ia_maker/design/pixel_portrait/__init__.py`
- Create: `src/vrm_ia_maker/design/pixel_portrait/contracts.py`
- Create: `tests/unit/vrm_ia_maker/design/pixel_portrait/__init__.py`
- Create: `tests/unit/vrm_ia_maker/design/pixel_portrait/test_contracts.py`

- [ ] **Step 1: Write failing contract tests**

Cover these exact invariants:

```python
def test_pixel_state_requires_dictionary_keys_to_match_panel_ids() -> None:
    payload = valid_state_payload()
    payload["panels"] = {"wrong": payload["panels"]["presence-neutral"]}
    with pytest.raises(ValidationError, match="Panel dictionary keys"):
        PixelPortraitAuthoringState.model_validate(payload)


def test_neutral_approval_requires_identity_lock() -> None:
    state = PixelPanelState(
        panel_id="presence-neutral",
        progress=PixelPanelProgress.APPROVED,
        attempts=(successful_attempt(),),
        candidates=(candidate(status=CandidateStatus.APPROVED),),
        decisions=(approval(),),
        approved_candidate_id="presence-neutral-attempt-1",
    )
    with pytest.raises(ValidationError, match="identity lock"):
        PixelPortraitAuthoringState(
            revision=revision(),
            plan_id="juana-talking-bust-v2-pixel",
            plan_version="1.0",
            panels={"presence-neutral": state},
        )


def test_composite_rejects_duplicate_or_unapproved_members() -> None:
    with pytest.raises(ValidationError, match="member hashes"):
        CompositeReviewSheet(
            sheet_id="presence-states-v1",
            scope=CompositeScope.FAMILY,
            family_id="presence-states",
            member_ids=("presence-neutral", "presence-neutral"),
            member_hashes=(DIGEST_A, DIGEST_A),
            artifact=artifact("composites/presence-states-v1.png"),
            composition_version="pixel-grid-v1",
            created_at=NOW,
        )
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/unit/vrm_ia_maker/design/pixel_portrait/test_contracts.py -q
```

Expected: collection fails because `pixel_portrait.contracts` does not exist.

- [ ] **Step 3: Add the strict models**

Implement these named contracts using `StrictDesignModel`,
`ArtifactEvidence`, `RightsMetadata`, `ProvenanceRecord`,
`GapRecord`, `CandidateStatus`, `GenerationAttempt`, and
`ApprovalDecision` from the existing design contracts:

```python
class PanelRuntimeRole(StrEnum):
    AUTHORING_ONLY = "authoring_only"
    STATE = "state"
    EYE_PATCH = "eye_patch"
    MOUTH_PATCH = "mouth_patch"


class CompositeScope(StrEnum):
    FAMILY = "family"
    PACKAGE_MASTER = "package_master"


class CompositeStatus(StrEnum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    STALE = "stale"


class HairOrientation(StrEnum):
    VIEWER_LEFT_SHAVE = "viewer_left_shave_viewer_right_long"


class PortraitIdentityLock(StrictDesignModel):
    logical_width: Literal[256] = 256
    logical_height: Literal[256] = 256
    file_width: Literal[512] = 512
    file_height: Literal[512] = 512
    palette_sha256: SHA256
    palette_max_colors: Annotated[int, Field(ge=2, le=64)]
    pivot: tuple[Annotated[int, Field(ge=0, le=255)], Annotated[int, Field(ge=0, le=255)]]
    eye_rect: LogicalRect
    mouth_rect: LogicalRect
    shoulder_left: LogicalPoint
    shoulder_right: LogicalPoint
    face_top_y: Annotated[int, Field(ge=0, le=255)]
    chin_y: Annotated[int, Field(ge=0, le=255)]
    face_height_target: Literal[160] = 160
    face_height_tolerance: Literal[2] = 2
    hair_orientation: Literal[HairOrientation.VIEWER_LEFT_SHAVE] = HairOrientation.VIEWER_LEFT_SHAVE

    @model_validator(mode="after")
    def validate_face_height(self) -> Self:
        if self.chin_y - self.face_top_y != self.face_height_target:
            raise ValueError("Neutral identity lock must record a 160-pixel face height.")
        return self
```

Also implement `PixelPackageRevision` with schema version `1.1`,
`PixelPanelCandidate`, `PixelPanelApproval`, `PixelPanelState`,
`CompositeReviewSheet`, `CompositeApproval`, and
`PixelPortraitAuthoringState`. Enforce contiguous attempts, immutable decision
history, one active approval, neutral-lock presence, unique provenance/gaps,
unique composite member IDs/hashes, and stale-composite exclusion from active
IDs.

- [ ] **Step 4: Verify GREEN**

Run the focused test command. Expected: all contract tests pass.

### Task 2: Fixed 49-panel plan and source-of-truth inventory

**Files:**
- Create: `src/vrm_ia_maker/design/pixel_portrait/plan.py`
- Create: `tests/unit/vrm_ia_maker/design/pixel_portrait/test_plan.py`

- [ ] **Step 1: Write failing plan tests**

```python
def test_pixel_plan_has_exact_inventory_and_family_order() -> None:
    assert tuple(f.family_id for f in PIXEL_PORTRAIT_PLAN.families) == (
        "presence-states",
        "face-turnaround",
        "facial-mechanics",
        "upper-body-turnaround",
        "expressions",
        "visemes",
        "hair-construction",
        "outfit-construction",
        "material-reference",
    )
    assert len(PIXEL_PORTRAIT_PLAN.panels) == 49
    assert len({p.panel_id for p in PIXEL_PORTRAIT_PLAN.panels}) == 49
    assert len({p.package_path for p in PIXEL_PORTRAIT_PLAN.panels}) == 49


def test_only_presence_panels_are_runtime_states() -> None:
    runtime = {
        p.panel_id for p in PIXEL_PORTRAIT_PLAN.panels
        if p.runtime_role is PanelRuntimeRole.STATE
    }
    assert runtime == {
        "presence-neutral", "presence-thinking", "presence-explaining",
        "presence-approval", "presence-doubt", "presence-error",
    }


def test_every_panel_uses_supported_raw_and_pixel_dimensions() -> None:
    for panel in PIXEL_PORTRAIT_PLAN.panels:
        assert (panel.request_width, panel.request_height) == (1024, 1024)
        assert (panel.logical_width, panel.logical_height) == (256, 256)
        assert (panel.file_width, panel.file_height) == (512, 512)
        assert panel.prompt_version == "pixel-panel-v1"
```

- [ ] **Step 2: Verify RED**

Run the plan test. Expected: import failure for `PIXEL_PORTRAIT_PLAN`.

- [ ] **Step 3: Implement the immutable plan**

Define strict `PixelPanelDefinition`, `PixelFamilyDefinition`, and
`PixelPortraitPlanDefinition` models. Build the inventory from explicit
ordered tuples, not filesystem discovery. Use these exact member lists:

```python
PANEL_MEMBERS = {
    "presence-states": ("neutral", "thinking", "explaining", "approval", "doubt", "error"),
    "face-turnaround": ("neutral-front", "left-profile", "right-profile", "left-three-quarter", "right-three-quarter"),
    "facial-mechanics": ("eyes-open", "eyes-closed", "blink-left", "blink-right", "jaw-open", "neutral-mouth"),
    "upper-body-turnaround": ("front", "left", "right", "back"),
    "expressions": ("neutral", "happy", "sad", "angry", "surprised", "relaxed"),
    "visemes": ("neutral", "aa", "ih", "ou", "ee", "oh"),
    "hair-construction": ("front", "left", "right", "back", "top", "hairline"),
    "outfit-construction": ("front", "left", "right", "back"),
    "material-reference": ("skin", "hair", "eyes", "outfit", "accessories", "combined-palette"),
}
```

Use one base English prompt containing the younger identity, viewer-left shave,
viewer-right long hair, fine pixel-art grid, transparent/solid background rule,
no extra panels, and no text. Add only a panel-specific instruction from the
definition. Neutral is first; all other panels depend on its active approval.
Map each technical panel to the exact sealed-package reference path and each
presence panel to its exact base-set source role.

- [ ] **Step 4: Verify GREEN**

Run the plan tests. Expected: exact counts, order, roles, sources, and paths pass.

### Task 3: Filesystem initialization and deterministic pixel normalization

**Files:**
- Create: `src/vrm_ia_maker/design/pixel_portrait/ports.py`
- Create: `src/vrm_ia_maker/design/pixel_portrait/adapters/__init__.py`
- Create: `src/vrm_ia_maker/design/pixel_portrait/adapters/filesystem.py`
- Create: `tests/unit/vrm_ia_maker/design/pixel_portrait/test_filesystem.py`

- [ ] **Step 1: Write failing initialization and raster tests**

Test that initialization requires the seven named base files, validates the
technical package seal, copies bytes without mutation, records hashes, refuses
an existing workspace, and creates `source-rights-incomplete` when rights are
missing.

Test the raster with a synthetic 1024-square gradient:

```python
candidate = workspace.stage_candidate(
    panel=PIXEL_PORTRAIT_PLAN.panel("presence-neutral"),
    attempt=1,
    generated=GeneratedImage(data=raw_png, provider="fake", model="fake-v1"),
    input_artifacts=locked_inputs,
    created_at=NOW,
)
with Image.open(workspace.resolve_artifact(candidate.panel.path)) as image:
    assert image.size == (512, 512)
    assert len(image.convert("RGBA").getcolors(maxcolors=65) or ()) <= 64
    pixels = image.convert("RGBA")
    for y in range(0, 512, 2):
        for x in range(0, 512, 2):
            assert len({pixels.getpixel((x + dx, y + dy)) for dx in (0, 1) for dy in (0, 1)}) == 1
```

- [ ] **Step 2: Verify RED**

Run `test_filesystem.py`. Expected: missing workspace implementation.

- [ ] **Step 3: Implement the workspace boundary**

Define `PixelWorkspaceInitialization` with exactly seven named base paths,
one technical package path, package identity, revision, authoritative source,
and optional base rights. Define `PixelPortraitWorkspacePort` for initialize,
load/save, resolve, stage, compose, seal, validate, and exclusive lock methods.

In the adapter:

- validate `FilesystemAuthoringWorkspace.validate_sealed_package()` against
  the technical package before copying;
- copy all sources exclusively and record byte length, dimensions, SHA-256,
  source class, and rights basis;
- write canonical JSON atomically with a same-directory temporary file and
  `os.replace`;
- validate raw PNG as 1024 by 1024;
- resize to 256 by 256 with `Image.Resampling.LANCZOS`;
- quantize to the stored maximum-64-color palette;
- resize to 512 by 512 with `Image.Resampling.NEAREST`;
- preserve raw, normalized panel, validation JSON, and artifact evidence;
- reject path traversal, symlink escape, changed bytes, and overwrite.

- [ ] **Step 4: Verify GREEN**

Run filesystem and contract tests. Expected: all pass without network access.

### Task 4: Panel-first application service and bounded attempts

**Files:**
- Create: `src/vrm_ia_maker/design/pixel_portrait/service.py`
- Create: `tests/unit/vrm_ia_maker/design/pixel_portrait/test_service.py`

- [ ] **Step 1: Write failing service tests**

Use a counting fake generator and injected UTC clock. Assert:

```python
first = service.run()
assert first.panel_id == "presence-neutral"
assert generator.calls == 1

with pytest.raises(PixelPortraitWorkflowError, match="pending review"):
    service.run()
assert generator.calls == 1
```

Add failure cases proving an in-progress record is saved before the provider,
provider and moderation failures consume one attempt, interrupted attempts are
recovered as failed, a fourth call is rejected, and only approved neutral plus
the exact named source artifacts enter later requests.

- [ ] **Step 2: Verify RED**

Run `test_service.py`. Expected: missing `PixelPortraitService`.

- [ ] **Step 3: Implement the plain use case**

Implement `initialize`, `status`, `run`, `validate`, and `set_rights`.
The service selects the first eligible panel in fixed plan order. It writes an
in-progress `GenerationAttempt`, calls the reused
`ReferenceImageGeneratorPort` exactly once, stages one candidate, and writes
the completed attempt. It never catches and retries a provider error. It
recovers a persisted in-progress attempt as a consumed sanitized failure before
a later explicit run.

- [ ] **Step 4: Verify GREEN**

Run service tests. Expected: bounded state-machine tests pass.

### Task 5: Decisions, identity lock, family sheets, and package master

**Files:**
- Modify: `src/vrm_ia_maker/design/pixel_portrait/service.py`
- Modify: `src/vrm_ia_maker/design/pixel_portrait/adapters/filesystem.py`
- Modify: focused contract/service/filesystem tests

- [ ] **Step 1: Write failing decision and composition tests**

Cover approve, reject, supersede, duplicate-decision rejection, and full reviewed
artifact scope. Neutral approval without `PortraitIdentityLock` must fail.
After the last panel in a family is approved, assert one pending-review family
sheet exists. Approve all family sheets and assert one pending-review package
master exists. Supersede one panel and assert only its family and the package
master are stale.

- [ ] **Step 2: Verify RED**

Run focused tests. Expected: decision/composition methods are absent.

- [ ] **Step 3: Implement decisions and deterministic composition**

Add service methods `approve_panel`, `reject_panel`,
`supersede_panel`, and `approve_composite`. Preserve every historical
candidate, decision, composite, and composite approval.

Compose fixed grids with RGBA panels, one-pixel logical separators scaled to two
physical pixels, no labels, and a metadata slot map. A family sheet records
ordered panel IDs and active hashes exactly once. The package master records
ordered approved family-sheet IDs and hashes exactly once. Only reviewed,
current composites are eligible for sealing.

- [ ] **Step 4: Verify GREEN**

Run focused tests. Expected: deterministic composition and invalidation pass.

### Task 6: Schema-1.1 publication and offline validation

**Files:**
- Modify: `src/vrm_ia_maker/design/pixel_portrait/adapters/filesystem.py`
- Modify: `src/vrm_ia_maker/design/pixel_portrait/service.py`
- Add seal integration tests

- [ ] **Step 1: Write failing seal tests**

Create a complete synthetic state and assert sealing writes:

```python
package = json.loads((destination / "package.json").read_text(encoding="utf-8"))
assert package["schema_version"] == "1.1"
assert package["profile"] == "pixel-talking-portrait"
assert package["master_reference"]["path"] == "references/master/master-character-sheet.png"
assert len(package["approved_reference_sheets"]) == 9
assert not (destination / "runtime").exists()
FilesystemPixelPortraitWorkspace.validate_sealed_package(destination)
```

Add one negative test per AC-07 precondition and prove the existing
`juana-talking-bust-v1` package still validates.

- [ ] **Step 2: Verify RED**

Run seal tests. Expected: seal method absent or failing.

- [ ] **Step 3: Implement no-clobber publication**

Create all canonical CharacterDesignPackage directories plus `sources/` and
`authoring/`. Copy verified source locks, 49 active panels, nine family
sheets, and the package master. Write package, provenance, approvals, gaps,
pixel-style, panel-definitions, anchor-profiles, composite-sheets, and seal JSON.
Hash every file except `seal.json`, then write the seal. Validate all recorded
digests, required canonical directories, profile fields, active approval IDs,
and master lineage before renaming staging to a missing destination.

- [ ] **Step 4: Verify GREEN**

Run seal integration, filesystem, and old design tests. Expected: both profile
validators pass.

### Task 7: Stable internal CLI

**Files:**
- Create: `src/vrm_ia_maker/design/pixel_portrait/cli.py`
- Create: `tests/unit/vrm_ia_maker/design/pixel_portrait/test_cli.py`

- [ ] **Step 1: Write failing CLI workflow tests**

Invoke `main()` with in-memory streams and injected fake generator for
`init`, `status`, `run`, panel decisions, composite review, validation,
rights update, and seal. Assert parseable JSON, stable non-zero exit codes,
English diagnostics, and no secret or remote raw message output.

- [ ] **Step 2: Verify RED**

Run `test_cli.py`. Expected: CLI module missing.

- [ ] **Step 3: Implement argparse commands**

Mirror the existing JSON CLI conventions. Require explicit workspace paths and
panel/composite IDs. Accept neutral identity-lock JSON only on neutral approval.
Keep provider creation lazy and reuse `OpenAIImageGenerator`. Do not change
the public project script entrypoint.

- [ ] **Step 4: Verify GREEN**

Run CLI and all pixel-portrait tests. Expected: complete synthetic workflow
passes.

### Task 8: Architecture documentation and full validation

**Files:**
- Create: `docs/DECISIONS/D-015-panel-first-pixel-portrait-authoring.md`
- Modify: `docs/DECISIONS/README.md`
- Modify: `docs/CHARACTER_DESIGN_PACKAGE.md`
- Update: `.ai-specs/changes/GH-23/GH-23-CHANGELOG.md`
- Update: GH-23 completion evidence and later QA/review artifacts

- [ ] **Step 1: Record D-015**

Document the sibling bounded context, schema-1.1 compatibility, fixed inventory,
neutral identity lock, deterministic raster/composition, sole master reference,
source rights, human review, provider boundary, and separate later runtime
bundle. Do not claim final images or viewer exist.

- [ ] **Step 2: Update package documentation and decision index**

Add the pixel profile beside the existing bounded talking-bust section and link
D-015. Preserve the canonical package contract and explain the additive
directories.

- [ ] **Step 3: Run focused validation**

```powershell
$env:PYTHONPATH='src'; python -m pytest tests/unit/vrm_ia_maker/design/pixel_portrait -q
python -m ruff check src/vrm_ia_maker/design/pixel_portrait tests/unit/vrm_ia_maker/design/pixel_portrait
$env:PYTHONPATH='src'; python -m pytest tests/unit/vrm_ia_maker/design -q
```

Expected: all commands exit zero.

- [ ] **Step 4: Run broad offline regression**

```powershell
python -m pytest -m "not requires_blender and not requires_vroid_host"
```

Expected: exit zero, or exact inherited unrelated failures recorded without
claiming GH-23 caused or fixed them.

- [ ] **Step 5: Run SDD validation and evidence workflows**

Use the project-local QA, code-review, changelog, PR-report, and PR-content
validators required by `.sdd-kit/CODEX.md`. Root rules still prohibit creating
a real commit or pull request; reports remain local evidence.
