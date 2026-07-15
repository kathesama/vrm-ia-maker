import { randomUUID } from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";

import { compileAssembly } from "./compile-assembly.mjs";
import { inspectGlb } from "./inspect-glb.mjs";

const USAGE =
  "Usage: node src/cli.mjs <asset-pack.json> <assembly.json> " +
  "<base-adapter.json> <compiled-spec.json> <inspection.json>";

async function readJson(filePath, label) {
  let content;
  try {
    content = await fs.readFile(filePath, "utf8");
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Cannot read ${label} ${filePath}: ${message}`, { cause: error });
  }
  try {
    return JSON.parse(content);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`Cannot parse ${label} ${filePath}: ${message}`, { cause: error });
  }
}

async function exists(filePath) {
  try {
    await fs.access(filePath);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") {
      return false;
    }
    throw error;
  }
}

function normalizedOutputPath(filePath) {
  const resolved = path.resolve(filePath);
  return process.platform === "win32" ? resolved.toLowerCase() : resolved;
}

async function rejectExistingOutputs(compiledPath, inspectionPath) {
  if (normalizedOutputPath(compiledPath) === normalizedOutputPath(inspectionPath)) {
    throw new Error("Compiled and inspection output targets must be different files.");
  }
  for (const outputPath of [compiledPath, inspectionPath]) {
    if (await exists(outputPath)) {
      throw new Error(`Output target already exists: ${outputPath}.`);
    }
  }
}

function temporaryPath(outputPath) {
  return path.join(
    path.dirname(outputPath),
    `.${path.basename(outputPath)}.${randomUUID()}.tmp`,
  );
}

async function writeOutputsAtomically(compiledPath, inspectionPath, result) {
  const compiledTemporaryPath = temporaryPath(compiledPath);
  const inspectionTemporaryPath = temporaryPath(inspectionPath);
  let compiledCreated = false;
  let inspectionCreated = false;

  try {
    await Promise.all([
      fs.mkdir(path.dirname(compiledPath), { recursive: true }),
      fs.mkdir(path.dirname(inspectionPath), { recursive: true }),
    ]);
    await Promise.all([
      fs.writeFile(
        compiledTemporaryPath,
        `${JSON.stringify(result.compiledSpec, null, 2)}\n`,
        { encoding: "utf8", flag: "wx" },
      ),
      fs.writeFile(
        inspectionTemporaryPath,
        `${JSON.stringify(result.inspection, null, 2)}\n`,
        { encoding: "utf8", flag: "wx" },
      ),
    ]);
    await fs.link(compiledTemporaryPath, compiledPath);
    compiledCreated = true;
    await fs.link(inspectionTemporaryPath, inspectionPath);
    inspectionCreated = true;
    await Promise.all([
      fs.rm(compiledTemporaryPath),
      fs.rm(inspectionTemporaryPath),
    ]);
  } catch (error) {
    await Promise.allSettled([
      fs.rm(compiledTemporaryPath, { force: true }),
      fs.rm(inspectionTemporaryPath, { force: true }),
      compiledCreated ? fs.rm(compiledPath, { force: true }) : Promise.resolve(),
      inspectionCreated ? fs.rm(inspectionPath, { force: true }) : Promise.resolve(),
    ]);
    throw error;
  }
}

export async function runCompilerCli({
  args,
  compile = compileAssembly,
  inspectAsset = inspectGlb,
}) {
  if (args.length !== 5 || args.some((argument) => !argument)) {
    throw new Error(USAGE);
  }
  const [assetPackPath, assemblyPath, baseAdapterPath, compiledPath, inspectionPath] =
    args.map((argument) => path.resolve(argument));
  await rejectExistingOutputs(compiledPath, inspectionPath);

  const [assetPack, assembly, baseAdapter] = await Promise.all([
    readJson(assetPackPath, "asset-pack manifest"),
    readJson(assemblyPath, "assembly manifest"),
    readJson(baseAdapterPath, "base-model adapter manifest"),
  ]);
  const result = await compile({
    assetPackPath,
    assetPack,
    assembly,
    baseAdapter,
    inspectAsset,
  });
  await writeOutputsAtomically(compiledPath, inspectionPath, result);
  return result;
}

async function main() {
  try {
    const result = await runCompilerCli({ args: process.argv.slice(2) });
    process.stdout.write(
      `Compiled ${result.compiledSpec.character_id} into ${path.resolve(process.argv[5])}.\n`,
    );
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    process.stderr.write(`Compilation failed: ${message}\n`);
    process.exitCode = 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main();
}
