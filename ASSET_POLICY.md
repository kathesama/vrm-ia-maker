# Asset Policy

## Purpose

VRM IA Maker transforms character designs and 3D assets into generated avatar artifacts. Software licensing and asset licensing are separate concerns. This policy defines the minimum provenance, integrity, and usage evidence required before an asset can participate in a releasable build.

## Scope

This policy applies to:

- VRM, GLB, glTF, FBX, OBJ, and Blender files;
- meshes, rigs, morph targets, animations, and spring-bone data;
- textures, normal maps, masks, materials, and shaders;
- hair, garments, accessories, fonts, logos, and icons;
- character sheets, turnarounds, expression sheets, and viseme references;
- generated intermediates and final avatar packages.

## Required asset record

Every asset must have a machine-readable record containing at least:

```yaml
asset_id: "stable/kebab-case-id"
name: "Human-readable asset name"
type: "vrm | glb | gltf | fbx | obj | blend | texture | hair | outfit | accessory | font | design-reference"
author: "Author or rights holder"
source_url: "https://authoritative-source.example/item"
license: "SPDX identifier or exact license name"
license_url: "https://authoritative-source.example/license"
commercial_use: true
modification_allowed: true
redistribution_allowed: false
attribution_required: true
attribution_text: "Required credit, or null when not required"
sha256: "64 lowercase hexadecimal characters"
acquired_at: "2026-07-13T00:00:00Z"
review_status: "pending | approved | rejected"
reviewed_by: "reviewer identity or null"
reviewed_at: "ISO-8601 timestamp or null"
notes: "Relevant restrictions, or null"
```

Additional fields may be required for a specific provider or asset type. Required legal text must be stored without paraphrasing when the license requires exact reproduction.

## Approval rules

An asset may be marked `approved` only when all of the following are true:

1. The author or rights holder is identified.
2. The authoritative source URL is recorded and reachable during review.
3. The exact license or contractual terms are available.
4. Commercial-use rights match the intended use.
5. Modification rights permit the transformations performed by the forge.
6. Redistribution rights cover the actual delivery model.
7. Required attribution is recorded and can be reproduced in release material.
8. A SHA-256 digest identifies the exact reviewed file.
9. Any dependency assets embedded inside the file are separately reviewed.
10. The reviewer records a decision and timestamp.

A missing value is not an implicit permission. `source_url: null`, `license: unknown`, or `sha256: null` keeps the asset in `pending` state and blocks releasable builds.

## Redistribution categories

Assets must be classified according to how the generated avatar will be delivered.

### Internal build input

The asset remains only on a controlled build machine and is not distributed. This still requires commercial-use and modification rights.

### Embedded application asset

The generated VRM is shipped inside an application but is not offered as a standalone download. The source license must permit this form of distribution.

### Standalone avatar distribution

The VRM is delivered directly to users or partners. The source license must permit redistribution of geometry, textures, and other embedded content in that form.

### Public source fixture

The asset is committed to a public repository or release archive. Explicit source redistribution permission is mandatory. A license that permits use but prohibits source redistribution is insufficient.

## Character design packages

The canonical character design package is also an asset package. Each package must include `LICENSE.md` and provenance for every incorporated reference.

For Juana, the preferred position is:

- original character design owned by the Juana project;
- original or explicitly licensed base geometry;
- original textures, hair, outfit, and accessories;
- generated avatar licensed independently from this Apache-2.0 tool.

Reference images obtained from third parties may guide design only when their terms permit that use. They must not be embedded in public fixtures without redistribution rights.

## Generated artifacts

A generated file does not receive Apache-2.0 merely because VRM IA Maker produced it. The output license is determined by:

```text
character design rights
+ base model rights
+ mesh and rig rights
+ texture and material rights
+ garment, hair, accessory, font, and logo rights
+ any required attribution or redistribution restrictions
```

Every releasable build must produce an asset manifest that records input asset IDs, exact hashes, licenses, and output-license decision.

## Marketplace and free assets

The following labels are not sufficient approval evidence:

- free;
- royalty-free;
- downloadable;
- personal use;
- sample;
- fan-made;
- AI-generated.

Marketplace terms must be reviewed for commercial use, modification, redistribution, sublicensing, attribution, and restrictions on extracted or standalone assets.

## Integrity and reproducibility

- Use SHA-256 for all source assets and generated outputs.
- Never overwrite an approved asset in place with different bytes.
- A changed file receives a new digest and a new review decision.
- Build manifests must identify the exact base asset and adapter version.
- Remote downloads must verify the expected digest before use.
- A digest mismatch is a hard failure, not a warning.

## Repository rules

- Large or restricted assets must not be committed merely for convenience.
- Git LFS does not solve licensing restrictions.
- Public fixtures should be original, CC0, or covered by equally explicit redistribution permission.
- Asset records may be committed without committing restricted asset bytes.
- Secrets, purchase receipts, account identifiers, and private marketplace tokens must never be committed.

## Repository storage classes

### Ordinary Git

Ordinary Git stores source code, tests, documentation, manifests, checksums,
provenance records, and small approved fixtures. Generated files must not be
committed merely because a local build produced them. A committed manifest
should identify the generation inputs and output digest without duplicating the
output bytes when another storage class owns those bytes.

### Git LFS

Git LFS stores required, redistributable, non-text binary inputs or evidence
that cannot be regenerated for a fresh checkout. LFS rules must be path-scoped
to the approved asset family; global image or model globs are prohibited
because they can migrate unrelated repository history. Git LFS must not be used
as a dependency cache and does not replace provenance or redistribution
approval.

The current path-scoped LFS assets are:

- `artifacts/debug/invalid-donor-overlay.blend`, retained by the GH-22 archive
  contract;
- canonical derived GLB inputs under `tools/juana_bust/assets/`.
- canonical Juana V2 pixel runtime PNG files under
  `packages/juana-pixel-runtime/v2/runtime/`.

### Ignored local build roots

`build/` contains downloaded toolchains, dependency caches, donor staging,
intermediate geometry, and reproducible build outputs. `output/` contains local
authoring packages and experiments. Both roots remain ignored and must be
reconstructed from pinned scripts, manifests, source records, and checksums.
Local brainstorm content, rejected captures, and test scratch directories use
the same ignored-storage class.

An ignored file is not automatically disposable. Ignore rules control Git
delivery only; deletion requires a separate, explicit retention decision.

### Release artifacts

Versioned deliverables such as sealed pixel-runtime bundles, distributable VRM
files, and review packages belong in an approved release or artifact store.
The repository commits their build logic, provenance, manifest, and checksum.
Publishing or replacing a release artifact is a separate approval-gated action
and must not happen as a side effect of a normal source commit.

## Build enforcement

The future asset catalog and build pipeline must reject releasable builds when:

- an asset record is missing;
- `review_status` is not `approved`;
- the source file digest does not match the approved digest;
- required attribution is absent from the release package;
- the requested distribution mode exceeds the recorded permissions;
- an embedded dependency has unresolved provenance.

Development-only experiments may use pending assets only in isolated local builds. Their outputs must be clearly marked non-redistributable and must not enter release directories.

## Existing inherited catalog

Inherited catalog entries are evidence to investigate, not automatic approvals. Entries with missing checksums, incomplete source URLs, ambiguous marketplace terms, or incomplete attribution remain non-product-ready until reviewed under this policy.

See `docs/migration/ASSET_AND_LICENSE_INVENTORY.md` for the current inventory.
