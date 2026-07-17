# Modular Asset Composition Spike

This spike proves the next product invariant after the hybrid VRM output path:

> Independent base, hair, outfit, and accessory assets can be selected through an
> explicit assembly contract, compiled with Three.js, finalized by Blender, and
> exported as a valid VRM 1.x avatar.

## Pipeline

```text
Blender generates repository-owned modular GLB fixtures
        -> Python seals the asset-pack manifest with SHA-256 values
        -> Three.js validates and compiles the selected assembly
        -> Blender imports, attaches, and rebinds selected components
        -> Blender + VRM Add-on exports VRM 1.0
        -> Python validates binary structure and component presence
        -> @pixiv/three-vrm loads and exercises the final avatar
```

Three.js owns selection, inspection, and compilation. Blender remains the last
writer of the distributed `.vrm` file.

## Retained contract boundary

The JSON Schemas under `contracts/`, the original array-shaped assembly examples,
the spike compiler, and the spike Blender finalizer remain schema 1.0 evidence.
They are intentionally not the production contract source of truth.

Production manifests are defined by `src/vrm_ia_maker/contracts.py`. The compiler
under `packages/three-assembly-compiler/` emits schema 1.1 and is exercised in the
workflow as an additional validated handoff. The schema 1.0 spike compiler and
finalizer continue to run as retained evidence. The same workflow also sends both
schema 1.1 variants through the production Forge, structural validator, and
Three.js validator; neither path replaces the other yet.

## Builds

The workflow produces two avatars from the same asset pack:

- `modular-without-accessory.vrm`: base + hair + skinned outfit.
- `modular-with-accessory.vrm`: base + hair + skinned outfit + rigid accessory.
- `production-modular-without-accessory.vrm`: schema 1.1 production Forge output.
- `production-modular-with-accessory.vrm`: schema 1.1 production Forge output
  with the rigid accessory.
- `production-blender-report-*.json`: strict production build reports paired
  with the production VRMs.

The validators prove that the optional accessory appears only in the second
output, while both outputs preserve the same humanoid, expression, and look-at
contracts.

## Fixture ownership

Every GLB used by this spike is generated procedurally by code in this directory.
The fixtures are repository-owned and declared CC0 for test and demonstration
purposes. No CharacterStudio model, `loot-assets` model, marketplace model, or
production Juana design is included.

## Non-goals

This spike does not implement the production character-design package, realistic
hair, production clothing, texture atlases, hidden-face culling, mesh merging,
KTX2 compression, or the final Juana avatar.
