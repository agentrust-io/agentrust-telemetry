import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {EvidenceAccumulator, finalizeTrace, SchemaValidator, TraceFinalizationError} from "../src/index.js";
import type {NormalizedEvent, TraceCodec, TraceConfiguration} from "../src/index.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const fixture = (name: string): NormalizedEvent => JSON.parse(readFileSync(`${root}/conformance/fixtures/valid/${name}`, "utf8")) as NormalizedEvent;
const validator = SchemaValidator.bundled();
const config: TraceConfiguration = {subject: "spiffe://example.test/agent/workflow", modelProvider: "example", modelId: "example-model", modelVersion: "2026-08", buildDigest: `sha256:${"b".repeat(64)}`, buildSlsaLevel: 1, originKind: "self", originProducer: "example-runtime", appraisalVerifier: "https://example.test/verifier", classificationTaxonomy: "example.enterprise.v1", classificationOrder: ["public", "internal", "confidential", "restricted"]};
class RecordingCodec implements TraceCodec<Record<string, unknown>> { profileV02 = "tag:github.com,2026:agentrust-trace/v0.2"; calls: string[] = []; failVerify = false; signRecord(record: Record<string, unknown>, key: unknown) { this.calls.push("sign"); assert.equal(key, "private"); return {...record, signature: "signed"}; } validateRecord(record: Record<string, unknown>) { this.calls.push("validate"); assert.equal(record.signature, "signed"); } publicKey(key: unknown) { this.calls.push("publicKey"); assert.equal(key, "private"); return "public"; } verifyRecord(record: Record<string, unknown>, key: unknown, options: {maxAgeSeconds: number | null}) { this.calls.push("verify"); assert.equal(record.signature, "signed"); assert.equal(key, "public"); assert.equal(options.maxAgeSeconds, null); if (this.failVerify) throw new Error("bad signature"); } }
function snapshot(extra: NormalizedEvent[] = [], completeness: "complete" | "incomplete" = "complete") { const accumulator = new EvidenceAccumulator("run-governed-sdlc-001", validator); accumulator.append(fixture("policy-decision.json")); accumulator.append(fixture("data-flow.json")); extra.forEach((event) => accumulator.append(event)); return accumulator.seal(completeness); }

test("finalizer derives claims then signs, validates, and self-verifies", () => {
  const codec = new RecordingCodec(); const evidence = snapshot(); const record = finalizeTrace(evidence, config, {signingKey: "private", codec});
  assert.deepEqual(codec.calls, ["sign", "validate", "publicKey", "verify"]);
  assert.deepEqual(record.runtime, {platform: "software-only", measurement: `sha256:${evidence.chainDigest}`});
  assert.deepEqual(record.policy, {bundle_hash: `sha256:${"a".repeat(64)}`, enforcement_mode: "enforce"});
  assert.equal(record.data_class, "confidential"); assert.deepEqual(record.appraisal, {status: "contraindicated", verifier: "https://example.test/verifier", timestamp: 1787079600}); assert.equal(record.tool_transcript, undefined);
});
test("tool transcript uses the shared RFC 8785 sequence/event digest", () => {
  const record = finalizeTrace(snapshot([fixture("action.json")]), config, {signingKey: "private", codec: new RecordingCodec()});
  assert.deepEqual(record.tool_transcript, {hash: "sha256:c697a0cb7991d61a4b4a7454de3be3a24046cbffb62f5fc14784ce52ccafe497", call_count: 1});
  const changed = fixture("action.json"); changed.outcome = "error"; changed.error_type = "remote_error";
  assert.notEqual((finalizeTrace(snapshot([changed]), config, {signingKey: "private", codec: new RecordingCodec()}).tool_transcript as Record<string, unknown>).hash, (record.tool_transcript as Record<string, unknown>).hash);
});
test("linked approval resolves a challenge while an unrelated approval does not", () => {
  const policy = fixture("policy-decision.json"); policy.decision = "challenge";
  const approval = fixture("approval.json"); approval.event_type = "approval.approved"; approval.policy_event_id = policy.event_id;
  const make = (item: NormalizedEvent) => { const accumulator = new EvidenceAccumulator("run-governed-sdlc-001", validator); accumulator.append(policy); accumulator.append(item); accumulator.append(fixture("data-flow.json")); return finalizeTrace(accumulator.seal("complete"), config, {signingKey: "private", codec: new RecordingCodec()}); };
  assert.equal((make(approval).appraisal as Record<string, unknown>).status, "affirming");
  approval.policy_event_id = "018f0f7d-7a13-7cc2-8000-000000000099"; approval.event_id = "018f0f7d-7a13-7cc2-8000-000000000098";
  assert.equal((make(approval).appraisal as Record<string, unknown>).status, "warning");
});
test("finalization refuses incomplete evidence, conflicts, unranked data, and missing trust inputs", () => {
  const open = new EvidenceAccumulator("run-governed-sdlc-001", validator); open.append(fixture("policy-decision.json"));
  assert.throws(() => finalizeTrace(open.snapshot(), config, {signingKey: "private", codec: new RecordingCodec()}), /sealed/);
  assert.throws(() => finalizeTrace(snapshot([], "incomplete"), config, {signingKey: "private", codec: new RecordingCodec()}), /completeness/);
  assert.throws(() => finalizeTrace(snapshot(), config, {signingKey: null, codec: new RecordingCodec()}), /signing key/);
  assert.throws(() => finalizeTrace(snapshot(), {...config, classificationOrder: ["public", "internal"]}, {signingKey: "private", codec: new RecordingCodec()}), /unranked/);
  const conflicting = fixture("policy-decision.json"); conflicting.event_id = "018f0f7d-7a13-7cc2-8000-000000000099"; ((conflicting.policy as Record<string, unknown>).bundle_digest as Record<string, unknown>).value = "f".repeat(64);
  assert.throws(() => finalizeTrace(snapshot([conflicting]), config, {signingKey: "private", codec: new RecordingCodec()}), /conflicting policy bundle/);
});
test("codec validation or self-verification failure is fail-closed", () => {
  const codec = new RecordingCodec(); codec.failVerify = true;
  assert.throws(() => finalizeTrace(snapshot(), config, {signingKey: "private", codec}), TraceFinalizationError);
  assert.deepEqual(codec.calls, ["sign", "validate", "publicKey", "verify"]);
});
