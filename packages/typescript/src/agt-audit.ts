import {createHash} from "node:crypto";
import {EventFactory} from "./factory.js";
import type {NormalizedEvent} from "./types.js";

type Source = Record<string, unknown>; type Digest = {algorithm: string; value: string};
const NAMESPACE = "398428fd-2730-498f-8ed8-6b4290668171";

export function agtAuditPolicyDecision(factory: EventFactory, source: Source, options: {runId: string; policyEngineVersion: string; bundleDigest: Digest; resourceType: string; evaluationDurationNs?: number; enforcementMode?: string}): NormalizedEvent {
  const sourceType = required(source.event_type, "event_type"); if (!new Set(["policy_evaluation", "policy_violation"]).has(sourceType)) throw new Error(`AGT audit event is not a policy event: ${sourceType}`);
  const duration = options.evaluationDurationNs ?? 0; safeDuration(duration, "evaluationDurationNs");
  return factory.build("policy.decision", {runId: options.runId, agentId: required(source.agent_did, "agent_did"), eventId: sourceEventId("policy", required(source.entry_id, "entry_id")), timeUnixNano: timestampNs(source.timestamp, "timestamp"), ...(source.trace_id === undefined || source.trace_id === null ? {} : {traceId: required(source.trace_id, "trace_id")})}, {
    decision: policyDecision(source.policy_decision), policy: {engine: "agt", engine_version: required(options.policyEngineVersion, "policyEngineVersion"), bundle_digest: options.bundleDigest, ...(source.matched_rule === undefined || source.matched_rule === null ? {} : {policy_id: required(source.matched_rule, "matched_rule")})}, action_type: required(source.action, "action"), resource_type: required(options.resourceType, "resourceType"), enforcement_mode: options.enforcementMode ?? "enforce", evaluation_duration_ns: duration, reason_codes: [`agt.audit:${sourceType}`],
  });
}

export function agtAuditAction(factory: EventFactory, source: Source, options: {runId: string; actionDigest: Digest; actionKind: string; operation: string; durationNs?: number}): NormalizedEvent {
  const sourceType = required(source.event_type, "event_type"); if (!new Set(["tool_invocation", "tool_blocked", "action"]).has(sourceType)) throw new Error(`AGT audit event is not an action event: ${sourceType}`);
  const duration = options.durationNs ?? auditDuration(source); safeDuration(duration, "durationNs");
  const entryId = required(source.entry_id, "entry_id");
  return factory.build("action.executed", {runId: options.runId, agentId: required(source.agent_did, "agent_did"), eventId: sourceEventId("action", entryId), timeUnixNano: timestampNs(source.timestamp, "timestamp"), ...(source.trace_id === undefined || source.trace_id === null ? {} : {traceId: required(source.trace_id, "trace_id")})}, {
    action_id: entryId, action_kind: options.actionKind, action_name: required(source.action, "action"), operation: required(options.operation, "operation"), outcome: sourceType === "tool_blocked" ? "denied" : actionOutcome(source.outcome), duration_ns: duration, action_digest: options.actionDigest, ...(source.target_did === undefined || source.target_did === null ? {} : {target: {kind: "agent", id: required(source.target_did, "target_did")}}),
  });
}

function policyDecision(value: unknown): string { const result = new Map<unknown, string>([["allow", "allow"], ["allowed", "allow"], ["deny", "deny"], ["denied", "deny"], ["require_approval", "challenge"], ["requires_approval", "challenge"], ["review", "challenge"], ["not_applicable", "not_applicable"], ["error", "error"]]).get(value); if (!result) throw new Error(`unsupported AGT audit policy decision: ${String(value)}`); return result; }
function actionOutcome(value: unknown): string { const result = new Map<unknown, string>([["success", "success"], ["failure", "error"], ["error", "error"], ["denied", "denied"], ["cancelled", "cancelled"], ["timeout", "timeout"]]).get(value); if (!result) throw new Error(`unsupported AGT audit action outcome: ${String(value)}`); return result; }
function auditDuration(source: Source): number { if (source.issued_at === undefined || source.issued_at === null || source.completed_at === undefined || source.completed_at === null) throw new Error("AGT action audit requires durationNs or both issued_at and completed_at"); const start = timestampNs(source.issued_at, "issued_at"); const end = timestampNs(source.completed_at, "completed_at"); if (end < start) throw new Error("AGT completed_at cannot predate issued_at"); const value = end - start; if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error("AGT audit duration exceeds the safe integer range"); return Number(value); }
function safeDuration(value: number, field: string): void { if (!Number.isSafeInteger(value) || value < 0) throw new Error(`${field} must be a non-negative safe integer`); }
function required(value: unknown, field: string): string { if (typeof value !== "string" || !value) throw new Error(`AGT audit ${field} must be a non-empty string`); return value; }
function timestampNs(value: unknown, field: string): bigint { if (typeof value !== "string") throw new Error(`AGT audit ${field} must be an RFC 3339 UTC timestamp`); const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)$/.exec(value); if (!match) throw new Error(`AGT audit ${field} must be an RFC 3339 UTC timestamp`); const milliseconds = Date.parse(`${match[1]}Z`); if (match[1]!.startsWith("0000") || !Number.isFinite(milliseconds) || new Date(milliseconds).toISOString().slice(0, 19) !== match[1]) throw new Error(`AGT audit ${field} is invalid`); return BigInt(milliseconds) * 1_000_000n + BigInt((match[2] ?? "").padEnd(9, "0") || "0"); }
function sourceEventId(kind: string, id: string): string { const ns = Buffer.from(NAMESPACE.replaceAll("-", ""), "hex"); const bytes = createHash("sha1").update(ns).update(`${kind}:${id}`, "utf8").digest().subarray(0, 16); bytes[6] = (bytes[6]! & 0x0f) | 0x50; bytes[8] = (bytes[8]! & 0x3f) | 0x80; const hex = bytes.toString("hex"); return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`; }
