// Regression controls: JavaScript remains intact while declarations are broken.
import assert from "node:assert/strict";
import {execFileSync, spawnSync} from "node:child_process";
import {mkdtempSync, readFileSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";

assert.equal(process.argv.length, 3, "usage: node tools/test_smoke_npm.mjs distribution.tgz");
const distribution = resolve(process.argv[2]);
const smoke = fileURLToPath(new URL("smoke_npm.mjs", import.meta.url));
const controls = [
  {
    name: "empty declaration exports", diagnostic: /TS2305/,
    mutate(directory) {
      writeFileSync(join(directory, "package/dist/index.d.ts"), "export {};\n");
    },
  },
  {
    name: "missing transitive declaration", diagnostic: /TS7016/,
    mutate(directory) {
      rmSync(join(directory, "package/dist/types.d.ts"));
    },
  },
  {
    name: "widened input type", diagnostic: /TS2578/,
    mutate(directory) {
      const path = join(directory, "package/dist/factory.d.ts");
      const original = readFileSync(path, "utf8");
      assert.match(original, /runId: string;/);
      writeFileSync(path, original.replace("runId: string;", "runId: any;"));
    },
  },
];

for (const control of controls) {
  test(`packed consumer rejects ${control.name}`, () => {
    const directory = mkdtempSync(join(tmpdir(), "agentrust-npm-regression-"));
    try {
      execFileSync("tar", ["-xzf", distribution, "-C", directory]);
      control.mutate(directory);
      const mutant = join(directory, "mutant.tgz");
      execFileSync("tar", ["-czf", mutant, "-C", directory, "package"]);
      const result = spawnSync(process.execPath, [smoke, mutant], {encoding: "utf8"});
      assert.ifError(result.error);
      const output = result.stdout + result.stderr;
      // Confirm failure is in declaration compilation, not install/runtime.
      assert.match(output, /# pass 4/, output);
      assert.equal(result.status, 1, output);
      assert.match(output, control.diagnostic, output);
    } finally {
      rmSync(directory, {recursive: true, force: true});
    }
  });
}
