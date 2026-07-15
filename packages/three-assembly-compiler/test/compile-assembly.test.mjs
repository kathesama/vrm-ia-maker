import assert from "node:assert/strict";
import path from "node:path";
import test from "node:test";

import { compileAssembly } from "../src/compile-assembly.mjs";

const DIGESTS = {
  base: "a".repeat(64),
  hair: "b".repeat(64),
  outfit: "c".repeat(64),
  accessory: "d".repeat(64),
};

function createFixture() {
  const root = path.resolve("test-fixtures");
  const assetPackPath = path.join(root, "asset-pack.json");
  const assetPack = {
    schema_version: "1.0",
    pack_id: "test-pack",
    provenance: {
      author: "Repository fixture",
      source: "generated test data",
      license: "CC0-1.0",
      commercial_use: true,
      modification_allowed: true,
      redistribution_allowed: true,
    },
    base_asset: {
      asset_id: "base-v1",
      path: "assets/base.glb",
      object_name: "Armature",
      sha256: DIGESTS.base,
      byte_length: 100,
      required_objects: ["Armature", "Body"],
      required_bones: ["hips", "head", "chest"],
      required_expressions: ["blink", "aa"],
    },
    components: [
      {
        asset_id: "hair-v1",
        slot: "hair",
        kind: "rigid_attachment",
        path: "assets/hair.glb",
        object_name: "Hair",
        sha256: DIGESTS.hair,
        byte_length: 20,
        required: true,
        attachment_bone: "head",
        required_bones: [],
        material_names: ["Hair_Primary"],
      },
      {
        asset_id: "outfit-v1",
        slot: "outfit",
        kind: "skinned_mesh",
        path: "assets/outfit.glb",
        object_name: "Outfit",
        sha256: DIGESTS.outfit,
        byte_length: 30,
        required: true,
        attachment_bone: null,
        required_bones: ["chest"],
        material_names: ["Outfit_Primary"],
      },
      {
        asset_id: "accessory-v1",
        slot: "accessory",
        kind: "rigid_attachment",
        path: "assets/accessory.glb",
        object_name: "Brooch",
        sha256: DIGESTS.accessory,
        byte_length: 10,
        required: false,
        attachment_bone: "chest",
        required_bones: [],
        material_names: ["Accessory_Primary"],
      },
    ],
  };
  const assembly = {
    schema_version: "1.0",
    character_id: "fixture-avatar",
    display_name: "Fixture Avatar",
    asset_pack_id: "test-pack",
    selections: {
      hair: { asset_id: "hair-v1", enabled: true },
      outfit: { asset_id: "outfit-v1", enabled: true },
      accessory: { asset_id: "accessory-v1", enabled: false },
    },
    material_overrides: {
      Hair_Primary: "#271C24",
      Outfit_Primary: "#202830",
    },
    metadata: {
      author: "Repository fixture",
      license: "CC0-1.0",
      commercial_use: true,
      redistribution: true,
    },
  };
  const baseAdapter = {
    schema_version: "1.0",
    adapter_id: "fixture-base-adapter",
    adapter_version: "1.0.0",
    base_asset_id: "base-v1",
    bones: { hips: "hips", head: "head" },
    expression_map: {
      blink: [{ shape_key: "blink", weight: 1.0 }],
      aa: [{ shape_key: "aa", weight: 0.8 }],
    },
    look_at: {
      horizontal_inner_degrees: 15.0,
      horizontal_outer_degrees: 30.0,
      vertical_down_degrees: 10.0,
      vertical_up_degrees: 12.0,
    },
  };
  const inspections = new Map([
    [
      path.join(root, "assets", "base.glb"),
      {
        sha256: DIGESTS.base,
        byteLength: 100,
        objectNames: ["Armature", "Body"],
        boneNames: ["hips", "head", "chest"],
        morphTargets: ["blink", "aa"],
        materialNames: ["Skin"],
        skinnedMeshes: {},
      },
    ],
    [
      path.join(root, "assets", "hair.glb"),
      {
        sha256: DIGESTS.hair,
        byteLength: 20,
        objectNames: ["Hair"],
        boneNames: [],
        morphTargets: [],
        materialNames: ["Hair_Primary"],
        skinnedMeshes: {},
      },
    ],
    [
      path.join(root, "assets", "outfit.glb"),
      {
        sha256: DIGESTS.outfit,
        byteLength: 30,
        objectNames: ["Outfit"],
        boneNames: ["chest"],
        morphTargets: [],
        materialNames: ["Outfit_Primary"],
        skinnedMeshes: { Outfit: ["chest"] },
      },
    ],
    [
      path.join(root, "assets", "accessory.glb"),
      {
        sha256: DIGESTS.accessory,
        byteLength: 10,
        objectNames: [],
        boneNames: [],
        morphTargets: [],
        materialNames: [],
        skinnedMeshes: {},
      },
    ],
  ]);
  const inspectionCalls = [];
  const inspectAsset = async (assetPath, options) => {
    inspectionCalls.push({ assetPath, options });
    const inspection = inspections.get(assetPath);
    assert.ok(inspection, `Unexpected inspection path: ${assetPath}`);
    return inspection;
  };

  return {
    assetPackPath,
    assetPack,
    assembly,
    baseAdapter,
    inspectAsset,
    inspections,
    inspectionCalls,
  };
}

