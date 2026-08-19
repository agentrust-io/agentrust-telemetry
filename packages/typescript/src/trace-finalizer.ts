import {createHash} from "node:crypto";
import canonicalize from "canonicalize";
import type {EvidenceSnapshot} from "./evidence.js";
import type {NormalizedEvent} from "./types.js";

export type TraceOriginKind = "self" | "third-party-control-plane" | "log-import";
export interface TraceConfiguration {subject: string; modelProvider: string; modelId: string; buildDigest: string; originKind: TraceOriginKind; originProducer: string; appraisalVerifier: string; classificationTaxonomy: string; classificationOrder: readonly string[]; modelVersion?: string; buildSlsaLevel?: number; buildBuilder?: string; buildProvenanceUri?: string; transparency?: string}
export interface TraceCodec<Signed extends Record<string, unknown> = Record<string, unknown>> {
  readonly profileV02: string;
  signRecord(record: Record<string, unknown>, signingKey: unknown): Signed;
  validateRecord(record: Signed): void;
  publicKey(signingKey: unknown): unknown;
  verifyRecord(record: Signed, verificationKey: unknown, options: {maxAgeSeconds: number | null}): void;
}
export class TraceFinalizationError extends Error {}

export function finalizeTrace<Signed extends Record<string, unknown>>(snapshot: EvidenceSnapshot, config: TraceConfiguration, options: {signingKey: unknown; codec: TraceCodec<Signed>}): Signed {
  requireFinalizable(snapshot, config, options);
  const events = snapshot.entries.map((entry) => entry.event);
  const issuedAt = latestSeconds(events);
  const [bundleHash, enforcementMode] = policyBinding(events);
  const transcript = toolTranscript(snapshot);
  const record: Record<string, unknown> = {
    eat_profile: options.codec.profileV02, iat: issuedAt, subject: config.subject,
    model: {provider: config.modelProvider, model_id: config.modelId, ...(config.modelVersion ? {version: config.modelVersion} : {})},
    runtime: {platform: "software-only", measurement: `sha256:${snapshot.chainDigest}`},
    policy: {bundle_hash: bundleHash, enforcement_mode: enforcementMode}, data_class: highestDataClass(events, config), ...(transcript ? {tool_transcript: transcript} : {}),
    origin: {kind: config.originKind, producer: config.originProducer},
    build_provenance: {slsa_level: config.buildSlsaLevel ?? 0, digest: config.buildDigest, ...(config.buildBuilder ? {builder: config.buildBuilder} : {}), ...(config.buildProvenanceUri ? {provenance_uri: config.buildProvenanceUri} : {})},
    appraisal: {status: appraisal(events), verifier: config.appraisalVerifier, timestamp: issuedAt}, ...(config.transparency ? {transparency: config.transparency} : {}),
  };
  try { const signed = options.codec.signRecord(record, options.signingKey); options.codec.validateRecord(signed); const verificationKey = options.codec.publicKey(options.signingKey); options.codec.verifyRecord(signed, verificationKey, {maxAgeSeconds: null}); return signed; }
  catch (error) { throw new TraceFinalizationError(`official TRACE signing or validation failed: ${error instanceof Error ? `${error.name}: ${error.message}` : String(error)}`, {cause: error}); }
}

