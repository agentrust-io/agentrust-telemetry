// Exercise the packed consumer surface outside the checkout, without dev tools.
import assert from "node:assert/strict";
import {execFileSync} from "node:child_process";
import {mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import {join, resolve} from "node:path";
import {fileURLToPath} from "node:url";

assert.equal(process.argv.length, 3, "usage: node tools/smoke_npm.mjs distribution.tgz");
const distribution = resolve(process.argv[2]);
const root = fileURLToPath(new URL("../", import.meta.url));
const metadata = JSON.parse(readFileSync(join(root, "packages/typescript/package.json"), "utf8"));
const fixtures = {};
for (const kind of ["valid", "invalid"]) {
  const directory = join(root, "conformance/fixtures", kind);
  fixtures[kind] = readdirSync(directory).filter(name => name.endsWith(".json")).sort()
    .map(name => ({name, event: JSON.parse(readFileSync(join(directory, name), "utf8"))}));
  assert.ok(fixtures[kind].length > 0, `missing ${kind} controls`);
}
const golden = JSON.parse(readFileSync(join(root, "compatibility/golden/event-factory.json"), "utf8"));
const directory = mkdtempSync(join(tmpdir(), "agentrust-npm-"));
try {
  writeFileSync(join(directory, "package.json"), JSON.stringify({private: true, type: "module"}));
  writeFileSync(join(directory, "controls.json"), JSON.stringify({metadata, fixtures, golden}));
  execFileSync("npm", ["install", "--ignore-scripts", "--no-audit", "--no-fund", distribution],
    {cwd: directory, stdio: "inherit"});
  writeFileSync(join(directory, "smoke.test.mjs"), `
import assert from "node:assert/strict";
import {existsSync, readFileSync, realpathSync} from "node:fs";
import {join, sep} from "node:path";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {SchemaValidator, EventValidationError, EventFactory} from "@agentrust-io/telemetry";
const {metadata, fixtures, golden} = JSON.parse(readFileSync("controls.json", "utf8"));
const installed = realpathSync(join("node_modules", metadata.name));
test("installed identity, module origin and declarations", () => {
  const actual = JSON.parse(readFileSync(join(installed, "package.json"), "utf8"));
  assert.equal(actual.name, metadata.name);
  assert.equal(actual.version, metadata.version);
  const module = realpathSync(fileURLToPath(import.meta.resolve(metadata.name)));
  assert.ok(module.startsWith(installed + sep));
  assert.ok(existsSync(join(installed, actual.types)), "missing type declarations");
});
const validator = SchemaValidator.bundled();
test("bundled schemas accept all conformant controls", () => {
  for (const {name, event} of fixtures.valid) {
    assert.doesNotThrow(() => validator.validate(event), name);
  }
});
test("bundled schemas refuse all invalid controls", () => {
  for (const {name, event} of fixtures.invalid) {
    assert.throws(() => validator.validate(event), EventValidationError, name);
  }
});
test("installed event construction matches the golden control", () => {
  const factory = new EventFactory(validator, {name: "parity-test", version: "1.0.0"},
    () => 1787079000000000000n, () => "018f0f7d-7a13-7cc2-8000-000000000042");
  assert.deepEqual(factory.build("usage.recorded",
    {runId: "run-1", agentId: "agent-1", workflowId: "workflow-1"},
    {scope: "model_call", operation: "chat", input_tokens: 7}), golden);
});
`);
  execFileSync(process.execPath, ["--test", "smoke.test.mjs"], {cwd: directory, stdio: "inherit"});
} finally {
  rmSync(directory, {recursive: true, force: true});
}
