import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";

import { compileAssembly } from "./compose.mjs";

const [assetPackPath, assemblyPath] = process.argv.slice(2);
if (!assetPackPath || !assemblyPath) {
  throw new Error("Usage: node negative-tests.mjs <asset-pack.json> <assembly.json>");
}

const originalPack = JSON.parse(await fs.readFile(assetPackPath, "utf8"));
const originalAssembly = JSON.parse(await fs.readFile(assemblyPath, "utf8"));
const assetPackRoot = path.dirname(path.resolve(assetPackPath));

function clone(value) {
  return JSON.parse(JSON.stringify(value));
}

function makeAssetPathsAbsolute(pack) {
  for (const asset of [pack.base_asset, ...pack.components]) {
    if (!path.isAbsolute(asset.path)) asset.path = path.resolve(assetPackRoot, asset.path);
  }
}

async function expectFailure(name, mutatePack, mutateAssembly) {
  const pack = clone(originalPack);
  const assembly = clone(originalAssembly);
  makeAssetPathsAbsolute(pack);
  mutatePack?.(pack);
  mutateAssembly?.(assembly);

  const temporaryDirectory = await fs.mkdtemp(path.join(os.tmpdir(), "modular-spike-negative-"));
  const packPath = path.join(temporaryDirectory, "asset-pack.json");
  const assemblyFile = path.join(temporaryDirectory, "assembly.json");
  await fs.writeFile(packPath, `${JSON.stringify(pack, null, 2)}\n`, "utf8");
  await fs.writeFile(assemblyFile, `${JSON.stringify(assembly, null, 2)}\n`, "utf8");

  try {
    await compileAssembly({
      assetPackPath: packPath,
      assemblyPath: assemblyFile,
      outputSpecPath: path.join(temporaryDirectory, "compiled.json"),
      inspectionPath: path.join(temporaryDirectory, "inspection.json"),
    });
  } catch (error) {
    console.log(`Negative contract passed: ${name} -> ${error.message}`);
    return;
  }
  throw new Error(`Negative contract did not fail: ${name}`);
}

await expectFailure(
  "missing required slot",
  null,
  (assembly) => {
    assembly.selections.find((selection) => selection.slot === "outfit").enabled = false;
  },
);

await expectFailure("hash mismatch", (pack) => {
  pack.base_asset.sha256 = "0".repeat(64);
});

await expectFailure("unknown attachment bone", (pack) => {
  pack.components.find((component) => component.slot === "hair").attachment_bone = "missingBone";
});

await expectFailure(
  "duplicate slot",
  null,
  (assembly) => {
    assembly.selections.push({ ...assembly.selections[0] });
  },
);

await expectFailure(
  "unknown material override",
  null,
  (assembly) => {
    assembly.material_overrides.MissingMaterial = "#112233";
  },
);

await expectFailure(
  "missing required expression",
  null,
  (assembly) => {
    assembly.required_expressions.push("missingExpression");
  },
);

await expectFailure("unknown skinned bone", (pack) => {
  pack.components.find((component) => component.slot === "outfit").required_bones.push(
    "missingBone",
  );
});

console.log("All modular assembly negative contracts passed.");
