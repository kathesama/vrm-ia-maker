import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { inspectGlb } from "../../packages/three-assembly-compiler/src/inspect-glb.mjs";

const REQUIRED_OBJECTS = new Set([
  "Juana_Production_Rig",
  "Juana_Production_Body",
  "Juana_Production_Head",
  "Juana_Production_Eye_L",
  "Juana_Production_Eye_R",
  "Juana_Production_Eyebrows",
  "Juana_Production_Eyelashes",
]);
const REQUIRED_BONES = new Set([
  "root",
  "spine05",
  "spine03",
  "spine01",
  "neck03",
  "head",
  "eyeL",
  "eyeR",
  "jaw",
]);
const FORBIDDEN_DONOR_PATTERNS = [
  /^DonorVRM_/i,
  /SAM3D/i,
  /Highpoly/i,
  /Hunyuan/i,
  /^Armature$/,
  /^Body$/,
  /^Head$/,
  /^Hair_Rigid$/,
  /^Icosphere$/,
  /^LeftEyeMesh$/,
  /^OutfitMesh$/,
  /^RightEyeMesh$/,
];

function missing(required, actual) {
  const available = new Set(actual);
  return [...required].filter((item) => !available.has(item)).sort();
}

function exportedBoneName(blenderBoneName) {
  return blenderBoneName.replaceAll(".", "");
}

export function validateJuanaInspection(inspection, adapter = null) {
  const missingObjects = missing(REQUIRED_OBJECTS, inspection.objectNames);
  const requiredBones = new Set(REQUIRED_BONES);
  if (adapter) {
    for (const boneName of Object.values(adapter.bones)) {
      requiredBones.add(exportedBoneName(boneName));
    }
  }
  const missingBones = missing(requiredBones, inspection.boneNames);
  if (missingObjects.length || missingBones.length) {
    throw new Error(
      `Provisional Juana GLB contract failed: missing objects=${JSON.stringify(
        missingObjects,
      )}, bones=${JSON.stringify(missingBones)}.`,
    );
  }

  const forbiddenObjects = inspection.objectNames.filter((name) =>
    FORBIDDEN_DONOR_PATTERNS.some((pattern) => pattern.test(name)),
  );
  if (forbiddenObjects.length) {
    throw new Error(
      `Donor or procedural spike geometry survived the GLB export: ${JSON.stringify(
        forbiddenObjects.sort(),
      )}.`,
    );
  }

  const productionNames = inspection.objectNames.filter((name) =>
    name.startsWith("Juana_Production_"),
  );
  const hairNames = productionNames.filter((name) => name.startsWith("Juana_Production_Hair_"));
  const outfitNames = productionNames.filter((name) =>
    name.startsWith("Juana_Production_Outfit_"),
  );
  if (!hairNames.length || !outfitNames.length) {
    throw new Error(
      `Production hair and outfit blockouts must survive export: hair=${hairNames.length}, ` +
        `outfit=${outfitNames.length}.`,
    );
  }

  for (const meshName of ["Juana_Production_Body", "Juana_Production_Head"]) {
    if (!Object.hasOwn(inspection.skinnedMeshes, meshName)) {
      throw new Error(`${meshName} must load as a skinned mesh through Three.js.`);
    }
    const missingMeshBones = missing(requiredBones, inspection.skinnedMeshes[meshName]);
    if (missingMeshBones.length) {
      throw new Error(
        `${meshName} skin is missing required bones: ${JSON.stringify(missingMeshBones)}.`,
      );
    }
  }
}

async function main() {
  const [, , glbArgument, reportArgument, adapterArgument, repositoryArgument] =
    process.argv;
  if (!glbArgument || !reportArgument || !adapterArgument || !repositoryArgument) {
    throw new Error(
      "Usage: node inspect_glb.mjs <input.glb> <report.json> " +
        "<base-adapter.json> <repository-root>",
    );
  }
  const glbPath = path.resolve(glbArgument);
  const reportPath = path.resolve(reportArgument);
  const adapterPath = path.resolve(adapterArgument);
  const repositoryRoot = path.resolve(repositoryArgument);
  const repositoryRelative = (physicalPath) =>
    path.relative(repositoryRoot, physicalPath).split(path.sep).join("/");
  const adapter = JSON.parse(await fs.readFile(adapterPath, "utf8"));
  const inspection = await inspectGlb(glbPath);
  validateJuanaInspection(inspection, adapter);

  const report = {
    schema_version: "1.0",
    status: "passed",
    loader: {
      package: "three",
      version: "0.183.2",
      implementation: "GLTFLoader",
    },
    adapter: {
      path: repositoryRelative(adapterPath),
      adapter_id: adapter.adapter_id,
      base_asset_id: adapter.base_asset_id,
    },
    asset: {
      path: repositoryRelative(glbPath),
      ...inspection,
    },
    provisional_boundary: {
      visual_canon_approved: false,
      final_vrm: false,
      expressions_deferred: true,
      next_gate: "Kathy visual and topology review",
    },
  };
  await fs.mkdir(path.dirname(reportPath), { recursive: true });
  await fs.writeFile(reportPath, `${JSON.stringify(report, null, 2)}\n`, "utf8");
  console.log("GH22_THREE_INSPECTION_PASSED");
}

const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : null;
const modulePath = fileURLToPath(import.meta.url);
if (invokedPath === modulePath) {
  await main();
}