function requireFinalizable(snapshot: EvidenceSnapshot, config: TraceConfiguration, options: {signingKey: unknown; codec: TraceCodec}): void {
  if (!snapshot.sealed) throw new TraceFinalizationError("evidence snapshot must be sealed");
  if (snapshot.completeness !== "complete") throw new TraceFinalizationError("TRACE finalization requires completeness='complete'");
  if (!snapshot.entries.length || !snapshot.chainDigest) throw new TraceFinalizationError("TRACE finalization requires non-empty chained evidence");
  if (options.signingKey === undefined || options.signingKey === null) throw new TraceFinalizationError("a caller-supplied signing key is required");
  if (!options.codec || !options.codec.profileV02 || ![options.codec.signRecord, options.codec.validateRecord, options.codec.publicKey, options.codec.verifyRecord].every((value) => typeof value === "function")) throw new TraceFinalizationError("a caller-supplied official TRACE codec is required");
  const required = {subject: config.subject, modelProvider: config.modelProvider, modelId: config.modelId, buildDigest: config.buildDigest, originProducer: config.originProducer, appraisalVerifier: config.appraisalVerifier};
  const missing = Object.entries(required).filter(([, value]) => !value).map(([name]) => name).sort(); if (missing.length) throw new TraceFinalizationError(`trusted TRACE configuration is missing: ${missing.join(", ")}`);
  if (new Set(config.classificationOrder).size !== config.classificationOrder.length) throw new TraceFinalizationError("classificationOrder contains duplicates");
}
function policyBinding(events: readonly NormalizedEvent[]): [string, string] { const decisions = events.filter((event) => event.event_type === "policy.decision"); if (!decisions.length) throw new TraceFinalizationError("no policy decision evidence is present"); const bindings = decisions.map((event) => (event.policy as Record<string, unknown>).bundle_digest as Record<string, unknown> | undefined); if (bindings.some((value) => !value)) throw new TraceFinalizationError("every policy decision must carry bundle_digest"); const algorithms = new Set(bindings.map((value) => String(value!.algorithm))); const unsupported = [...algorithms].filter((value) => !new Set(["sha256", "sha384"]).has(value)).sort(); if (unsupported.length) throw new TraceFinalizationError(`TRACE does not support observed policy digest algorithms: ${unsupported.join(", ")}`); const bundles = new Set(bindings.map((value) => `${String(value!.algorithm)}:${String(value!.value)}`)); if (bundles.size !== 1) throw new TraceFinalizationError("conflicting policy bundle digests are present"); const modes = new Set(decisions.map((event) => String(event.enforcement_mode))); if (modes.size !== 1) throw new TraceFinalizationError("conflicting policy enforcement modes are present"); return [[...bundles][0]!, new Map([["enforce", "enforce"], ["monitor", "advisory"], ["disabled", "declared"]]).get([...modes][0]!)!]; }
function highestDataClass(events: readonly NormalizedEvent[], config: TraceConfiguration): string { const flows = events.filter((event) => event.event_type === "data_flow.observed"); if (!flows.length) throw new TraceFinalizationError("no classified data-flow evidence is present"); const classifications = flows.map((event) => event.classification as Record<string, unknown>); if (classifications.some((value) => value.taxonomy !== config.classificationTaxonomy)) throw new TraceFinalizationError("data-flow taxonomy conflicts with TRACE configuration"); const rank = new Map(config.classificationOrder.map((value, index) => [value, index])); const values = classifications.map((value) => String(value.value)); const unknown = [...new Set(values.filter((value) => !rank.has(value)))].sort(); if (unknown.length) throw new TraceFinalizationError(`unranked data classifications are present: ${unknown.join(", ")}`); return values.reduce((highest, value) => rank.get(value)! > rank.get(highest)! ? value : highest); }
function appraisal(events: readonly NormalizedEvent[]): string { const decisions = new Map(events.filter((event) => event.event_type === "policy.decision").map((event) => [event.event_id, String(event.decision)])); const approvals = events.filter((event) => event.event_type.startsWith("approval.")); const types = new Set(approvals.map((event) => event.event_type)); if ([...decisions.values()].some((value) => value === "deny" || value === "error") || ["approval.rejected", "approval.expired", "approval.execution_failed"].some((value) => types.has(value))) return "contraindicated"; const approved = new Set(approvals.filter((event) => event.event_type === "approval.approved" && typeof event.policy_event_id === "string").map((event) => String(event.policy_event_id))); if ([...decisions].some(([id, value]) => value === "challenge" && !approved.has(id)) || types.has("approval.cancelled")) return "warning"; return decisions.size || approvals.length ? "affirming" : "none"; }
function toolTranscript(snapshot: EvidenceSnapshot): Record<string, unknown> | undefined { const actions = snapshot.entries.filter((entry) => entry.event.event_type === "action.executed").map((entry) => ({sequence: entry.sequence, event: entry.event})); if (!actions.length) return undefined; const canonical = canonicalize(actions); if (canonical === undefined) throw new TraceFinalizationError("tool transcript cannot be canonicalized"); return {hash: `sha256:${createHash("sha256").update(canonical, "utf8").digest("hex")}`, call_count: actions.length}; }
function latestSeconds(events: readonly NormalizedEvent[]): number { const latest = events.reduce((value, event) => { const current = BigInt(event.time_unix_nano); return current > value ? current : value; }, 0n) / 1_000_000_000n; if (latest > BigInt(Number.MAX_SAFE_INTEGER)) throw new TraceFinalizationError("TRACE issuance time exceeds the JavaScript safe-integer range"); return Number(latest); }
