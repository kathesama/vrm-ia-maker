# Asset And License Inventory

This is an engineering inventory, not legal advice. It separates software
licensing from model, texture, image, and generated-output licensing.

## Software License State

| Artifact | Observed statement | Status |
|---|---|---|
| `LICENSE` | Apache License 2.0 full text | Governing repository license evidence. |
| `NOTICE` | Copyright 2026 Volmarr Wyrd; Apache-2.0; upstream URL | Must be preserved and adapted for derived distributions. |
| `LEGAL-NOTICE.md` | Explicitly says Apache-2.0 and does not override it | Historical project policy; review relevance to new product. |
| `pyproject.toml` | `license = { text = "MIT" }` | Incorrect metadata; must be fixed. |

Recommended near-term action:

- keep Apache-2.0 for the derived tool unless a formal license review decides
  otherwise;
- preserve upstream copyright and NOTICE content;
- add a clear derived-project attribution and imported baseline commit;
- correct package metadata before release.

## Generated Avatar License Boundary

Running an Apache-2.0 tool does not automatically place its output under
Apache-2.0. The license of `juana.vrm` is determined by the character design and
all incorporated meshes, textures, garments, hair, accessories, fonts, and other
assets.

The intended policy is:

```text
vrm-ia-maker source code: Apache-2.0
Juana character design and generated VRM: separate project-owned license
Third-party inputs: their own compatible licenses and attribution requirements
```

The output manifest must state this explicitly.

## Tracked Root Media

Five root images are tracked and total 1,890,487 bytes:

| File | Bytes | Product need | Provenance status |
|---|---:|---|---|
| `2D66H.jpg` | 341,442 | Upstream README/branding illustration | Not documented per file. |
| `QRAO5.jpg` | 302,013 | Upstream README/branding illustration | Not documented per file. |
| `Viking_Apache_V2_1.jpg` | 466,456 | Upstream licensing/branding art | Not documented per file. |
| `image-23-RuneForgeAI.jpg` | 398,899 | Upstream narrative/branding art | Not documented per file. |
| `IMG_0407.jpeg` | 381,677 | Upstream media | Purpose and provenance unclear. |

Do not use these images in Juana assets or new branding until authorship, source,
and redistribution rights are confirmed. They are not needed to compile a VRM.

## Hoard Catalog

The catalog tracks metadata; the base model binaries are not committed.

| Asset ID | Declared license | Binary in Git | Checksum | Provenance assessment |
|---|---|---|---|---|
| `vroid/sample_a` | CC0-1.0 | No | `null` | Source URL present; acceptable as a bootstrap fixture only after pinning a checksum and confirming current source. |
| `vroid/sample_b` | CC0-1.0 | No | `null` | Same as Sample A. |
| `turbosquid/female_rigged_2024` | `TurboSquid-Free` | No | `null` | Source and terms URL present, but redistribution/derivative-output terms require explicit review. Do not adopt as Juana base by assumption. |
| `runa/mb_lab_base_v5` | CC-BY-4.0 | No | `null` | `source_url` is null and required attribution chain is incomplete. Not product-ready. |

Additional inconsistencies:

- entries can say `cached: true` even though cache/bases are local and ignored;
- file size is recorded without an immutable digest;
- the catalog mixes remote fixtures, a marketplace asset, and a character-specific
  derived asset;
- the tool currently permits metadata that is insufficient for a provenance
  audit.

## Tracked Domain Data

| File | Role | License/provenance concern |
|---|---|---|
| `data/loom/known_blendshapes.yaml` | Expression and viseme names | Derived from public VRM/VRoid conventions; source notes exist but should be made precise. |
| `data/gate/vrchat_rules.yaml` | VRChat budgets and requirements as of 2024 | External platform rules can change; source version/date must be maintained if retained. |
| `data/gate/vtube_rules.yaml` | VTube Studio/VRM requirements as of 2024 | Same freshness and attribution concern. |
| `data/hoard/catalog.yaml` | Asset registry | Must evolve into mandatory provenance records. |

## Non-Tracked Runtime Artifacts

The repository ignores or does not commit:

- base `.vrm` and `.fbx` files under Hoard bases;
- build outputs under `out/` and `output/`;
- Annáll runtime databases and event files;
- user configuration and environment files.

Fresh diagnostics created an empty `data/annall/runs.sqlite` in the working tree,
but the clean `git archive` proves it is not tracked. Generated residue must not
be confused with repository content.

## Required Provenance Record

Every future base, texture, garment, hairstyle, accessory, font, and reference
asset should have at least:

```yaml
asset_id: string
asset_type: base_model | texture | hair | garment | accessory | font | reference
name: string
author: string
source_url: string
source_revision: string | null
license_id: string
license_url: string
commercial_use: allowed | forbidden | conditional
modification: allowed | forbidden | conditional
redistribution_source: allowed | forbidden | conditional
redistribution_compiled_vrm: allowed | forbidden | conditional
attribution_text: string | null
sha256: string
reviewed_at: ISO-8601
reviewed_by: string
notes: string | null
```

A missing required field must block production compilation, not merely emit a
warning.

## Output Manifest Requirements

Generated builds should include:

```json
{
  "character_id": "juana",
  "output_license": "All-Rights-Reserved",
  "tool_license": "Apache-2.0",
  "tool_commit": "...",
  "design_package_sha256": "...",
  "base_asset_id": "...",
  "base_asset_sha256": "...",
  "incorporated_assets": [],
  "required_attribution": [],
  "redistribution_allowed": false
}
```

Tool license and output license are separate fields by design.

## Third-Party Software

The baseline also depends on Blender, the VRM Add-on for Blender, Python packages,
and platform-specific GUI libraries. This ticket did not perform a complete
third-party software license audit. Before distribution, produce a
`THIRD_PARTY_NOTICES.md` from the final dependency set. Removing REST, MCP, and
Brúarhönd first will materially reduce that set.

## Risk Decisions

1. Do not select Juana's base model until its compiled-output and redistribution
   rights are explicit.
2. Do not treat catalog labels such as `Free` as a license grant.
3. Do not rely on mutable URLs without hashes and revisions.
4. Do not embed reference-sheet images into the generated VRM unless their license
   permits it.
5. Preserve Apache source attribution even when the generated avatar is
   proprietary.
