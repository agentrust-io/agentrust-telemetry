import type {Attributes, Counter, Histogram, Meter} from "@opentelemetry/api";
import type {NormalizedEvent} from "./types.js";
import {TOKEN_FIELDS} from "./usage.js";

export class OTelMetricEmitter {
  readonly #policyCount: Counter; readonly #policyDuration: Histogram; readonly #approvalCount: Counter;
  readonly #actionCount: Counter; readonly #actionDuration: Histogram; readonly #dataFlowCount: Counter;
  readonly #tokenCount: Counter; readonly #cost: Counter; readonly #classifications: ReadonlySet<string>;
  constructor(meter: Meter, options: {classificationValues?: Iterable<string>} = {}) {
    this.#classifications = new Set(options.classificationValues ?? []);
    if (this.#classifications.size > 64) throw new Error("classificationValues cannot contain more than 64 entries");
    for (const value of this.#classifications) if (!value || value.length > 128) throw new Error("classificationValues must be non-empty and at most 128 characters");
    this.#policyCount = meter.createCounter("agentrust.policy.decisions", {unit: "{decision}", description: "Policy decisions"});
    this.#policyDuration = meter.createHistogram("agentrust.policy.evaluation.duration", {unit: "s", description: "Policy evaluation duration"});
    this.#approvalCount = meter.createCounter("agentrust.approval.events", {unit: "{event}", description: "Approval lifecycle events"});
    this.#actionCount = meter.createCounter("agentrust.action.executions", {unit: "{execution}", description: "Resolved action attempts"});
    this.#actionDuration = meter.createHistogram("agentrust.action.duration", {unit: "s", description: "Resolved action duration"});
    this.#dataFlowCount = meter.createCounter("agentrust.data_flow.events", {unit: "{event}", description: "Classified data-flow events"});
    this.#tokenCount = meter.createCounter("agentrust.usage.tokens", {unit: "{token}", description: "Reported token usage"});
    this.#cost = meter.createCounter("agentrust.usage.cost", {unit: "1", description: "Reported cost in the currency attribute"});
  }
  emit(event: NormalizedEvent): boolean {
    if (event.event_type === "policy.decision") { const a = attrs({"agentrust.policy.decision": event.decision, "agentrust.policy.enforcement_mode": event.enforcement_mode}); this.#policyCount.add(1, a); this.#policyDuration.record(Number(event.evaluation_duration_ns) / 1e9, a); return true; }
    if (event.event_type.startsWith("approval.")) { this.#approvalCount.add(1, attrs({"agentrust.approval.phase": event.event_type.slice(9), "agentrust.approval.actor_type": event.actor_type})); return true; }
    if (event.event_type === "action.executed") { const a = attrs({"agentrust.action.kind": event.action_kind, "agentrust.action.outcome": event.outcome}); this.#actionCount.add(1, a); this.#actionDuration.record(Number(event.duration_ns) / 1e9, a); return true; }
    if (event.event_type === "data_flow.observed") { const value = String((event.classification as Record<string, unknown>).value); this.#dataFlowCount.add(1, attrs({"agentrust.data_flow.direction": event.direction, "agentrust.data_flow.policy_decision": event.policy_decision, "agentrust.data_flow.classification": this.#classifications.has(value) ? value : "_other", "agentrust.data_flow.transformation": event.transformation ?? "none"})); return true; }
    if (event.event_type === "usage.recorded") { const base = {"agentrust.usage.scope": String(event.scope)}; const names = ["input", "output", "cache_read", "cache_write", "reasoning"]; TOKEN_FIELDS.forEach((field, i) => { if (typeof event[field] === "number") this.#tokenCount.add(event[field] as number, {...base, "gen_ai.token.type": names[i]!}); }); const cost = event.cost as Record<string, unknown> | undefined; if (cost) this.#cost.add(Number(cost.amount), {...base, "agentrust.cost.currency": String(cost.currency), "agentrust.cost.source": String(cost.source)}); return true; }
    return false;
  }
}
function attrs(values: Record<string, unknown>): Attributes { return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, String(value)])); }
