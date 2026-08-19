import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {EvidenceAccumulator, EvidencePersistenceError, SchemaValidator, TelemetryClient} from "../src/index.js";
import type {EvidenceEntry, NormalizedEvent} from "../src/index.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const validator = SchemaValidator.bundled();
const fixture = (name: string): NormalizedEvent => JSON.parse(readFileSync(`${root}/conformance/fixtures/valid/${name}`, "utf8")) as NormalizedEvent;

test("evidence chain matches the shared Python and TypeScript golden vector", () => {
  const golden = JSON.parse(readFileSync(`${root}/compatibility/golden/evidence-chain.json`, "utf8")) as {profile: string; run_id: string; entries: Array<{fixture: string; sequence: number; previous_digest: string | null; digest: string}>};
  const accumulator = new EvidenceAccumulator(golden.run_id, validator);
  const entries = golden.entries.map((expected) => accumulator.append(fixture(expected.fixture)));
  assert.equal(accumulator.snapshot().canonicalizationProfile, golden.profile);
  entries.forEach((actual, index) => {
    const expected = golden.entries[index]!;
    assert.equal(actual.sequence, expected.sequence);
    assert.equal(actual.previousDigest ?? null, expected.previous_digest);
    assert.equal(actual.digest, expected.digest);
  });
});

test("durable acknowledgement is fail-closed, retryable, and copy-isolated", () => {
  const calls: EvidenceEntry[] = [];
  let acknowledge = false;
  const accumulator = new EvidenceAccumulator("run-governed-sdlc-001", validator, {durableAppend: (entry) => { calls.push(entry); entry.event.run_id = "callback-mutated"; return acknowledge; }});
  assert.equal(accumulator.mode, "callback");
  assert.throws(() => accumulator.append(fixture("usage.json")), EvidencePersistenceError);
  assert.equal(accumulator.snapshot().entries.length, 0);
  acknowledge = true;
  const accepted = accumulator.append(fixture("usage.json"));
  accepted.event.run_id = "caller-mutated";
  assert.equal(accumulator.snapshot().entries[0]!.event.run_id, "run-governed-sdlc-001");
  assert.equal(calls.length, 2);
});

test("cross-run, duplicate, overflow, invalid number, and sealed mutations are rejected", () => {
  const accumulator = new EvidenceAccumulator("run-governed-sdlc-001", validator, {maxEvents: 1});
  const wrongRun = fixture("usage.json"); wrongRun.run_id = "other";
  assert.throws(() => accumulator.append(wrongRun), /does not match/);
  const first = fixture("policy-decision.json"); accumulator.append(first);
  assert.throws(() => accumulator.append(first), /duplicate/);
  assert.throws(() => accumulator.append(fixture("usage.json")), /maxEvents/);
  assert.equal(accumulator.seal("incomplete").completeness, "incomplete");
  assert.throws(() => accumulator.append(fixture("usage.json")), /sealed/);

  const nonFinite = new EvidenceAccumulator("run-governed-sdlc-001", validator);
  const event = fixture("usage.json"); (event.cost as Record<string, unknown>).amount = Number.NaN;
  assert.throws(() => nonFinite.append(event), /must be number|cannot be canonicalized/);
  assert.equal(nonFinite.snapshot().entries.length, 0);
});

test("reentrant durable callbacks cannot corrupt sequence state", () => {
  let accumulator: EvidenceAccumulator;
  accumulator = new EvidenceAccumulator("run-governed-sdlc-001", validator, {durableAppend: () => { accumulator.append(fixture("usage.json")); return true; }});
  assert.throws(() => accumulator.append(fixture("policy-decision.json")), EvidencePersistenceError);
  assert.equal(accumulator.snapshot().entries.length, 0);
});

test("client does not project an event when evidence persistence fails", () => {
  const events: unknown[] = [];
  const accumulator = new EvidenceAccumulator("run-governed-sdlc-001", validator, {durableAppend: () => false});
  const span = {spanContext: () => ({traceId: "4bf92f3577b34da6a3ce929d0e0e4736", spanId: "00f067aa0ba902b7", traceFlags: 1}), addEvent: (...args: unknown[]) => events.push(args)};
  assert.throws(() => new TelemetryClient(validator, {spanResolver: () => span, evidenceSink: accumulator}).emit(fixture("policy-decision.json")), EvidencePersistenceError);
  assert.deepEqual(events, []);
});
