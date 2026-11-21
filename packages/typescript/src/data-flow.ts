import {EventFactory, type EnvelopeFields} from "./factory.js";
import type {NormalizedEvent} from "./types.js";

const IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$/;
const MEDIA_TYPE = /^[A-Za-z0-9!#$&^_.+-]+\/[A-Za-z0-9!#$&^_.+-]+$/;
type Digest = {algorithm: string; value: string};

export class ClassificationResult {
  constructor(readonly taxonomy: string, readonly value: string, readonly producer: string) {
    identifier(taxonomy, "classification taxonomy");
    identifier(value, "classification value");
    identifier(producer, "classification producer");
    Object.freeze(this);
  }
}
export class DataEndpoint {
  constructor(readonly kind: string, readonly id?: string) {
    identifier(kind, "endpoint kind");
    if (id !== undefined) identifier(id, "endpoint id");
    Object.freeze(this);
  }
  asEventValue(): {kind: string; id?: string} { return {kind: this.kind, ...(this.id === undefined ? {} : {id: this.id})}; }
}

export class SourceClassification {
  constructor(readonly source: DataEndpoint, readonly classification: ClassificationResult) {
    if (!(source instanceof DataEndpoint)) throw new TypeError("source must be a DataEndpoint");
    if (!(classification instanceof ClassificationResult)) throw new TypeError("classification must be a ClassificationResult");
    Object.freeze(this);
  }
}

export class ClassificationOrder {
  readonly levels: readonly string[];

  constructor(readonly taxonomy: string, levels: readonly string[]) {
    identifier(taxonomy, "classification taxonomy");
    if (!Array.isArray(levels) || levels.length === 0) throw new Error("classification levels must be a non-empty array");
    for (const level of levels) identifier(level, "classification level");
    if (new Set(levels).size !== levels.length) throw new Error("classification levels must be unique");
    this.levels = Object.freeze([...levels]);
    Object.freeze(this);
  }

  rank(result: ClassificationResult): number {
    if (!(result instanceof ClassificationResult)) throw new TypeError("classification must be a ClassificationResult");
    if (result.taxonomy !== this.taxonomy) throw new Error(`taxonomy mismatch: expected ${this.taxonomy}, got ${result.taxonomy}`);
    const rank = this.levels.indexOf(result.value);
    if (rank < 0) throw new Error(`unknown classification value for ${this.taxonomy}: ${result.value}`);
    return rank;
  }
}

function validateSourceClassifications(
  sources: readonly SourceClassification[] | undefined,
  order: ClassificationOrder | undefined,
): readonly SourceClassification[] | undefined {
  if (sources === undefined && order === undefined) return undefined;
  if (sources === undefined || order === undefined) throw new Error("sourceClassifications and classificationOrder must be supplied together");
  if (!(order instanceof ClassificationOrder)) throw new TypeError("classificationOrder must be a ClassificationOrder");
  if (!Array.isArray(sources) || sources.length === 0) throw new Error("derived data must identify at least one source");
  if (sources.length > 1024) throw new Error("derived data may identify at most 1024 sources");

  const seen = new Set<string>();
  for (const record of sources) {
    if (!(record instanceof SourceClassification)) throw new TypeError("each source must be a SourceClassification");
    const key = `${record.source.kind}\\u0000${record.source.id ?? ""}`;
    if (seen.has(key)) throw new Error("duplicate source reference");
    seen.add(key);
    order.rank(record.classification);
  }
  return [...sources];
}

function derivedClassificationFields(
  observed: ClassificationResult,
  sources: readonly SourceClassification[] | undefined,
  order: ClassificationOrder | undefined,
): Record<string, unknown> {
  if (sources === undefined && order === undefined) return {};
  if (sources === undefined || order === undefined) throw new Error("sourceClassifications and classificationOrder must be supplied together");
  order.rank(observed);

  const sourceValues = sources.map((record) => ({
    source: record.source.asEventValue(),
    classification: {taxonomy: record.classification.taxonomy, value: record.classification.value, producer: record.classification.producer},
  }));
  let effective = observed;
  let effectiveRank = order.rank(observed);
  for (const record of sources) {
    const rank = order.rank(record.classification);
    if (rank > effectiveRank) { effective = record.classification; effectiveRank = rank; }
  }

  // The output label wins ties with source labels; the first source at a
  // strictly higher rank wins ties with later sources in input array order.
  return {
    classification: {taxonomy: effective.taxonomy, value: effective.value, producer: effective.producer},
    observed_classification: {taxonomy: observed.taxonomy, value: observed.value, producer: observed.producer},
    source_classifications: sourceValues,
  };
}

export interface DataClassifier {classify(value: unknown): ClassificationResult}

export function classifiedDataFlow(factory: EventFactory, classifier: DataClassifier, value: unknown, options: {runId: string; agentId: string; direction: string; source: DataEndpoint; destination: DataEndpoint; purpose: string; policyDecision?: string; contentDigest?: Digest; sizeBytes?: number; tokenCount?: number; mediaType?: string; transformation?: string; sourceClassifications?: readonly SourceClassification[]; classificationOrder?: ClassificationOrder; envelope?: Omit<EnvelopeFields, "runId" | "agentId">}): NormalizedEvent {
  identifier(options.purpose, "purpose");
  if (!(options.source instanceof DataEndpoint) || !(options.destination instanceof DataEndpoint)) throw new TypeError("source and destination must be DataEndpoint instances");
  if (options.mediaType !== undefined && (!MEDIA_TYPE.test(options.mediaType) || options.mediaType.length > 255)) throw new Error("mediaType must be a parameter-free type/subtype identifier");
  for (const [field, amount] of [["sizeBytes", options.sizeBytes], ["tokenCount", options.tokenCount]] as const) if (amount !== undefined && (!Number.isSafeInteger(amount) || amount < 0 || amount > Number.MAX_SAFE_INTEGER)) throw new Error(`${field} must be a non-negative safe integer`);
  const records = validateSourceClassifications(options.sourceClassifications, options.classificationOrder);

  // Validate cheap arguments and source lineage before the potentially costly
  // adopter-owned classifier is invoked.
  const result = classifier.classify(value);
  if (!(result instanceof ClassificationResult)) throw new TypeError("classifier must return ClassificationResult");
  const derived = derivedClassificationFields(result, records, options.classificationOrder);
  return factory.build("data_flow.observed", {runId: options.runId, agentId: options.agentId, ...options.envelope}, {
    direction: options.direction, source: options.source.asEventValue(), destination: options.destination.asEventValue(), classification: (derived.classification as Record<string, string> | undefined) ?? {taxonomy: result.taxonomy, value: result.value, producer: result.producer}, ...omitClassification(derived), purpose: options.purpose, policy_decision: options.policyDecision ?? "not_evaluated",
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
  const rec = object(decision, "AGT decision");
  if (typeof rec.allowed !== "boolean") throw new Error("AGT data access allowed must be a boolean");
  const label = object(rec.data_label, "AGT data_label");
  const classification = agtDataClassification(label);
  return classifiedDataFlow(factory, {classify: () => classification}, undefined, {...options, agentId: required(rec.agent_id, "AGT data access agent_id"), policyDecision: rec.allowed ? "allow" : "deny", envelope: {timeUnixNano: timestampNs(rec.evaluated_at, "evaluated_at"), ...options.envelope}});
}

function omitClassification(fields: Record<string, unknown>): Record<string, unknown> { const {classification: _classification, ...rest} = fields; return rest; }

function identifier(value: unknown, field: string): string { if (typeof value !== "string" || !IDENTIFIER.test(value) || value.includes("://")) throw new Error(`${field} must be a 1-256 character metadata identifier without whitespace, URLs, query strings, fragments, or key/value delimiters`); return value; }
function required(value: unknown, field: string): string { if (typeof value !== "string" || !value) throw new Error(`${field} must be a non-empty string`); return value; }
function object(value: unknown, field: string): Record<string, unknown> { if (typeof value !== "object" || value === null || Array.isArray(value)) throw new Error(`${field} must be an object`); return value as Record<string, unknown>; }
function present(key: string, value: unknown): Record<string, unknown> { return value === undefined ? {} : {[key]: value}; }
function timestampNs(value: unknown, field: string): bigint { if (typeof value !== "string") throw new Error(`AGT data access ${field} must be an RFC 3339 UTC timestamp`); const match = /^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(\d{1,9}))?(?:Z|\+00:00)$/.exec(value); if (!match) throw new Error(`AGT data access ${field} must be an RFC 3339 UTC timestamp`); const milliseconds = Date.parse(`${match[1]}Z`); if (match[1]!.startsWith("0000") || !Number.isFinite(milliseconds) || milliseconds < 0 || new Date(milliseconds).toISOString().slice(0, 19) !== match[1]) throw new Error(`AGT data access ${field} is invalid`); return BigInt(milliseconds) * 1_000_000n + BigInt((match[2] ?? "").padEnd(9, "0") || "0"); }
