import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import process from "node:process";
import test from "node:test";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import { compileAssembly } from "../src/compile-assembly.mjs";

const execFileAsync = promisify(execFile);
const fixtureDirectory = fileURLToPath(new URL("./fixtures/", import.meta.url));
const repositoryRoot = fileURLToPath(new URL("../../../", import.meta.url));

async function readJson(fileName) {
  return JSON.parse(await fs.readFile(path.join(fixtureDirectory, fileName), "utf8"));
}

test("emits a compiled document accepted by the production Pydantic loaders", async (context) => {
  const outputDirectory = await fs.mkdtemp(path.join(os.tmpdir(), "assembly-conformance-"));
  context.after(() => fs.rm(outputDirectory, { recursive: true, force: true }));
  const assetPackPath = path.join(fixtureDirectory, "asset-pack.json");
  const assetPack = await readJson("asset-pack.json");
  const assembly = await readJson("assembly.json");
  const baseAdapter = await readJson("base-adapter.json");
  const inspections = {
    "base.glb": {
      sha256: "a".repeat(64),
      byteLength: 100,
      objectNames: ["Armature", "Body"],
      boneNames: ["hips", "head"],
      morphTargets: ["blink", "aa"],
      materialNames: ["Skin"],
      skinnedMeshes: {},
    },
    "hair.glb": {
      sha256: "b".repeat(64),
      byteLength: 20,
      objectNames: ["Hair"],
      boneNames: [],
      morphTargets: [],
      materialNames: ["Hair_Primary"],
      skinnedMeshes: {},
    },
    "accessory.glb": {
      sha256: "c".repeat(64),
      byteLength: 10,
      objectNames: [],
      boneNames: [],
      morphTargets: [],
      materialNames: [],
      skinnedMeshes: {},
    },
  };
  const result = await compileAssembly({
    assetPackPath,
    assetPack,
    assembly,
    baseAdapter,
    inspectAsset: async (assetPath) => inspections[path.basename(assetPath)],
  });
  const compiledPath = path.join(outputDirectory, "compiled.json");
  await fs.writeFile(compiledPath, `${JSON.stringify(result.compiledSpec, null, 2)}\n`, "utf8");

  const python = process.env.PYTHON ?? (process.platform === "win32" ? "python" : "python3");
  const script = [
    "import sys",
    "from pathlib import Path",
    "from vrm_ia_maker import (load_asset_pack_manifest, load_assembly_manifest, load_base_model_adapter_manifest, load_compiled_assembly_spec)",
    "load_asset_pack_manifest(Path(sys.argv[1]))",
    "load_assembly_manifest(Path(sys.argv[2]))",
    "load_base_model_adapter_manifest(Path(sys.argv[3]))",
    "compiled = load_compiled_assembly_spec(Path(sys.argv[4]))",
    "print(f'{compiled.schema_version}:{compiled.base_adapter_id}')",
  ].join("; ");
  const { stdout } = await execFileAsync(
    python,
    [
      "-c",
      script,
      assetPackPath,
      path.join(fixtureDirectory, "assembly.json"),
      path.join(fixtureDirectory, "base-adapter.json"),
      compiledPath,
    ],
    {
      cwd: repositoryRoot,
      env: { ...process.env, PYTHONPATH: path.join(repositoryRoot, "src") },
    },
  );

  assert.equal(stdout.trim(), "1.1:cross-runtime-adapter");
});
