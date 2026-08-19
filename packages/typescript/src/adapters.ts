import {createHash} from "node:crypto";
import {EventFactory, type EnvelopeFields} from "./factory.js";
import type {NormalizedEvent} from "./types.js";

type Digest = {algorithm: string; value: string};
type Decision = "allow" | "deny" | "challenge" | "not_applicable" | "error";
const IDENTIFIER = /^[A-Za-z0-9_.:-]{1,128}$/;
const OPA_NAMESPACE = "881f86d8-7573-4d35-98cb-c00b934cc04f";

export function opaDecisionLog(factory: EventFactory, source: Record<string, unknown>, options: {runId: string; agentId: string; actionType: string; resourceType: string; bundleDigest: Digest; opaVersion?: string; enforcementMode?: string; resultMapper?: (value: unknown) => Decision}): NormalizedEvent {
  const sourceId = requiredString(source.decision_id, "OPA decision_id");
  const decision = (options.resultMapper ?? booleanDecision)(source.result);
  if (!["allow", "deny", "challenge", "not_applicable", "error"].includes(decision)) throw new Error(`OPA result mapper returned unsupported decision: ${decision}`);
  const labels = record(source.labels ?? {}, "OPA labels");
  const version = requiredString(options.opaVersion ?? labels.version, "OPA version");
  const metrics = record(source.metrics ?? {}, "OPA metrics");
  const duration = metrics.timer_rego_query_eval_ns ?? 0;
  if (!Number.isSafeInteger(duration) || (duration as number) < 0) throw new Error("OPA timer_rego_query_eval_ns must be a non-negative safe integer");
  const ids = source.ids ?? [];
  if (!Array.isArray(ids) || ids.some((value) => typeof value !== "string" || !value)) throw new Error("OPA ids must be an array of non-empty strings");
  if (ids.length > 32) throw new Error("OPA ids exceed the 32-code contract limit");
  const path = source.path;
  return factory.build("policy.decision", {runId: options.runId, agentId: options.agentId, eventId: uuidV5(OPA_NAMESPACE, sourceId), ...(source.timestamp === undefined ? {} : {timeUnixNano: utcTimestampNs(source.timestamp, "OPA timestamp", true)}), ...optionalEnvelope(source)}, {
    decision, policy: {engine: "opa", engine_version: version, bundle_digest: options.bundleDigest, ...(typeof path === "string" && path ? {policy_id: path.replace(/^\/+/, "")} : {})},
    action_type: options.actionType, resource_type: options.resourceType, enforcement_mode: options.enforcementMode ?? "enforce", evaluation_duration_ns: duration,
    reason_codes: ids.map((value) => `opa.rule:${value}`),
  });
}

export function cedarPolicyDecision(factory: EventFactory, options: {runId: string; agentId: string; decision: string; cedarVersion: string; bundleDigest: Digest; actionType: string; resourceType: string; evaluationDurationNs: number; determiningPolicyIds?: Iterable<string>; errorCodes?: Iterable<string>; enforcementMode?: string; inputDigest?: Digest; envelope?: Omit<EnvelopeFields, "runId" | "agentId">}): NormalizedEvent {
  const decision = options.decision.toLowerCase();
  if (decision !== "allow" && decision !== "deny") throw new Error("Cedar decision must be Allow or Deny");
  const policies = identifiers(options.determiningPolicyIds ?? [], "determiningPolicyIds");
  const errors = identifiers(options.errorCodes ?? [], "errorCodes");
  if (errors.some((value) => !IDENTIFIER.test(value))) throw new Error("Cedar errorCodes must be identifiers, not error messages");
  const reasons = [...policies.map((value) => `cedar.policy:${value}`), ...errors.map((value) => `cedar.error:${value}`)];
  if (reasons.length > 32) throw new Error("Cedar reasons and errors exceed the 32-code contract limit");
  if (!Number.isSafeInteger(options.evaluationDurationNs) || options.evaluationDurationNs < 0) throw new Error("Cedar evaluationDurationNs must be a non-negative safe integer");
  return factory.build("policy.decision", {runId: options.runId, agentId: options.agentId, ...options.envelope}, {
    decision, policy: {engine: "cedar", engine_version: options.cedarVersion, bundle_digest: options.bundleDigest, ...(policies.length === 1 ? {policy_id: policies[0]} : {}), ...(options.inputDigest ? {input_digest: options.inputDigest} : {})},
    action_type: options.actionType, resource_type: options.resourceType, enforcement_mode: options.enforcementMode ?? "enforce", evaluation_duration_ns: options.evaluationDurationNs, reason_codes: reasons,
  });
}

