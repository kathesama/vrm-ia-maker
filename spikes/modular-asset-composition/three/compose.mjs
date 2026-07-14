import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

if (!globalThis.self) {
  globalThis.self = globalThis;
}
if (!globalThis.ProgressEvent) {
  globalThis.ProgressEvent = class ProgressEvent {
    constructor(type, init = {}) {
      this.type = type;
      Object.assign(this, init);
    }
  };
}

const BONE_MAP = {
  hips: "hips",
  spine: "spine",
  chest: "chest",
  upperChest: "upperChest",
  neck: "neck",
  head: "head",
  leftShoulder: "leftShoulder",
  leftUpperArm: "leftUpperArm",
  leftLowerArm: "leftLowerArm",
  leftHand: "leftHand",
  rightShoulder: "rightShoulder",
  rightUpperArm: "rightUpperArm",
  rightLowerArm: "rightLowerArm",
  rightHand: "rightHand",
  leftUpperLeg: "leftUpperLeg",
  leftLowerLeg: "leftLowerLeg",
  leftFoot: "leftFoot",
  rightUpperLeg: "rightUpperLeg",
  rightLowerLeg: "rightLowerLeg",
  rightFoot: "rightFoot",
  leftEye: "L_Eye",
  rightEye: "R_Eye",
  jaw: "jaw",
};

const VRM_EXPRESSIONS = [
  "blink",
  "blinkLeft",
  "blinkRight",
  "aa",
  "ih",
  "ou",
  "ee",
  "oh",
  "happy",
  "sad",
  "angry",
  "surprised",
  "relaxed",
];

function assertObject(value, label) {
  if (!value || typeof value !== "object" || Array.isArray(value)) {
    throw new Error(`${label} must be an object.`);
  }
  return value;
}

function assertString(value, label) {
  if (typeof value !== "string" || value.length === 0) {
    throw new Error(`${label} must be a non-empty string.`);
  }
  return value;
}

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function resolveAssetPath(manifestPath, assetPath) {
  const root = path.dirname(path.resolve(manifestPath));
  const resolved = path.isAbsolute(assetPath)
    ? path.resolve(assetPath)
    : path.resolve(root, assetPath);
  if (!path.isAbsolute(assetPath) && resolved !== root && !resolved.startsWith(`${root}${path.sep}`)) {
    throw new Error(`Asset path escapes the asset-pack directory: ${assetPath}`);
  }
  return resolved;
}

async function readJson(filePath) {
  return JSON.parse(await fs.readFile(filePath, "utf8"));
}

async function inspectGlb(filePath) {
  const bytes = await fs.readFile(filePath);
  const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
  const loader = new GLTFLoader();
  const gltf = await loader.parseAsync(arrayBuffer, `${path.dirname(filePath)}/`);

  const objectNames = new Set();
  const meshNames = new Set();
  const materialNames = new Set();
  const morphTargets = new Set();
  const boneNames = new Set();
  const skinnedMeshes = new Map();

  gltf.scene.traverse((object) => {
    if (object.name) objectNames.add(object.name);
    if (object.isBone && object.name) boneNames.add(object.name);
    if (object.isMesh || object.isSkinnedMesh) {
      if (object.name) meshNames.add(object.name);
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of materials) {
        if (material?.name) materialNames.add(material.name);
      }
      for (const name of Object.keys(object.morphTargetDictionary ?? {})) {
        morphTargets.add(name);
      }
    }
    if (object.isSkinnedMesh && object.name) {
      skinnedMeshes.set(
        object.name,
        new Set((object.skeleton?.bones ?? []).map((bone) => bone.name).filter(Boolean)),
      );
    }
  });

  return {
    path: filePath,
    byteLength: bytes.byteLength,
    sha256: sha256(bytes),
    objectNames,
    meshNames,
    materialNames,
    morphTargets,
    boneNames,
    skinnedMeshes,
  };
}

function verifyDigest(asset, inspection) {
  if (!/^[a-f0-9]{64}$/u.test(asset.sha256 ?? "")) {
    throw new Error(`Asset ${asset.asset_id} does not have a sealed SHA-256 value.`);
  }
  if (asset.sha256 !== inspection.sha256) {
    throw new Error(
      `SHA-256 mismatch for ${asset.asset_id}: expected ${asset.sha256}, got ${inspection.sha256}.`,
    );
  }
  if (asset.byte_length !== inspection.byteLength) {
    throw new Error(
      `Byte-length mismatch for ${asset.asset_id}: expected ${asset.byte_length}, got ${inspection.byteLength}.`,
    );
  }
}

function requireMembers(actual, required, label) {
  const missing = required.filter((name) => !actual.has(name));
  if (missing.length > 0) {
    throw new Error(`${label} is missing: ${missing.join(", ")}`);
  }
}

