import assert from "node:assert/strict";
import crypto from "node:crypto";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { inspectGlb } from "../src/inspect-glb.mjs";

function createStructuralGlb() {
  const binary = Buffer.alloc(208);
  for (let vertex = 0; vertex < 3; vertex += 1) {
    binary.writeFloatLE(1, 96 + vertex * 16);
  }
  for (let diagonal = 0; diagonal < 4; diagonal += 1) {
    binary.writeFloatLE(1, 144 + (diagonal * 4 + diagonal) * 4);
  }

  const document = {
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [
      { name: "Armature", children: [1, 2] },
      { name: "hips" },
      { name: "BodyMesh", mesh: 0, skin: 0 },
    ],
    meshes: [
      {
        name: "BodyMesh",
        weights: [0],
        extras: { targetNames: ["blink"] },
        primitives: [
          {
            attributes: { POSITION: 0, JOINTS_0: 2, WEIGHTS_0: 3 },
            targets: [{ POSITION: 1 }],
            material: 0,
          },
        ],
      },
    ],
    materials: [{ name: "BodyMaterial" }],
    skins: [{ joints: [1], skeleton: 1, inverseBindMatrices: 4 }],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126,
        count: 3,
        type: "VEC3",
        min: [0, 0, 0],
        max: [0, 0, 0],
      },
      {
        bufferView: 1,
        componentType: 5126,
        count: 3,
        type: "VEC3",
        min: [0, 0, 0],
        max: [0, 0, 0],
      },
      { bufferView: 2, componentType: 5123, count: 3, type: "VEC4" },
      { bufferView: 3, componentType: 5126, count: 3, type: "VEC4" },
      { bufferView: 4, componentType: 5126, count: 1, type: "MAT4" },
    ],
    bufferViews: [
      { buffer: 0, byteOffset: 0, byteLength: 36, target: 34962 },
      { buffer: 0, byteOffset: 36, byteLength: 36, target: 34962 },
      { buffer: 0, byteOffset: 72, byteLength: 24, target: 34962 },
      { buffer: 0, byteOffset: 96, byteLength: 48, target: 34962 },
      { buffer: 0, byteOffset: 144, byteLength: 64 },
    ],
    buffers: [{ byteLength: binary.byteLength }],
  };
  const json = Buffer.from(JSON.stringify(document), "utf8");
  const paddedJsonLength = Math.ceil(json.byteLength / 4) * 4;
  const totalLength = 12 + 8 + paddedJsonLength + 8 + binary.byteLength;
  const glb = Buffer.alloc(totalLength);
  glb.writeUInt32LE(0x46546c67, 0);
  glb.writeUInt32LE(2, 4);
  glb.writeUInt32LE(totalLength, 8);
  glb.writeUInt32LE(paddedJsonLength, 12);
  glb.writeUInt32LE(0x4e4f534a, 16);
  json.copy(glb, 20);
  glb.fill(0x20, 20 + json.byteLength, 20 + paddedJsonLength);
  const binaryHeader = 20 + paddedJsonLength;
  glb.writeUInt32LE(binary.byteLength, binaryHeader);
  glb.writeUInt32LE(0x004e4942, binaryHeader + 4);
  binary.copy(glb, binaryHeader + 8);
  return glb;
}

test("reads integrity metadata without parsing an unselected GLB", async (context) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "three-assembly-inspector-"));
  context.after(() => fs.rm(directory, { recursive: true, force: true }));
  const glbPath = path.join(directory, "catalog-only.glb");
  const bytes = Buffer.from("catalog integrity fixture", "utf8");
  await fs.writeFile(glbPath, bytes);

  const inspection = await inspectGlb(glbPath, { structural: false });

  assert.equal(inspection.byteLength, bytes.byteLength);
  assert.equal(
    inspection.sha256,
    crypto.createHash("sha256").update(bytes).digest("hex"),
  );
  assert.deepEqual(inspection.objectNames, []);
  assert.deepEqual(inspection.boneNames, []);
  assert.deepEqual(inspection.morphTargets, []);
  assert.deepEqual(inspection.materialNames, []);
  assert.deepEqual(inspection.skinnedMeshes, {});
});

test("uses Three.js to inspect selected GLB structure", async (context) => {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "three-assembly-inspector-"));
  context.after(() => fs.rm(directory, { recursive: true, force: true }));
  const glbPath = path.join(directory, "structural.glb");
  await fs.writeFile(glbPath, createStructuralGlb());

  const inspection = await inspectGlb(glbPath, { structural: true });

  assert.deepEqual(inspection.objectNames, ["Armature", "BodyMesh", "hips"]);
  assert.deepEqual(inspection.boneNames, ["hips"]);
  assert.deepEqual(inspection.morphTargets, ["blink"]);
  assert.deepEqual(inspection.materialNames, ["BodyMaterial"]);
  assert.deepEqual(inspection.skinnedMeshes, { BodyMesh: ["hips"] });
});
