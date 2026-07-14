import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { GLTFLoader } from "three/examples/jsm/loaders/GLTFLoader.js";

if (!globalThis.self) {
  globalThis.self = globalThis;
}

const [manifestPath, basePath, outputSpecPath, inspectionPath] = process.argv.slice(2);
if (!manifestPath || !basePath || !outputSpecPath || !inspectionPath) {
  throw new Error(
    "Usage: node compose.mjs <assembly.manifest.json> <base.glb> <compiled-spec.json> <inspection.json>",
  );
}

const manifest = JSON.parse(await fs.readFile(manifestPath, "utf8"));
const source = await fs.readFile(basePath);
const arrayBuffer = source.buffer.slice(source.byteOffset, source.byteOffset + source.byteLength);
const loader = new GLTFLoader();
const gltf = await loader.parseAsync(arrayBuffer, `${path.dirname(basePath)}/`);

const objectNames = [];
const meshNames = [];
const materialNames = new Set();
const morphTargets = new Set();
const boneNames = new Set();

gltf.scene.traverse((object) => {
  if (object.name) objectNames.push(object.name);
  if (object.isMesh || object.isSkinnedMesh) {
    meshNames.push(object.name);
    const materials = Array.isArray(object.material) ? object.material : [object.material];
    for (const material of materials) {
      if (material?.name) materialNames.add(material.name);
    }
    for (const name of Object.keys(object.morphTargetDictionary ?? {})) {
      morphTargets.add(name);
    }
  }
  if (object.isBone && object.name) boneNames.add(object.name);
});

const missingObjects = manifest.base_asset.required_objects.filter(
  (name) => !objectNames.includes(name),
);
if (missingObjects.length > 0) {
  throw new Error(`Three.js composition failed; missing objects: ${missingObjects.join(", ")}`);
}

const missingExpressions = manifest.required_expressions.filter(
  (name) => !morphTargets.has(name),
);
if (missingExpressions.length > 0) {
  throw new Error(
    `Three.js composition failed; missing morph targets: ${missingExpressions.join(", ")}`,
  );
}

const disabledComponents = manifest.components.filter((component) => !component.enabled);
if (disabledComponents.length > 0) {
  throw new Error("The initial spike does not support disabled components.");
}

const boneMap = {
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

const missingBones = Object.values(boneMap).filter((name) => !boneNames.has(name));
if (missingBones.length > 0) {
  throw new Error(`Three.js composition failed; missing bones: ${missingBones.join(", ")}`);
}

const expressionMap = Object.fromEntries(
  [
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
  ].map((name) => [name, [{ shape_key: name, weight: 1.0 }]]),
);

const compiledSpec = {
  spec_version: "1.0",
  avatar_id: manifest.character_id,
  display_name: manifest.display_name,
  base_asset_id: "generated/hybrid-spike-base",
  body: { height_scale: 1.0 },
  face: {
    skin_color: manifest.materials.skin,
    eye_color: manifest.materials.eyes,
  },
  bones: boneMap,
  expression_map: expressionMap,
  look_at: {
    horizontal_inner_degrees: 15.0,
    horizontal_outer_degrees: 15.0,
    vertical_down_degrees: 10.0,
    vertical_up_degrees: 10.0,
  },
  metadata: manifest.metadata,
  assembly_manifest: {
    schema_version: manifest.schema_version,
    components: manifest.components,
  },
};

const inspection = {
  engine: "three",
  character_id: manifest.character_id,
  object_names: objectNames.sort(),
  mesh_names: meshNames.sort(),
  material_names: [...materialNames].sort(),
  bone_names: [...boneNames].sort(),
  morph_targets: [...morphTargets].sort(),
  required_objects_present: true,
  required_bones_present: true,
  required_expressions_present: true,
};

await fs.mkdir(path.dirname(outputSpecPath), { recursive: true });
await fs.writeFile(outputSpecPath, `${JSON.stringify(compiledSpec, null, 2)}\n`, "utf8");
await fs.writeFile(inspectionPath, `${JSON.stringify(inspection, null, 2)}\n`, "utf8");

console.log(`Three.js compiled ${manifest.character_id} into ${outputSpecPath}`);