function hexToRgb(value, fallback) {
  if (typeof value !== "string" || !/^#[A-Fa-f0-9]{6}$/u.test(value)) return fallback;
  return {
    r: Number.parseInt(value.slice(1, 3), 16) / 255,
    g: Number.parseInt(value.slice(3, 5), 16) / 255,
    b: Number.parseInt(value.slice(5, 7), 16) / 255,
  };
}

function expressionMap() {
  return Object.fromEntries(
    VRM_EXPRESSIONS.map((name) => [name, [{ shape_key: name, weight: 1.0 }]]),
  );
}

export async function compileAssembly({
  assetPackPath,
  assemblyPath,
  outputSpecPath,
  inspectionPath,
}) {
  const assetPack = assertObject(await readJson(assetPackPath), "AssetPackManifest");
  const assembly = assertObject(await readJson(assemblyPath), "AssemblyManifest");

  if (assetPack.schema_version !== "1.0" || assembly.schema_version !== "1.0") {
    throw new Error("Both manifests must use schema_version 1.0.");
  }
  if (assembly.asset_pack_id !== assetPack.pack_id) {
    throw new Error(
      `Assembly references asset pack ${assembly.asset_pack_id}, expected ${assetPack.pack_id}.`,
    );
  }
  assertString(assembly.character_id, "AssemblyManifest.character_id");
  assertString(assembly.display_name, "AssemblyManifest.display_name");

  if (!Array.isArray(assetPack.components) || !Array.isArray(assembly.selections)) {
    throw new Error("AssetPackManifest components and AssemblyManifest selections must be arrays.");
  }

  const selectionSlots = assembly.selections.map((selection) => selection.slot);
  const duplicateSlots = selectionSlots.filter((slot, index) => selectionSlots.indexOf(slot) !== index);
  if (duplicateSlots.length > 0) {
    throw new Error(`Assembly has duplicate selections for slots: ${[...new Set(duplicateSlots)].join(", ")}`);
  }

  const componentById = new Map(assetPack.components.map((component) => [component.asset_id, component]));
  const selectedComponents = [];
  const disabledComponents = [];
  for (const selection of assembly.selections) {
    const component = componentById.get(selection.asset_id);
    if (!component) {
      throw new Error(`Assembly selects unknown asset ${selection.asset_id}.`);
    }
    if (component.slot !== selection.slot) {
      throw new Error(
        `Assembly selects ${selection.asset_id} for ${selection.slot}, but the asset belongs to ${component.slot}.`,
      );
    }
    if (selection.enabled) selectedComponents.push(component);
    else disabledComponents.push(component);
  }

  for (const component of assetPack.components.filter((entry) => entry.required)) {
    if (!selectedComponents.some((entry) => entry.asset_id === component.asset_id)) {
      throw new Error(`Required slot ${component.slot} is not enabled.`);
    }
  }

  const baseAsset = assertObject(assetPack.base_asset, "AssetPackManifest.base_asset");
  const basePath = resolveAssetPath(assetPackPath, baseAsset.path);
  const baseInspection = await inspectGlb(basePath);
  verifyDigest(baseAsset, baseInspection);
  requireMembers(
    baseInspection.objectNames,
    baseAsset.required_objects ?? [],
    "Base asset objects",
  );
  requireMembers(baseInspection.boneNames, baseAsset.required_bones ?? [], "Base asset bones");
  requireMembers(
    baseInspection.morphTargets,
    baseAsset.required_expressions ?? [],
    "Base asset morph targets",
  );
  requireMembers(
    baseInspection.morphTargets,
    assembly.required_expressions ?? [],
    "Assembly-required expressions",
  );

  const allAssets = [baseAsset, ...assetPack.components];
  const digestReports = [];
  for (const asset of allAssets) {
    const assetPath = resolveAssetPath(assetPackPath, asset.path);
    const bytes = await fs.readFile(assetPath);
    const report = {
      asset_id: asset.asset_id,
      path: assetPath,
      byte_length: bytes.byteLength,
      sha256: sha256(bytes),
    };
    if (report.sha256 !== asset.sha256 || report.byte_length !== asset.byte_length) {
      throw new Error(`Asset integrity validation failed for ${asset.asset_id}.`);
    }
    digestReports.push(report);
  }

  const selectedReports = [];
  const availableMaterials = new Set(baseInspection.materialNames);
  for (const component of selectedComponents) {
    const componentPath = resolveAssetPath(assetPackPath, component.path);
    const componentInspection = await inspectGlb(componentPath);
    verifyDigest(component, componentInspection);
    requireMembers(
      componentInspection.objectNames,
      [component.object_name],
      `Component ${component.asset_id} objects`,
    );
    for (const materialName of componentInspection.materialNames) {
      availableMaterials.add(materialName);
    }

    if (component.kind === "rigid_attachment") {
      if (!component.attachment_bone || !baseInspection.boneNames.has(component.attachment_bone)) {
        throw new Error(
          `Rigid component ${component.asset_id} references unknown attachment bone ${component.attachment_bone}.`,
        );
      }
    } else if (component.kind === "skinned_mesh") {
      const skinBones = componentInspection.skinnedMeshes.get(component.object_name);
      if (!skinBones) {
        throw new Error(`Component ${component.asset_id} does not expose a skinned mesh.`);
      }
      requireMembers(
        skinBones,
        component.required_bones ?? [],
        `Component ${component.asset_id} skin bones`,
      );
      const unknownBones = [...skinBones].filter((boneName) => !baseInspection.boneNames.has(boneName));
      if (unknownBones.length > 0) {
        throw new Error(
          `Component ${component.asset_id} uses bones absent from the base: ${unknownBones.join(", ")}`,
        );
      }
    } else {
      throw new Error(`Unsupported component kind: ${component.kind}`);
    }

    selectedReports.push({
      asset_id: component.asset_id,
      slot: component.slot,
      kind: component.kind,
      path: componentPath,
      object_name: component.object_name,
      attachment_bone: component.attachment_bone ?? null,
      required_bones: component.required_bones ?? [],
      material_names: [...componentInspection.materialNames].sort(),
      bone_names: [...componentInspection.boneNames].sort(),
    });
  }

  const materialOverrides = assertObject(
    assembly.material_overrides ?? {},
    "AssemblyManifest.material_overrides",
  );
  const unknownMaterials = Object.keys(materialOverrides).filter(
    (materialName) => !availableMaterials.has(materialName),
  );
  if (unknownMaterials.length > 0) {
    throw new Error(`Material overrides reference unknown materials: ${unknownMaterials.join(", ")}`);
  }

  const compiledSpec = {
    schema_version: "1.0",
    character_id: assembly.character_id,
    display_name: assembly.display_name,
    asset_pack_id: assetPack.pack_id,
    provenance: assetPack.provenance,
    base_asset: {
      asset_id: baseAsset.asset_id,
      path: basePath,
      object_name: baseAsset.object_name,
      sha256: baseAsset.sha256,
    },
    components: selectedReports,
    disabled_components: disabledComponents.map((component) => ({
      asset_id: component.asset_id,
      slot: component.slot,
      object_name: component.object_name,
    })),
    material_overrides: materialOverrides,
    vrm_spec: {
      spec_version: "1.0",
      avatar_id: assembly.character_id,
      display_name: assembly.display_name,
      base_asset_id: baseAsset.asset_id,
      body: { height_scale: 1.0 },
      face: {
        skin_color: { r: 0.72, g: 0.42, b: 0.30 },
        eye_color: { r: 0.20, g: 0.55, b: 0.78 },
      },
      hair: {
        color: hexToRgb(materialOverrides.Hair_Primary, { r: 0.17, g: 0.11, b: 0.15 }),
      },
      tint_blend: { hair: 1.0, skin: 0.0, eye: 0.0 },
      subsurface_scattering: { enabled: false },
      bones: BONE_MAP,
      expression_map: expressionMap(),
      look_at: {
        horizontal_inner_degrees: 15.0,
        horizontal_outer_degrees: 15.0,
        vertical_down_degrees: 10.0,
        vertical_up_degrees: 10.0,
      },
      metadata: assembly.metadata,
      assembly_manifest: {
        schema_version: assembly.schema_version,
        selected_assets: selectedReports.map((component) => component.asset_id),
        disabled_assets: disabledComponents.map((component) => component.asset_id),
      },
    },
  };

  const inspection = {
    compiler: "three",
    character_id: assembly.character_id,
    asset_pack_id: assetPack.pack_id,
    base: {
      path: basePath,
      object_names: [...baseInspection.objectNames].sort(),
      bone_names: [...baseInspection.boneNames].sort(),
      morph_targets: [...baseInspection.morphTargets].sort(),
      material_names: [...baseInspection.materialNames].sort(),
    },
    selected_components: selectedReports,
    disabled_components: compiledSpec.disabled_components,
    asset_integrity: digestReports,
    material_overrides: materialOverrides,
    required_objects_present: true,
    required_bones_present: true,
    required_expressions_present: true,
    skeletons_compatible: true,
  };

  await fs.mkdir(path.dirname(outputSpecPath), { recursive: true });
  await fs.writeFile(outputSpecPath, `${JSON.stringify(compiledSpec, null, 2)}\n`, "utf8");
  await fs.writeFile(inspectionPath, `${JSON.stringify(inspection, null, 2)}\n`, "utf8");
  console.log(`Three.js compiled ${assembly.character_id} into ${outputSpecPath}`);
  return { compiledSpec, inspection };
}

async function main() {
  const [assetPackPath, assemblyPath, outputSpecPath, inspectionPath] = process.argv.slice(2);
  if (!assetPackPath || !assemblyPath || !outputSpecPath || !inspectionPath) {
    throw new Error(
      "Usage: node compose.mjs <asset-pack.json> <assembly.json> <compiled-spec.json> <inspection.json>",
    );
  }
  await compileAssembly({ assetPackPath, assemblyPath, outputSpecPath, inspectionPath });
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
