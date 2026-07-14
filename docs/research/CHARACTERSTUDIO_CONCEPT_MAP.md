# CharacterStudio Concept Map

## Purpose

This document records which CharacterStudio and `loot-assets` concepts inform the
VRM IA Maker modular assembly contracts. It does not authorize importing either
application, its Web3 stack, or its asset repository.

## Concept mapping

| CharacterStudio / loot-assets concept | VRM IA Maker concept | Decision |
|---|---|---|
| `requiredTraits` | required component slots | Adapt the concept. |
| `initialTraits` | default assembly selections | Adapt the concept. |
| `trait` | component slot | Adapt the concept. |
| `collection` | asset candidates for a slot | Adapt the concept. |
| `blendshapeTraits` | versioned morph operations | Evaluate after the base-adapter contract exists. |
| per-trait colors and textures | material overrides | Adapt with explicit material names and validation. |
| culling layers | future optimization policy | Research only; not part of this spike. |
| skeleton merge | skinned-component rebinding | Reimplement behind tests; do not copy yet. |
| texture atlas generation | future web optimization stage | Evaluate after expression and spring-bone preservation tests. |
| browser preview | Three.js assembly inspection | Adopt as a build-time validation role. |
| CharacterStudio VRM exporter | final VRM writer | Reject for the current pipeline. Blender remains authoritative. |

## Licensing boundary

CharacterStudio source is MIT-licensed, but its separate asset repository does
not provide the provenance fields required by `ASSET_POLICY.md` for production
use. This spike therefore generates its own procedural fixtures and does not
consume `loot-assets`.

Any future source port must:

1. identify the exact upstream file and commit;
2. preserve the MIT copyright and license notice;
3. add focused characterization tests before adaptation;
4. record the port in `THIRD_PARTY_NOTICES.md`;
5. prove that VRM expressions, humanoid mappings, skinning, and spring-bone data
   survive the operation.

## Architecture decision supported by SPIKE-2

```text
AssetPackManifest
        -> AssemblyManifest
        -> Three.js assembly compiler
        -> CompiledAssemblySpec
        -> Blender modular finalizer
        -> VRM 1.0
        -> Three.js consumer validator
```

Three.js owns selection and consumer verification. Blender owns geometry
assembly, rig rebinding, VRM metadata, and final export.

## Explicitly rejected scope

- React application adoption;
- Zustand state management;
- Ethereum, Solana, wallet, minting, or NFT integrations;
- CharacterStudio's VRM exporter;
- `loot-assets` production models;
- any runtime AI control inside the avatar layer.
