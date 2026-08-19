import assert from "node:assert/strict";
import test from "node:test";
import {agtApprovalRequest, agtApprovalResolution, agtPolicyDecisionRecord, EventFactory, SchemaValidator} from "../src/index.js";

const actionDigest = `sha256:${"a".repeat(64)}`; const bundle = {algorithm: "sha256", value: "b".repeat(64)};
const factory = new EventFactory(SchemaValidator.bundled(), {name: "approval-tests", version: "1"}, () => 1n, () => "018f0f7d-7a13-7cc2-8000-000000000042");
const policy = {action_digest: actionDigest, policy_rule_id: "high-risk-tools", policy_version: "7", approval_chain_id: "operators", approval_chain_version: "3", verdict: "require_approval", policy_decision_id: "pd_1", decided_at: "2026-08-18T12:00:00Z"};
const request = {policy_decision_id: "pd_1", action_digest: actionDigest, agent_id: "agent-1", operation: "deploy", policy_version: "7", approval_chain_id: "operators", approval_chain_version: "3", expires_at: "2026-08-18T12:10:00Z", approval_request_id: "ar_1", requested_at: "2026-08-18T12:00:01Z"};
const resolution = {approval_request_id: "ar_1", outcome: "allow", action_digest: actionDigest, policy_version: "7", approval_chain_version: "3", approval_resolution_id: "apr_1", resolved_at: "2026-08-18T12:02:00Z", final_entry_digest: `sha256:${"c".repeat(64)}`};

test("approval chain preserves Python-compatible policy, request, and resolution links", () => {
  const p = agtPolicyDecisionRecord(factory, policy, {runId: "run-1", agentId: "agent-1", actionType: "deploy", resourceType: "environment", policyEngineVersion: "1.0.0", bundleDigest: bundle});
  const q = agtApprovalRequest(factory, request, policy, {runId: "run-1"});
  const r = agtApprovalResolution(factory, resolution, request, {runId: "run-1"});
  assert.equal(p.event_id, "5e8f8100-3a82-54ab-89cb-fd43a08202b2"); assert.equal(q.event_id, "7781e4c1-4010-52d3-8aec-e0e89925b91e"); assert.equal(r.event_id, "900a5dda-3723-5cba-a3b2-c7281d05676c");
  assert.equal(q.policy_event_id, p.event_id); assert.equal(r.policy_event_id, p.event_id); assert.equal(r.approval_id, q.approval_id); assert.equal(r.event_type, "approval.approved");
  assert.equal((r.approval_evidence_digest as Record<string, unknown>).value, "c".repeat(64));
});

test("request mapping rejects every policy binding mismatch", () => {
  for (const [field, value] of [["policy_decision_id", "other"], ["action_digest", `sha256:${"d".repeat(64)}`], ["policy_version", "8"], ["approval_chain_id", "other"], ["approval_chain_version", "4"]]) assert.throws(() => agtApprovalRequest(factory, {...request, [field]: value}, policy, {runId: "run-1"}), new RegExp(`${field} does not match`));
  assert.throws(() => agtApprovalRequest(factory, {...request, policy_version: undefined}, {...policy, policy_version: undefined}, {runId: "run-1"}), /policy_version must be a non-empty/);
});

test("resolution mapping rejects request mismatch, chronology reversal, and malformed evidence", () => {
  for (const [field, value] of [["approval_request_id", "other"], ["action_digest", `sha256:${"d".repeat(64)}`], ["policy_version", "8"], ["approval_chain_version", "4"]]) assert.throws(() => agtApprovalResolution(factory, {...resolution, [field]: value}, request, {runId: "run-1"}), new RegExp(`${field} does not match`));
  assert.throws(() => agtApprovalResolution(factory, {...resolution, resolved_at: "2026-08-18T11:59:59Z"}, request, {runId: "run-1"}), /cannot predate/);
  assert.throws(() => agtApprovalResolution(factory, {...resolution, final_entry_digest: "not-a-digest"}, request, {runId: "run-1"}), /sha256/);
});

test("only terminal outcomes map to terminal approval events", () => {
  for (const [outcome, expected] of [["allow", "approval.approved"], ["deny", "approval.rejected"], ["expired", "approval.expired"]]) assert.equal(agtApprovalResolution(factory, {...resolution, outcome}, request, {runId: "run-1"}).event_type, expected);
  assert.throws(() => agtApprovalResolution(factory, {...resolution, outcome: "vote"}, request, {runId: "run-1"}), /unsupported/);
});