test("compiles enabled and disabled selections using adapter mappings", async () => {
  const fixture = createFixture();

  const result = await compileAssembly(fixture);

  assert.equal(result.compiledSpec.schema_version, "1.1");
  assert.equal(result.compiledSpec.base_adapter_id, "fixture-base-adapter");
  assert.equal(result.compiledSpec.base_adapter_version, "1.0.0");
  assert.deepEqual(
    result.compiledSpec.components.map((component) => component.asset_id),
    ["hair-v1", "outfit-v1"],
  );
  assert.deepEqual(result.compiledSpec.disabled_components, [
    { asset_id: "accessory-v1", slot: "accessory", object_name: "Brooch" },
  ]);
  assert.deepEqual(result.compiledSpec.vrm_spec.bones, fixture.baseAdapter.bones);
  assert.deepEqual(
    result.compiledSpec.vrm_spec.expression_map,
    fixture.baseAdapter.expression_map,
  );
  assert.deepEqual(result.compiledSpec.vrm_spec.look_at, fixture.baseAdapter.look_at);
});

test("treats an omitted selection enabled flag as true", async () => {
  const fixture = createFixture();
  delete fixture.assembly.selections.hair.enabled;

  const result = await compileAssembly(fixture);

  assert.deepEqual(
    result.compiledSpec.components.map((component) => component.asset_id),
    ["hair-v1", "outfit-v1"],
  );
});

test("defaults omitted material overrides to an empty map", async () => {
  const fixture = createFixture();
  delete fixture.assembly.material_overrides;

  const result = await compileAssembly(fixture);

  assert.deepEqual(result.compiledSpec.material_overrides, {});
});

test("honors omitted schema version defaults", async () => {
  const fixture = createFixture();
  delete fixture.assetPack.schema_version;
  delete fixture.assembly.schema_version;
  delete fixture.baseAdapter.schema_version;

  const result = await compileAssembly(fixture);

  assert.equal(result.compiledSpec.schema_version, "1.1");
});

const selectionFailures = [
  {
    name: "rejects an asset-pack identifier mismatch",
    mutate: (fixture) => {
      fixture.assembly.asset_pack_id = "another-pack";
    },
    error: /references asset pack another-pack, expected test-pack/u,
  },
  {
    name: "rejects an unknown selected asset",
    mutate: (fixture) => {
      fixture.assembly.selections.hair.asset_id = "unknown-hair";
    },
    error: /selects unknown asset unknown-hair/u,
  },
  {
    name: "rejects a selected asset assigned to the wrong slot",
    mutate: (fixture) => {
      fixture.assembly.selections.hair.asset_id = "outfit-v1";
    },
    error: /belongs to outfit/u,
  },
  {
    name: "rejects a disabled required component",
    mutate: (fixture) => {
      fixture.assembly.selections.hair.enabled = false;
    },
    error: /Required component hair-v1 must be selected and enabled/u,
  },
  {
    name: "rejects an omitted required component",
    mutate: (fixture) => {
      delete fixture.assembly.selections.outfit;
    },
    error: /Required component outfit-v1 must be selected and enabled/u,
  },
  {
    name: "rejects an adapter bound to a different base asset",
    mutate: (fixture) => {
      fixture.baseAdapter.base_asset_id = "another-base";
    },
    error: /Base adapter references asset another-base, expected base-v1/u,
  },
];

for (const scenario of selectionFailures) {
  test(scenario.name, async () => {
    const fixture = createFixture();
    scenario.mutate(fixture);

    await assert.rejects(() => compileAssembly(fixture), scenario.error);
  });
}

