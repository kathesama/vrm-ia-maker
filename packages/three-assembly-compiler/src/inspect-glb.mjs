import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
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

function sha256(bytes) {
  return crypto.createHash("sha256").update(bytes).digest("hex");
}

function emptyStructure() {
  return {
    objectNames: [],
    boneNames: [],
    morphTargets: [],
    materialNames: [],
    skinnedMeshes: {},
  };
}

async function resolveContainedPath(filePath, allowedRoot) {
  if (!allowedRoot) {
    return filePath;
  }
  const [realRoot, realFilePath] = await Promise.all([
    fs.realpath(allowedRoot),
    fs.realpath(filePath),
  ]);
  const relative = path.relative(realRoot, realFilePath);
  if (
    relative === ".." ||
    relative.startsWith(`..${path.sep}`) ||
    path.isAbsolute(relative)
  ) {
    throw new Error(`Relative asset path resolves outside the asset-pack directory: ${filePath}.`);
  }
  return realFilePath;
}

function inspectScene(scene) {
  const objectNames = new Set();
  const boneNames = new Set();
  const morphTargets = new Set();
  const materialNames = new Set();
  const skinnedMeshes = new Map();

  scene.traverse((object) => {
    if (object.name) {
      objectNames.add(object.name);
    }
    if (object.isBone && object.name) {
      boneNames.add(object.name);
    }
    if (object.isMesh || object.isSkinnedMesh) {
      const materials = Array.isArray(object.material) ? object.material : [object.material];
      for (const material of materials) {
        if (material?.name) {
          materialNames.add(material.name);
        }
      }
      for (const name of Object.keys(object.morphTargetDictionary ?? {})) {
        morphTargets.add(name);
      }
    }
    if (object.isSkinnedMesh && object.name) {
      skinnedMeshes.set(
        object.name,
        (object.skeleton?.bones ?? []).map((bone) => bone.name).filter(Boolean).sort(),
      );
    }
  });

  return {
    objectNames: [...objectNames].sort(),
    boneNames: [...boneNames].sort(),
    morphTargets: [...morphTargets].sort(),
    materialNames: [...materialNames].sort(),
    skinnedMeshes: Object.fromEntries([...skinnedMeshes.entries()].sort(([a], [b]) =>
      a.localeCompare(b),
    )),
  };
}

export async function inspectGlb(filePath, { structural = true, allowedRoot = null } = {}) {
  const physicalPath = await resolveContainedPath(filePath, allowedRoot);
  const bytes = await fs.readFile(physicalPath);
  const integrity = {
    byteLength: bytes.byteLength,
    sha256: sha256(bytes),
  };
  if (!structural) {
    return { ...integrity, ...emptyStructure() };
  }

  const arrayBuffer = bytes.buffer.slice(
    bytes.byteOffset,
    bytes.byteOffset + bytes.byteLength,
  );
  const resourceRoot = pathToFileURL(`${path.dirname(physicalPath)}${path.sep}`).href;
  try {
    const loader = new GLTFLoader();
    const gltf = await loader.parseAsync(arrayBuffer, resourceRoot);
    return { ...integrity, ...inspectScene(gltf.scene) };
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Failed to inspect GLB ${filePath}: ${message}`, { cause: error });
  }
}
