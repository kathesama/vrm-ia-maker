# SPIKE-2: Modular Asset Composition

## Question

Can independent base, hair, outfit, and accessory GLB assets be selected through
an explicit manifest, compiled with Three.js, assembled in Blender, and exported
as a valid VRM 1.x file without losing the runtime contract?

## Success condition

The spike succeeds only when two distinct assemblies produce two valid VRM 1.x
files:

- both contain the required humanoid bones and speech expressions;
- both load through `@pixiv/three-vrm`;
- both share one skeleton between body and outfit;
- both attach hair to the head bone;
- only the assembly that enables the accessory contains its object.

## Boundary

The fixtures are procedural test geometry. They are not Juana's final visual
model. The spike validates the modular build path that later production assets
will use.

## Evidence

The `Modular VRM output spike` GitHub Actions workflow uploads generated GLBs,
sealed manifests, compiled specifications, Blender assembly reports, final VRM
files, and structural and Three.js validation reports.
