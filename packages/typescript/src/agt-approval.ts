import {createHash} from "node:crypto";
import {EventFactory} from "./factory.js";
import type {NormalizedEvent} from "./types.js";

type Source = Record<string, unknown>;
type Digest = {algorithm: string; value: string};
const NAMESPACE = "ea5a1737-5417-4eaa-8bb0-4fc40e4cb837";
const DIGEST = /^sha256:([0-9a-f]{64})$/;

export function agtPolicyDecisionRecord(factory: EventFactory, source: Source, options: {runId: string; agentId: string; actionType: string; resourceType: string; policyEngineVersion: string; bundleDigest: Digest; evaluationDurationNs?: number; enforcementMode?: string; traceId?: string; spanId?: string}): NormalizedEvent {
  if (source.verdict !== "require_approval") throw new Error("AGT PolicyDecisionRecord verdict must be require_approval");
  const sourceId = required(source.policy_decision_id, "policy_decision_id");
  const duration = options.evaluationDurationNs ?? 0;
  if (!Number.isSafeInteger(duration) || duration < 0) throw new Error("evaluationDurationNs must be a non-negative safe integer");
  return factory.build("policy.decision", {runId: options.runId, agentId: options.agentId, eventId: sourceEventId("policy", sourceId), timeUnixNano: timestampNs(source.decided_at, "decided_at"), ...context(options)}, {
    decision: "challenge", policy: {engine: "agt", engine_version: required(options.policyEngineVersion, "policyEngineVersion"), policy_id: required(source.policy_rule_id, "policy_rule_id"), bundle_digest: options.bundleDigest},
    action_type: options.actionType, resource_type: options.resourceType, enforcement_mode: options.enforcementMode ?? "enforce", evaluation_duration_ns: duration, reason_codes: ["agt.verdict:require_approval"],
  });
}

export function agtApprovalRequest(factory: EventFactory, request: Source, policy: Source, options: {runId: string; traceId?: string; spanId?: string}): NormalizedEvent {
  verifyPairs(request, policy, [["policy_decision_id", "policy_decision_id"], ["action_digest", "action_digest"], ["policy_version", "policy_version"], ["approval_chain_id", "approval_chain_id"], ["approval_chain_version", "approval_chain_version"]], "request", "policy decision");
  const approvalId = required(request.approval_request_id, "approval_request_id");
  const policyId = required(request.policy_decision_id, "policy_decision_id");
  const requestedAt = timestampNs(request.requested_at, "requested_at");
  return factory.build("approval.requested", {runId: options.runId, agentId: required(request.agent_id, "agent_id"), eventId: sourceEventId("approval.requested", approvalId), timeUnixNano: requestedAt, ...context(options)}, {
    approval_id: approvalId, policy_event_id: sourceEventId("policy", policyId), chain_id: required(request.approval_chain_id, "approval_chain_id"), chain_version: required(request.approval_chain_version, "approval_chain_version"), action_digest: digest(request.action_digest, "action_digest"), actor_type: "policy", requested_at_unix_nano: requestedAt, expires_at_unix_nano: timestampNs(request.expires_at, "expires_at"), reason_codes: ["agt.approval:requested"],
  });
}

export function agtApprovalResolution(factory: EventFactory, resolution: Source, request: Source, options: {runId: string; traceId?: string; spanId?: string}): NormalizedEvent {
  verifyPairs(resolution, request, [["approval_request_id", "approval_request_id"], ["action_digest", "action_digest"], ["policy_version", "policy_version"], ["approval_chain_version", "approval_chain_version"]], "resolution", "request");
  const eventType = new Map<unknown, string>([["allow", "approval.approved"], ["deny", "approval.rejected"], ["expired", "approval.expired"]]).get(resolution.outcome);
  if (!eventType) throw new Error(`unsupported AGT approval outcome: ${String(resolution.outcome)}`);
  const resolvedAt = timestampNs(resolution.resolved_at, "resolved_at");
  const requestedAt = timestampNs(request.requested_at, "requested_at");
  if (resolvedAt < requestedAt) throw new Error("AGT approval resolution cannot predate its request");
  const approvalId = required(resolution.approval_request_id, "approval_request_id");
  const resolutionId = required(resolution.approval_resolution_id, "approval_resolution_id");
  const finalDigest = resolution.final_entry_digest;
  return factory.build(eventType, {runId: options.runId, agentId: required(request.agent_id, "agent_id"), eventId: sourceEventId("approval.resolution", resolutionId), timeUnixNano: resolvedAt, ...context(options)}, {
    approval_id: approvalId, policy_event_id: sourceEventId("policy", required(request.policy_decision_id, "policy_decision_id")), chain_id: required(request.approval_chain_id, "approval_chain_id"), chain_version: required(request.approval_chain_version, "approval_chain_version"), resolution_id: resolutionId, action_digest: digest(resolution.action_digest, "action_digest"), actor_type: "system", requested_at_unix_nano: requestedAt, expires_at_unix_nano: timestampNs(request.expires_at, "expires_at"), reason_codes: [`agt.outcome:${String(resolution.outcome)}`], ...(finalDigest === undefined || finalDigest === null ? {} : {approval_evidence_digest: digest(finalDigest, "final_entry_digest")}),
  });
}

function verifyPairs(left: Source, right: Source, pairs: Array<[string, string]>, leftName: string, rightName: string): void { for (const [leftField, rightField] of pairs) { const leftValue = required(left[leftField], leftField); const rightValue = required(right[rightField], rightField); if (leftValue !== rightValue) throw new Error(`AGT ${leftName} ${leftField} does not match ${rightName} ${rightField}`); } }
function digest(value: unknown, field: string): Digest { const match = DIGEST.exec(required(value, field)); if (!match) throw new Error(`AGT ${field} must use sha256:<lowercase-hex>`); return {algorithm: "sha256", value: match[1]!}; }
function required(value: unknown, field: string): string { if (typeof value !== "string" || !value) throw new Error(`AGT ${field} must be a non-empty string`); return value; }
function context(value: {traceId?: string; spanId?: string}): {traceId?: string; spanId?: string} { return {...(value.traceId === undefined ? {} : {traceId: required(value.traceId, "traceId")}), ...(value.spanId === undefined ? {} : {spanId: required(value.spanId, "spanId")})}; }
function timestampNs(value: unknown, field: string): bigint { if (typeof value !== "string") throw new Error(`AGT ${field} must be an RFC 3339 UTC timestamp string`); const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)$/.exec(value); if (!match) throw new Error(`AGT ${field} must be an RFC 3339 UTC timestamp string`); const milliseconds = Date.parse(`${match[1]}Z`); if (match[1]!.startsWith("0000") || !Number.isFinite(milliseconds) || new Date(milliseconds).toISOString().slice(0, 19) !== match[1]) throw new Error(`AGT ${field} is not a valid timestamp`); return BigInt(milliseconds) * 1_000_000n + BigInt((match[2] ?? "").padEnd(9, "0") || "0"); }
function sourceEventId(kind: string, id: string): string { const ns = Buffer.from(NAMESPACE.replaceAll("-", ""), "hex"); const bytes = createHash("sha1").update(ns).update(`${kind}:${id}`, "utf8").digest().subarray(0, 16); bytes[6] = (bytes[6]! & 0x0f) | 0x50; bytes[8] = (bytes[8]! & 0x3f) | 0x80; const hex = bytes.toString("hex"); return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`; }
