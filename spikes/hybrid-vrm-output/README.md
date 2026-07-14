# Hybrid Blender + Three.js VRM Output Spike

This spike proves one narrow product invariant:

> A successful build must produce a real VRM 1.x file that loads through
> `@pixiv/three-vrm`.

## Pipeline

```text
Blender authors an original humanoid GLB fixture
        -> Three.js inspects the scene and compiles AssemblyManifest
        -> Blender + VRM Add-on finalizes VRM 1.0
        -> Python validates the binary VRM structure
        -> @pixiv/three-vrm loads and exercises the avatar contract
```

Three.js owns composition decisions and consumer validation. Blender remains the
last writer of the distributed `.vrm` file.

## Output

The GitHub Actions workflow uploads an artifact named `hybrid-vrm-output` with:

```text
hybrid-spike-avatar.vrm
compiled-spec.json
three-inspection.json
structural-validation.json
threejs-validation.json
toolchain.json
```

The fixture is generated from repository-owned procedural geometry. It does not
contain `loot-assets`, CharacterStudio models, marketplace assets, or Juana's
production character design.

## Acceptance contract

The workflow fails when any of the following is true:

- no `.vrm` file is produced;
- the file is not glTF 2.0 with `VRMC_vrm` 1.x;
- a required humanoid bone is missing;
- one of `blink`, `aa`, `ih`, `ou`, `ee`, or `oh` is missing;
- `@pixiv/three-vrm` cannot load the result;
- the expression manager or look-at controller is unavailable.
