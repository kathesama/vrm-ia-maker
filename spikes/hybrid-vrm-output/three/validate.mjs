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

const [vrmPath, outputReportPath] = process.argv.slice(2);
if (!vrmPath || !outputReportPath) {
  throw new Error("Usage: node validate.mjs <avatar.vrm> <report.json>");
}

function parseGlbJson(bytes) {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const magic = view.getUint32(0, true);
  if (magic !== 0x46546c67) throw new Error("The file is not a GLB container.");
  const chunkLength = view.getUint32(12, true);
  const chunkType = view.getUint32(16, true);
  if (chunkType !== 0x4e4f534a) throw new Error("The first GLB chunk is not JSON.");
  const jsonBytes = bytes.subarray(20, 20 + chunkLength);
  return JSON.parse(new TextDecoder().decode(jsonBytes).replace(/\u0000+$/u, ""));
}

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
if (!vrmExtension) {
  throw new Error("The Three.js-loaded file does not contain VRMC_vrm.");
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

for (const expressionName of requiredExpressions) {
  vrm.expressionManager.setValue(expressionName, 0.25);
}
vrm.update(0);
for (const expressionName of requiredExpressions) {
  vrm.expressionManager.setValue(expressionName, 0.0);
}
vrm.update(0);

const report = {
  validator: "@pixiv/three-vrm",
  three_vrm_loaded: true,
  vrm_spec_version: vrmExtension.specVersion ?? null,
  required_bones: requiredBones,
  required_expressions: requiredExpressions,
  look_at_available: true,
  expression_manager_available: true,
  scene_object_count: (() => {
    let count = 0;
    gltf.scene.traverse(() => {
      count += 1;
    });
    return count;
  })(),
  sha256: crypto.createHash("sha256").update(bytes).digest("hex"),
  byte_length: bytes.byteLength,
};

await fs.mkdir(path.dirname(outputReportPath), { recursive: true });
await fs.writeFile(outputReportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
console.log(`Three.js validated ${vrmPath}`);
