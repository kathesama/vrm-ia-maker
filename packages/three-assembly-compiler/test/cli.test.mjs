import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { promisify } from "node:util";

import test from "node:test";

import { runCompilerCli } from "../src/cli.mjs";

const execFileAsync = promisify(execFile);
const cliPath = fileURLToPath(new URL("../src/cli.mjs", import.meta.url));

async function createCliFixture(context) {
  const root = await fs.mkdtemp(path.join(os.tmpdir(), "three-assembly-cli-"));
  context.after(() => fs.rm(root, { recursive: true, force: true }));
  const assetPackPath = path.join(root, "asset-pack.json");
  const assemblyPath = path.join(root, "assembly.json");
  const baseAdapterPath = path.join(root, "base-adapter.json");
  await Promise.all(
    [assetPackPath, assemblyPath, baseAdapterPath].map((filePath) =>
      fs.writeFile(filePath, "{}\n", "utf8"),
    ),
  );
  return {
    root,
    assetPackPath,
    assemblyPath,
    baseAdapterPath,
    compiledPath: path.join(root, "output", "compiled.json"),
    inspectionPath: path.join(root, "output", "inspection.json"),
  };
}

function cliArgs(fixture) {
  return [
    fixture.assetPackPath,
    fixture.assemblyPath,
    fixture.baseAdapterPath,
    fixture.compiledPath,
    fixture.inspectionPath,
  ];
}

async function pathExists(filePath) {
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

test("writes both compiler outputs after successful compilation", async (context) => {
  const fixture = await createCliFixture(context);
  const compile = async () => ({
    compiledSpec: { schema_version: "1.1", character_id: "fixture" },
    inspection: { compiler: "fixture-inspector" },
  });

  await runCompilerCli({ args: cliArgs(fixture), compile, inspectAsset: async () => ({}) });

  assert.deepEqual(JSON.parse(await fs.readFile(fixture.compiledPath, "utf8")), {
    schema_version: "1.1",
    character_id: "fixture",
  });
  assert.deepEqual(JSON.parse(await fs.readFile(fixture.inspectionPath, "utf8")), {
    compiler: "fixture-inspector",
  });
});

test("refuses existing output without replacing it", async (context) => {
  const fixture = await createCliFixture(context);
  await fs.mkdir(path.dirname(fixture.compiledPath), { recursive: true });
  await fs.writeFile(fixture.compiledPath, "existing\n", "utf8");
  let compileCalled = false;

  await assert.rejects(
    () =>
      runCompilerCli({
        args: cliArgs(fixture),
        compile: async () => {
          compileCalled = true;
          return {};
        },
        inspectAsset: async () => ({}),
      }),
    /Output target already exists/u,
  );

  assert.equal(compileCalled, false);
  assert.equal(await fs.readFile(fixture.compiledPath, "utf8"), "existing\n");
  assert.equal(await pathExists(fixture.inspectionPath), false);
});

test("leaves no output or temporary files after compiler failure", async (context) => {
  const fixture = await createCliFixture(context);

  await assert.rejects(
    () =>
      runCompilerCli({
        args: cliArgs(fixture),
        compile: async () => {
          throw new Error("Selected component is incompatible.");
        },
        inspectAsset: async () => ({}),
      }),
    /Selected component is incompatible/u,
  );

  assert.equal(await pathExists(fixture.compiledPath), false);
  assert.equal(await pathExists(fixture.inspectionPath), false);
  assert.equal(await pathExists(path.dirname(fixture.compiledPath)), false);
});

test("process exits non-zero with an English usage diagnostic", async () => {
  await assert.rejects(
    () => execFileAsync(process.execPath, [cliPath]),
    (error) => {
      assert.notEqual(error.code, 0);
      assert.match(error.stderr, /Compilation failed: Usage:/u);
      return true;
    },
  );
});
