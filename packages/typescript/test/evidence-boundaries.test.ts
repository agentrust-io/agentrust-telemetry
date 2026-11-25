import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {EvidenceAccumulator, SchemaValidator} from "../src/index.js";
import {entryDigest} from "../src/evidence-digest.js";
import type {NormalizedEvent} from "../src/index.js";

const validator = SchemaValidator.bundled();
const event = JSON.parse(readFileSync(new URL("../../../conformance/fixtures/valid/policy-decision.json", import.meta.url), "utf8")) as NormalizedEvent;

test("evidence capacity accepts positive safe integers and rejects runtime type coercion", () => {
  for (const maxEvents of [1, 10_000, Number.MAX_SAFE_INTEGER]) {
    assert.doesNotThrow(() => new EvidenceAccumulator(event.run_id, validator, {maxEvents}));
  }
  for (const value of [true, false, "10", 0, -1, 1.5, NaN, Infinity, Number.MAX_SAFE_INTEGER + 1]) {
    assert.throws(() => new EvidenceAccumulator(event.run_id, validator, {maxEvents: value as number}), /maxEvents/);
  }
});

test("previous digest requires the exact lowercase representation", () => {
  const valid = "ab".repeat(32);
  assert.match(entryDigest(1, valid, event), /^[0-9a-f]{64}$/);
  assert.match(entryDigest(0, undefined, event), /^[0-9a-f]{64}$/);
  for (const value of ["", valid.toUpperCase(), valid + "ZZ", " " + valid, valid + "\n", "ab".repeat(31), null, 12]) {
    assert.throws(() => entryDigest(1, value as string, event), /previous digest/);
  }
});