export function agtPolicyDecision(factory: EventFactory, source: Record<string, unknown>, options: {runId: string; policyEngineVersion: string; bundleDigest: Digest; resourceType?: string; enforcementMode?: string}): NormalizedEvent {
  const kind = source.kind;
  if (kind !== "policy_check" && kind !== "policy_violation") throw new Error(`AGT event kind is not a policy decision: ${String(kind)}`);
  const attributes = record(source.attributes ?? {}, "AGT attributes");
  const reasonCodes = attributes.reason_codes ?? [];
  if (!Array.isArray(reasonCodes) || reasonCodes.length > 32 || reasonCodes.some((value) => typeof value !== "string" || !IDENTIFIER.test(value)) || new Set(reasonCodes).size !== reasonCodes.length) throw new Error("AGT reason_codes must contain at most 32 unique identifiers");
  const latency = source.latency_ms ?? 0;
  if (typeof latency !== "number" || !Number.isFinite(latency) || latency < 0) throw new Error("AGT latency_ms must be a finite non-negative number");
  const duration = Math.round(latency * 1_000_000);
  if (!Number.isSafeInteger(duration)) throw new Error("AGT latency_ms exceeds the safe nanosecond range");
  const policyName = source.policy_name;
  return factory.build("policy.decision", {runId: options.runId, agentId: requiredString(source.agent_id, "AGT agent_id"), eventId: normalizeUuid(requiredString(source.event_id, "AGT event_id")), timeUnixNano: utcTimestampNs(source.occurred_at, "AGT occurred_at", false), ...optionalEnvelope(source)}, {
    decision: agtDecision(source.decision), policy: {engine: "agt", engine_version: requiredString(options.policyEngineVersion, "AGT policyEngineVersion"), bundle_digest: options.bundleDigest, ...(policyName === undefined ? {} : {policy_id: requiredString(policyName, "AGT policy_name")})},
    action_type: requiredString(source.action, "AGT action"), resource_type: requiredString(options.resourceType ?? attributes.resource_type, "AGT resource_type"), enforcement_mode: options.enforcementMode ?? "enforce", evaluation_duration_ns: duration, reason_codes: reasonCodes,
  });
}

export class AgtGovernanceEventSink<Success, Failure> {
  constructor(readonly client: {emit(event: NormalizedEvent): {accepted: boolean; projectionErrors?: readonly unknown[]}}, readonly mapper: (source: unknown) => Iterable<NormalizedEvent>, readonly results: {success: Success; failure: Failure}) {}
  emit(sources: readonly unknown[]): Success | Failure { try { const events = sources.flatMap((source) => [...this.mapper(source)]); for (const event of events) { const result = this.client.emit(event); if (!result.accepted || (result.projectionErrors?.length ?? 0) > 0) return this.results.failure; } return this.results.success; } catch { return this.results.failure; } }
  shutdown(_timeoutMs = 5_000): true { return true; }
  forceFlush(_timeoutMs = 30_000): true { return true; }
}

function booleanDecision(value: unknown): Decision { if (value === true) return "allow"; if (value === false) return "deny"; if (value === null || value === undefined) return "not_applicable"; throw new Error("OPA non-boolean result requires an explicit resultMapper"); }
function agtDecision(value: unknown): Decision { const mapped = new Map<unknown, Decision>([["allow", "allow"], ["allowed", "allow"], ["deny", "deny"], ["denied", "deny"], ["block", "deny"], ["blocked", "deny"], ["require_approval", "challenge"], ["requires_approval", "challenge"], ["review", "challenge"]]).get(value); if (!mapped) throw new Error(`unsupported AGT policy decision: ${String(value)}`); return mapped; }
function record(value: unknown, name: string): Record<string, unknown> { if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${name} must be an object`); return value as Record<string, unknown>; }
function requiredString(value: unknown, name: string): string { if (typeof value !== "string" || !value) throw new Error(`${name} must be a non-empty string`); return value; }
function identifiers(values: Iterable<string>, name: string): string[] { if (typeof values === "string") throw new Error(`Cedar ${name} must be an iterable of strings, not a string`); const result = [...new Set(values)].sort(); if (result.some((value) => typeof value !== "string" || !value)) throw new Error(`Cedar ${name} must contain non-empty strings`); return result; }
function optionalEnvelope(source: Record<string, unknown>): Partial<EnvelopeFields> { return {...(source.trace_id === undefined ? {} : {traceId: requiredString(source.trace_id, "trace_id")}), ...(source.span_id === undefined ? {} : {spanId: requiredString(source.span_id, "span_id")})}; }
function utcTimestampNs(value: unknown, name: string, requireZ: boolean): bigint { if (typeof value !== "string") throw new Error(`${name} must be an RFC 3339 UTC string`); const suffix = requireZ ? "Z" : "(?:Z|\\+00:00)"; const match = new RegExp(`^(\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2})(?:\\.(\\d{1,9}))?${suffix}$`).exec(value); if (!match) throw new Error(`${name} must use RFC 3339 UTC form`); const milliseconds = Date.parse(`${match[1]}Z`); if (match[1]!.startsWith("0000") || !Number.isFinite(milliseconds) || new Date(milliseconds).toISOString().slice(0, 19) !== match[1]) throw new Error(`${name} is not a valid timestamp`); return BigInt(milliseconds) * 1_000_000n + BigInt((match[2] ?? "").padEnd(9, "0") || "0"); }
function normalizeUuid(value: string): string { const hex = value.replaceAll("-", "").toLowerCase(); if (!/^[0-9a-f]{32}$/.test(hex)) throw new Error("AGT event_id must be a UUID"); return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`; }
function uuidV5(namespace: string, name: string): string { const ns = Buffer.from(namespace.replaceAll("-", ""), "hex"); const bytes = createHash("sha1").update(ns).update(name, "utf8").digest().subarray(0, 16); bytes[6] = (bytes[6]! & 0x0f) | 0x50; bytes[8] = (bytes[8]! & 0x3f) | 0x80; const hex = bytes.toString("hex"); return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`; }
