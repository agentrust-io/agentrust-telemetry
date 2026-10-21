import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {EvidenceAccumulator, EvidenceError, EvidencePersistenceError, SchemaValidator, TelemetryClient} from "../src/index.js";
import type {EvidenceEntry, NormalizedEvent} from "../src/index.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const read = (path: string) => JSON.parse(readFileSync(`${root}/${path}`, "utf8"));
const fixture = (name: string): NormalizedEvent => read(`conformance/fixtures/valid/${name}`) as NormalizedEvent;
const matrix = read("compatibility/golden/delivery-faults.json") as {
  fixtures: string[];
  cases: Array<{mode: string; delivered_indices: number[]; log_emitted: boolean; error_count: number}>;
};
const golden = read("compatibility/golden/evidence-chain.json") as {run_id: string; entries: Array<{digest: string}>};

for (const scenario of matrix.cases) {
  test(`delivery ${scenario.mode} preserves evidence and unknown completeness`, () => {
    const observed: Array<Record<string, unknown>> = [];
    const validator = SchemaValidator.bundled();
    const evidence = new EvidenceAccumulator(golden.run_id, validator);
    const client = new TelemetryClient(validator, {
      evidenceSink: evidence,
      logEmitter: {emit(record) {
        if (scenario.mode === "raise") throw new Error("synthetic delivery failure");
        if (scenario.mode === "drop") return;
        if (scenario.mode === "reverse") observed.unshift(record);
        else {
          observed.push(record);
          if (scenario.mode === "duplicate") observed.push(record);
        }
      }},
    });
    const events = matrix.fixtures.map(fixture);
    for (const event of events) {
      const result = client.emit(event);
      assert.equal(result.accepted, true);
      assert.equal(result.evidencePersisted, true);
      assert.equal(result.logEmitted, scenario.log_emitted);
      assert.equal(result.projectionErrors.length, scenario.error_count);
    }
    const snapshot = evidence.snapshot();
    assert.deepEqual(snapshot.entries.map(e => e.digest), golden.entries.map(e => e.digest));
    assert.deepEqual(observed.map(r => (r.body as NormalizedEvent).event_id),
      scenario.delivered_indices.map(i => events[i]!.event_id));
    assert.equal(snapshot.completeness, "unknown");
    assert.equal(snapshot.sealed, false);
    assert.equal(evidence.seal("unknown").completeness, "unknown");
  });
}

for (const failure of ["false", "exception"]) {
  test(`lost ${failure} acknowledgement retries without double projection`, () => {
    // An idempotent adopter-store test double; not durable storage.
    const committed = new Map<string, EvidenceEntry>();
    const attempts: EvidenceEntry[] = [];
    const projections: unknown[] = [];
    const validator = SchemaValidator.bundled();
    const event = fixture("policy-decision.json");
    const evidence = new EvidenceAccumulator(event.run_id, validator, {durableAppend(entry) {
      attempts.push(entry);
      const old = committed.get(entry.eventId);
      if (old) assert.deepEqual(entry, old);
      else committed.set(entry.eventId, entry);
      if (attempts.length === 1) {
        if (failure === "exception") throw new Error("commit happened; acknowledgement lost");
        return false;
      }
      return true;
    }});
    const client = new TelemetryClient(validator, {evidenceSink: evidence,
      logEmitter: {emit(record) {projections.push(record);}}});
    assert.throws(() => client.emit(event), EvidencePersistenceError);
    assert.equal(committed.size, 1);
    assert.deepEqual(evidence.snapshot().entries, []);
    assert.deepEqual(projections, []);
    assert.equal(client.emit(event).evidencePersisted, true);
    assert.deepEqual(attempts[0], attempts[1]);
    assert.equal(committed.size, 1);
    assert.equal(evidence.snapshot().entries.length, 1);
    assert.equal(projections.length, 1);
    assert.throws(() => client.emit(event), EvidenceError);
    assert.equal(attempts.length, 2);
    assert.equal(projections.length, 1);
  });
}