test("checks integrity for every catalog asset and structure only where required", async () => {
  const fixture = createFixture();

  await compileAssembly(fixture);

  assert.deepEqual(
    fixture.inspectionCalls.map(({ assetPath, options }) => [path.basename(assetPath), options]),
    [
      ["base.glb", { structural: true }],
      ["hair.glb", { structural: true }],
      ["outfit.glb", { structural: true }],
      ["accessory.glb", { structural: false }],
    ],
  );
});

const integrationFailures = [
  {
    name: "rejects a relative asset path that escapes the pack directory",
    mutate: (fixture) => {
      fixture.assetPack.components[2].path = "../accessory.glb";
    },
    error: /path escapes the asset-pack directory/u,
  },
  {
    name: "rejects a digest mismatch for an unselected catalog asset",
    mutate: (fixture) => {
      const inspection = fixture.inspections.get(
        path.join(path.dirname(fixture.assetPackPath), "assets", "accessory.glb"),
      );
      inspection.sha256 = "e".repeat(64);
    },
    error: /SHA-256 mismatch for accessory-v1/u,
  },
  {
    name: "rejects a byte-length mismatch",
    mutate: (fixture) => {
      fixture.assetPack.base_asset.byte_length = 101;
    },
    error: /Byte-length mismatch for base-v1/u,
  },
  {
    name: "rejects a missing required base object",
    mutate: (fixture) => {
      fixture.assetPack.base_asset.required_objects.push("Head");
    },
    error: /Base asset objects is missing: Head/u,
  },
  {
    name: "rejects a missing required base bone",
    mutate: (fixture) => {
      fixture.assetPack.base_asset.required_bones.push("neck");
    },
    error: /Base asset bones is missing: neck/u,
  },
  {
    name: "rejects a missing required base expression",
    mutate: (fixture) => {
      fixture.assetPack.base_asset.required_expressions.push("happy");
    },
    error: /Base asset expressions is missing: happy/u,
  },
  {
    name: "rejects an adapter bone absent from the base",
    mutate: (fixture) => {
      fixture.baseAdapter.bones.neck = "neck";
    },
    error: /Adapter-mapped base bones is missing: neck/u,
  },
  {
    name: "rejects an adapter shape key absent from the base",
    mutate: (fixture) => {
      fixture.baseAdapter.expression_map.happy = [{ shape_key: "Smile", weight: 1.0 }];
    },
    error: /Adapter-mapped shape keys is missing: Smile/u,
  },
  {
    name: "rejects a missing selected component object",
    mutate: (fixture) => {
      fixture.assetPack.components[0].object_name = "MissingHair";
    },
    error: /Component hair-v1 objects is missing: MissingHair/u,
  },
  {
    name: "rejects a missing declared component material",
    mutate: (fixture) => {
      fixture.assetPack.components[0].material_names.push("Hair_Secondary");
    },
    error: /Component hair-v1 materials is missing: Hair_Secondary/u,
  },
  {
    name: "rejects an unknown rigid attachment bone",
    mutate: (fixture) => {
      fixture.assetPack.components[0].attachment_bone = "neck";
    },
    error: /references unknown attachment bone neck/u,
  },
  {
    name: "rejects a missing required skinned-mesh bone",
    mutate: (fixture) => {
      fixture.assetPack.components[1].required_bones.push("hips");
    },
    error: /Component outfit-v1 skin bones is missing: hips/u,
  },
  {
    name: "rejects a skinned-mesh bone absent from the base",
    mutate: (fixture) => {
      const inspection = fixture.inspections.get(
        path.join(path.dirname(fixture.assetPackPath), "assets", "outfit.glb"),
      );
      inspection.skinnedMeshes.Outfit.push("neck");
    },
    error: /uses bones absent from the base: neck/u,
  },
  {
    name: "rejects an object that is not a skinned mesh",
    mutate: (fixture) => {
      const inspection = fixture.inspections.get(
        path.join(path.dirname(fixture.assetPackPath), "assets", "outfit.glb"),
      );
      inspection.skinnedMeshes = {};
    },
    error: /does not expose a skinned mesh/u,
  },
  {
    name: "rejects a material override absent from selected assets",
    mutate: (fixture) => {
      fixture.assembly.material_overrides.Accessory_Primary = "#FFFFFF";
    },
    error: /Material overrides reference unknown materials: Accessory_Primary/u,
  },
];

for (const scenario of integrationFailures) {
  test(scenario.name, async () => {
    const fixture = createFixture();
    scenario.mutate(fixture);

    await assert.rejects(() => compileAssembly(fixture), scenario.error);
  });
}
