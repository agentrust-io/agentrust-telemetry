import assert from "node:assert/strict";
import test from "node:test";
import {agtAuditAction, agtAuditPolicyDecision, EventFactory, SchemaValidator} from "../src/index.js";

const digest = {algorithm: "sha256", value: "a".repeat(64)}; const bundle = {algorithm: "sha256", value: "b".repeat(64)};
const factory = new EventFactory(SchemaValidator.bundled(), {name: "audit-tests", version: "1"}, () => 1n, () => "018f0f7d-7a13-7cc2-8000-000000000042");
function source(overrides: Record<string, unknown> = {}): Record<string, unknown> { return {entry_id: "audit_123", timestamp: "2026-08-18T12:00:00Z", issued_at: "2026-08-18T11:59:59.995Z", completed_at: "2026-08-18T12:00:00Z", event_type: "policy_evaluation", agent_did: "did:agt:agent-1", action: "tool.invoke", arguments_hash: "c".repeat(64), resource: "/customer/42", target_did: null, data: {prompt: "must not cross"}, outcome: "success", policy_decision: "require_approval", matched_rule: "high-risk-tools", entry_hash: "d".repeat(64), trace_id: "4bf92f3577b34da6a3ce929d0e0e4736", ...overrides}; }
test("audit policy mapping matches Python ID and excludes free-form and partial hashes", () => {
  const event = agtAuditPolicyDecision(factory, source(), {runId: "run-1", policyEngineVersion: "5.0.0", bundleDigest: bundle, resourceType: "tool"});
  assert.equal(event.event_id, "3b61ffca-b678-5f7d-8753-cbeda8825378"); assert.equal(event.decision, "challenge"); assert.equal((event.policy as Record<string, unknown>).policy_id, "high-risk-tools");
  const serialized = JSON.stringify(event); for (const value of ["/customer/42", "must not cross", "arguments_hash", "entry_hash"]) assert.equal(serialized.includes(value), false);
});
test("audit action requires caller full digest and computes safe duration", () => {
  const event = agtAuditAction(factory, source({event_type: "tool_invocation", policy_decision: null}), {runId: "run-1", actionDigest: digest, actionKind: "tool", operation: "invoke"});
  assert.equal(event.event_id, "be18d792-9eba-5142-9607-46e0039a3a2a"); assert.equal(event.duration_ns, 5_000_000); assert.deepEqual(event.action_digest, digest); assert.notEqual((event.action_digest as Record<string, unknown>).value, "c".repeat(64));
  assert.equal(agtAuditAction(factory, source({event_type: "tool_blocked"}), {runId: "run-1", actionDigest: digest, actionKind: "tool", operation: "invoke"}).outcome, "denied");
});
test("audit action rejects absent, reversed, and unsafe timing", () => {
  assert.throws(() => agtAuditAction(factory, source({event_type: "tool_invocation", issued_at: null}), {runId: "run-1", actionDigest: digest, actionKind: "tool", operation: "invoke"}), /requires durationNs/);
  assert.throws(() => agtAuditAction(factory, source({event_type: "tool_invocation", issued_at: "2026-08-18T12:00:01Z"}), {runId: "run-1", actionDigest: digest, actionKind: "tool", operation: "invoke"}), /cannot predate/);
  assert.throws(() => agtAuditAction(factory, source({event_type: "tool_invocation"}), {runId: "run-1", actionDigest: digest, actionKind: "tool", operation: "invoke", durationNs: Number.MAX_SAFE_INTEGER + 1}), /safe integer/);
});
