import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";

import { VRMLoaderPlugin } from "@pixiv/three-vrm";
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

const [vrmPath, compiledSpecPath, outputReportPath] = process.argv.slice(2);
if (!vrmPath || !compiledSpecPath || !outputReportPath) {
  throw new Error("Usage: node validate.mjs <avatar.vrm> <compiled-spec.json> <report.json>");
}

function parseGlbJson(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  if (view.getUint32(0, true) !== 0x46546c67) {
    throw new Error("The file is not a GLB container.");
  }
  const chunkLength = view.getUint32(12, true);
  const chunkType = view.getUint32(16, true);
  if (chunkType !== 0x4e4f534a) {
    throw new Error("The first GLB chunk is not JSON.");
  }
  const jsonBytes = bytes.subarray(20, 20 + chunkLength);
  return JSON.parse(new TextDecoder().decode(jsonBytes).replace(/\u0000+$/u, ""));
}

function hasAncestor(object, ancestorName) {
  let current = object.parent;
  const visited = new Set();
  while (current && !visited.has(current)) {
    if (current.name === ancestorName) return true;
    visited.add(current);
    current = current.parent;
  }
  return false;
}

const compiled = JSON.parse(await fs.readFile(compiledSpecPath, "utf8"));
const bytes = await fs.readFile(vrmPath);
const arrayBuffer = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength);
const loader = new GLTFLoader();
loader.register((parser) => new VRMLoaderPlugin(parser));
const gltf = await loader.parseAsync(arrayBuffer, `${path.dirname(vrmPath)}/`);
const vrm = gltf.userData.vrm;
if (!vrm) {
  throw new Error("@pixiv/three-vrm did not create a VRM instance.");
}

const requiredBones = [
  "hips",
  "spine",
  "chest",
  "neck",
  "head",
  "leftUpperArm",
  "leftLowerArm",
  "leftHand",
  "rightUpperArm",
  "rightLowerArm",
  "rightHand",
  "leftUpperLeg",
  "leftLowerLeg",
  "leftFoot",
  "rightUpperLeg",
  "rightLowerLeg",
  "rightFoot",
];
const missingBones = requiredBones.filter(
  (name) => !vrm.humanoid?.getRawBoneNode?.(name),
);
if (missingBones.length > 0) {
  throw new Error(`Three.js VRM validation found missing bones: ${missingBones.join(", ")}`);
}

const glbJson = parseGlbJson(bytes);
const vrmExtension = glbJson.extensions?.VRMC_vrm;
if (!vrmExtension || !String(vrmExtension.specVersion ?? "").startsWith("1.")) {
  throw new Error("The Three.js-loaded file is not VRM 1.x.");
}
const presetExpressions = vrmExtension.expressions?.preset ?? {};
const requiredExpressions = ["blink", "aa", "ih", "ou", "ee", "oh"];
const missingExpressions = requiredExpressions.filter((name) => !(name in presetExpressions));
if (missingExpressions.length > 0) {
  throw new Error(
    `Three.js VRM validation found missing expressions: ${missingExpressions.join(", ")}`,
  );
}
if (!vrm.expressionManager) {
  throw new Error("The VRM expression manager is unavailable.");
}
if (!vrm.lookAt) {
  throw new Error("The VRM look-at controller is unavailable.");
}

const selectedObjects = compiled.components.map((component) => component.object_name);
const disabledObjects = compiled.disabled_components.map((component) => component.object_name);
const missingSelected = selectedObjects.filter((name) => !gltf.scene.getObjectByName(name));
const presentDisabled = disabledObjects.filter((name) => gltf.scene.getObjectByName(name));
if (missingSelected.length > 0) {
  throw new Error(`Three.js could not find selected components: ${missingSelected.join(", ")}`);
}
if (presentDisabled.length > 0) {
  throw new Error(`Three.js found disabled components: ${presentDisabled.join(", ")}`);
}

const body = gltf.scene.getObjectByName("Body");
const outfitComponent = compiled.components.find((component) => component.slot === "outfit");
const outfit = gltf.scene.getObjectByName(outfitComponent.object_name);
if (!body?.isSkinnedMesh || !outfit?.isSkinnedMesh) {
  throw new Error("Body and outfit must load as SkinnedMesh objects.");
}
if (body.skeleton !== outfit.skeleton) {
  throw new Error("Body and outfit do not share the same Three.js skeleton instance.");
}

const hairComponent = compiled.components.find((component) => component.slot === "hair");
const hair = gltf.scene.getObjectByName(hairComponent.object_name);
if (!hair || !hasAncestor(hair, hairComponent.attachment_bone)) {
  throw new Error(
    `Hair does not load below attachment bone ${hairComponent.attachment_bone}.`,
  );
}

for (const expressionName of requiredExpressions) {
  vrm.expressionManager.setValue(expressionName, 0.25);
}
vrm.update(0);
for (const expressionName of requiredExpressions) {
  vrm.expressionManager.setValue(expressionName, 0.0);
}
vrm.update(0);

let sceneObjectCount = 0;
gltf.scene.traverse(() => {
  sceneObjectCount += 1;
});

const report = {
  validator: "@pixiv/three-vrm",
  valid: true,
  character_id: compiled.character_id,
  three_vrm_loaded: true,
  vrm_spec_version: vrmExtension.specVersion ?? null,
  required_bones: requiredBones,
  required_expressions: requiredExpressions,
  selected_component_objects: selectedObjects,
  disabled_component_objects: disabledObjects,
  selected_components_present: true,
  disabled_components_absent: true,
  body_and_outfit_are_skinned: true,
  body_and_outfit_share_skeleton: true,
  hair_attachment_verified: true,
  look_at_available: true,
  expression_manager_available: true,
  scene_object_count: sceneObjectCount,
  sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
  byte_length: bytes.byteLength,
};

await fs.mkdir(path.dirname(outputReportPath), { recursive: true });
await fs.writeFile(outputReportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(`Three.js validated modular VRM ${vrmPath}`);
