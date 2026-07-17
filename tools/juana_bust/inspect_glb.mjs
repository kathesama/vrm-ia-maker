import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { inspectGlb } from "../../packages/three-assembly-compiler/src/inspect-glb.mjs";

const REQUIRED_OBJECTS = new Set([
  "Juana_Armature",
  "Juana_Body",
  "Juana_Eye_L",
  "Juana_Eye_R",
  "Juana_Eyebrows",
  "Juana_Eyelashes",
  "Juana_Hair_Close_Cut_Base",
  "Juana_Hair_Long_Right",
  "Juana_Outfit_Inner",
  "Juana_Outfit_Jacket",
  "Juana_Choker",
  "Juana_Choker_Gold_Closure",
  "Juana_Choker_Text_Export",
  "Juana_Necklace_Export",
  "Juana_Gold_Pendant",
  "Juana_Gold_Hoop_L",
  "Juana_Gold_Hoop_R",
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
const REQUIRED_MORPHS = new Set([
  "blink",
  "blinkLeft",
  "blinkRight",
  "aa",
  "ih",
  "ou",
  "ee",
  "oh",
]);

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
  const requiredMorphs = new Set(REQUIRED_MORPHS);
  if (adapter) {
    for (const boneName of Object.values(adapter.bones)) {
      requiredBones.add(exportedBoneName(boneName));
    }
    for (const bindings of Object.values(adapter.expression_map)) {
      for (const binding of bindings) {
        requiredMorphs.add(binding.shape_key);
      }
    }
  }
  const missingBones = missing(requiredBones, inspection.boneNames);
  const missingMorphs = missing(requiredMorphs, inspection.morphTargets);
  if (missingObjects.length || missingBones.length || missingMorphs.length) {
    throw new Error(
      `Provisional Juana GLB contract failed: missing objects=${JSON.stringify(
        missingObjects,
      )}, bones=${JSON.stringify(missingBones)}, morphs=${JSON.stringify(missingMorphs)}.`,
    );
  }
  if (!Object.hasOwn(inspection.skinnedMeshes, "Juana_Body")) {
    throw new Error("Juana_Body must load as a skinned mesh through Three.js.");
  }
  const bodyBones = inspection.skinnedMeshes.Juana_Body;
  const missingBodyBones = missing(requiredBones, bodyBones);
  if (missingBodyBones.length) {
    throw new Error(
      `Juana_Body skin is missing required bones: ${JSON.stringify(missingBodyBones)}.`,
    );
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
      next_gate: "Kathy visual review",
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
