import {EventFactory, type EnvelopeFields} from "./factory.js";
import type {NormalizedEvent} from "./types.js";

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$/;
const MEDIA_TYPE = /^[A-Za-z0-9!#$&^_.+-]+\/[A-Za-z0-9!#$&^_.+-]+$/;
type Digest = {algorithm: string; value: string};

export class ClassificationResult {
  constructor(readonly taxonomy: string, readonly value: string, readonly producer: string) { identifier(taxonomy, "classification taxonomy"); identifier(value, "classification value"); identifier(producer, "classification producer"); }
}
export class DataEndpoint {
  constructor(readonly kind: string, readonly id?: string) { identifier(kind, "endpoint kind"); if (id !== undefined) identifier(id, "endpoint id"); }
  asEventValue(): {kind: string; id?: string} { return {kind: this.kind, ...(this.id === undefined ? {} : {id: this.id})}; }
}
export interface DataClassifier {classify(value: unknown): ClassificationResult}

export function classifiedDataFlow(factory: EventFactory, classifier: DataClassifier, value: unknown, options: {runId: string; agentId: string; direction: string; source: DataEndpoint; destination: DataEndpoint; purpose: string; policyDecision?: string; contentDigest?: Digest; sizeBytes?: number; tokenCount?: number; mediaType?: string; transformation?: string; envelope?: Omit<EnvelopeFields, "runId" | "agentId">}): NormalizedEvent {
  const result = classifier.classify(value);
  if (!(result instanceof ClassificationResult)) throw new TypeError("classifier must return ClassificationResult");
  identifier(options.purpose, "purpose");
  if (options.mediaType !== undefined && (!MEDIA_TYPE.test(options.mediaType) || options.mediaType.length > 255)) throw new Error("mediaType must be a parameter-free type/subtype identifier");
  for (const [field, amount] of [["sizeBytes", options.sizeBytes], ["tokenCount", options.tokenCount]] as const) if (amount !== undefined && (!Number.isSafeInteger(amount) || amount < 0)) throw new Error(`${field} must be a non-negative safe integer`);
  return factory.build("data_flow.observed", {runId: options.runId, agentId: options.agentId, ...options.envelope}, {
    direction: options.direction, source: options.source.asEventValue(), destination: options.destination.asEventValue(), classification: {taxonomy: result.taxonomy, value: result.value, producer: result.producer}, purpose: options.purpose, policy_decision: options.policyDecision ?? "not_evaluated",
    ...present("content_digest", options.contentDigest), ...present("size_bytes", options.sizeBytes), ...present("token_count", options.tokenCount), ...present("media_type", options.mediaType), ...present("transformation", options.transformation),
  });
}

export function agtDataClassification(source: Record<string, unknown>): ClassificationResult {
  const levels = ["public", "internal", "confidential", "restricted", "top_secret"];
  const raw = source.classification;
  if (!Number.isInteger(raw) || typeof raw !== "number" || raw < 0 || raw >= levels.length) throw new Error(`unsupported AGT data classification: ${String(raw)}`);
  return new ClassificationResult("agt.data_classification.v1", levels[raw]!, "agt.data_label");
}

export function agtDataAccessFlow(factory: EventFactory, decision: Record<string, unknown>, options: {runId: string; direction: string; source: DataEndpoint; destination: DataEndpoint; purpose: string; contentDigest?: Digest; sizeBytes?: number; tokenCount?: number; mediaType?: string; transformation?: string; envelope?: Omit<EnvelopeFields, "runId" | "agentId" | "timeUnixNano">}): NormalizedEvent {
  if (typeof decision.allowed !== "boolean") throw new Error("AGT data access allowed must be a boolean");
  const label = object(decision.data_label, "AGT data_label");
  const classification = agtDataClassification(label);
  return classifiedDataFlow(factory, {classify: () => classification}, undefined, {...options, agentId: required(decision.agent_id, "AGT data access agent_id"), policyDecision: decision.allowed ? "allow" : "deny", envelope: {timeUnixNano: timestampNs(decision.evaluated_at, "evaluated_at"), ...options.envelope}});
}

function identifier(value: unknown, field: string): string { if (typeof value !== "string" || !IDENTIFIER.test(value) || value.includes("://")) throw new Error(`${field} must be a 1-256 character metadata identifier without whitespace, URLs, query strings, fragments, or key/value delimiters`); return value; }
function required(value: unknown, field: string): string { if (typeof value !== "string" || !value) throw new Error(`${field} must be a non-empty string`); return value; }
function object(value: unknown, field: string): Record<string, unknown> { if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${field} must be an object`); return value as Record<string, unknown>; }
function present(key: string, value: unknown): Record<string, unknown> { return value === undefined ? {} : {[key]: value}; }
function timestampNs(value: unknown, field: string): bigint { if (typeof value !== "string") throw new Error(`AGT data access ${field} must be an RFC 3339 UTC timestamp`); const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)$/.exec(value); if (!match) throw new Error(`AGT data access ${field} must be an RFC 3339 UTC timestamp`); const milliseconds = Date.parse(`${match[1]}Z`); if (match[1]!.startsWith("0000") || !Number.isFinite(milliseconds) || new Date(milliseconds).toISOString().slice(0, 19) !== match[1]) throw new Error(`AGT data access ${field} is invalid`); return BigInt(milliseconds) * 1_000_000n + BigInt((match[2] ?? "").padEnd(9, "0") || "0"); }
