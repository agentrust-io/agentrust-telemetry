import assert from "node:assert/strict";
import test from "node:test";
import {AgtGovernanceEventSink, agtPolicyDecision, cedarPolicyDecision, EventFactory, opaDecisionLog, SchemaValidator} from "../src/index.js";
import type {NormalizedEvent} from "../src/index.js";

const digest = {algorithm: "sha256", value: "a".repeat(64)};
const factory = new EventFactory(SchemaValidator.bundled(), {name: "adapter-tests", version: "1"}, () => 1787079000000000000n, () => "018f0f7d-7a13-7cc2-8000-000000000042");

test("OPA boolean decision logs preserve safe facts and match Python identifiers", () => {
  const source = {decision_id: "decision-123", labels: {version: "1.8.0"}, path: "/agents/allow", input: {secret: "must-not-copy"}, result: true, timestamp: "2026-08-18T12:34:56.123456789Z", metrics: {timer_rego_query_eval_ns: 4200}, ids: ["allow-agent"], trace_id: "4bf92f3577b34da6a3ce929d0e0e4736", span_id: "00f067aa0ba902b7"};
  const event = opaDecisionLog(factory, source, {runId: "run-1", agentId: "agent-1", actionType: "agent.invoke", resourceType: "agent", bundleDigest: digest});
  assert.equal(event.event_id, "f340f74c-976a-5bad-a542-dbac78522ee3");
  assert.equal(event.time_unix_nano, "1787056496123456789"); assert.equal(event.decision, "allow"); assert.equal(event.evaluation_duration_ns, 4200);
  assert.equal(JSON.stringify(event).includes("must-not-copy"), false);
  assert.deepEqual(event.reason_codes, ["opa.rule:allow-agent"]);
});

test("OPA rejects ambiguous results, malformed collections, and normalized invalid dates", () => {
  const options = {runId: "run-1", agentId: "agent-1", actionType: "agent.invoke", resourceType: "agent", bundleDigest: digest, opaVersion: "1.8.0"};
  assert.throws(() => opaDecisionLog(factory, {decision_id: "d", result: {allow: true}}, options), /explicit resultMapper/);
  assert.equal(opaDecisionLog(factory, {decision_id: "d", result: {allow: true}}, {...options, resultMapper: (value) => (value as {allow: boolean}).allow ? "allow" : "deny"}).decision, "allow");
  assert.throws(() => opaDecisionLog(factory, {decision_id: "d", result: true, metrics: []}, options), /metrics must be an object/);
  assert.throws(() => opaDecisionLog(factory, {decision_id: "d", result: true, timestamp: "2026-02-30T00:00:00Z"}, options), /not a valid timestamp/);
  assert.throws(() => opaDecisionLog(factory, {decision_id: "d", result: true, trace_id: 42}, options), /trace_id must be a non-empty string/);
});

test("Cedar sorts stable codes, retains final decision, and rejects prose errors", () => {
  const event = cedarPolicyDecision(factory, {runId: "run-1", agentId: "agent-1", decision: "Allow", cedarVersion: "4.11.2", bundleDigest: digest, actionType: "Document::read", resourceType: "Document", evaluationDurationNs: 900, determiningPolicyIds: ["permit-read", "permit-read"], errorCodes: ["entity_attribute_missing"]});
  assert.equal(event.decision, "allow"); assert.equal((event.policy as Record<string, unknown>).policy_id, "permit-read");
  assert.deepEqual(event.reason_codes, ["cedar.policy:permit-read", "cedar.error:entity_attribute_missing"]);
  assert.throws(() => cedarPolicyDecision(factory, {runId: "run-1", agentId: "agent-1", decision: "Deny", cedarVersion: "4", bundleDigest: digest, actionType: "read", resourceType: "doc", evaluationDurationNs: 1, errorCodes: ["failed to read secret /customer/42"]}), /not error messages/);
  assert.throws(() => cedarPolicyDecision(factory, {runId: "run-1", agentId: "agent-1", decision: "Deny", cedarVersion: "4", bundleDigest: digest, actionType: "read", resourceType: "doc", evaluationDurationNs: 1, determiningPolicyIds: "deny-secret"}), /not a string/);
});

function agtSource(decision = "require_approval"): Record<string, unknown> { return {event_id: "018f0f7d7a137cc28000000000000042", occurred_at: "2026-08-18T12:34:56.123456789+00:00", kind: "policy_check", agent_id: "agent-1", action: "tool.invoke", decision, reason: "secret customer text", resource: "/customer/42", policy_name: "tool-policy", latency_ms: 1.25, attributes: {resource_type: "tool", reason_codes: ["approval.required"], prompt: "must not copy"}}; }
const mapAgt = (source: unknown): NormalizedEvent[] => [agtPolicyDecision(factory, source as Record<string, unknown>, {runId: "run-1", policyEngineVersion: "1.2.3", bundleDigest: digest})];

test("AGT policy mapping excludes free-form content and sink prevalidates a whole batch", () => {
  const event = mapAgt(agtSource())[0]!; assert.equal(event.decision, "challenge"); assert.equal(event.event_id, "018f0f7d-7a13-7cc2-8000-000000000042"); assert.equal(event.time_unix_nano, "1787056496123456789"); assert.equal(event.evaluation_duration_ns, 1_250_000);
  const serialized = JSON.stringify(event); for (const secret of ["secret customer", "/customer/42", "must not copy"]) assert.equal(serialized.includes(secret), false);
  const emitted: NormalizedEvent[] = []; const sink = new AgtGovernanceEventSink({emit: (item) => { emitted.push(item); return {accepted: true, projectionErrors: []}; }}, mapAgt, {success: "success", failure: "failure"});
  assert.equal(sink.emit([agtSource(), agtSource("unknown")]), "failure"); assert.deepEqual(emitted, []);
  assert.equal(sink.emit([agtSource()]), "success"); assert.equal(emitted.length, 1);
});

test("AGT sink reports projection failure and identifiers cannot carry prose", () => {
  const sink = new AgtGovernanceEventSink({emit: () => ({accepted: true, projectionErrors: ["log failed"]})}, mapAgt, {success: 0, failure: 1});
  assert.equal(sink.emit([agtSource()]), 1);
  const source = agtSource(); source.attributes = {resource_type: "tool", reason_codes: ["customer secret denied"]};
  assert.throws(() => mapAgt(source), /unique identifiers/);
});
