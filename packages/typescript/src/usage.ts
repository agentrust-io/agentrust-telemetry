import {Decimal} from "decimal.js";
import canonicalize from "canonicalize";
import {EventFactory, type EnvelopeFields} from "./factory.js";
import type {NormalizedEvent} from "./types.js";
import {SchemaValidator} from "./validation.js";

export const TOKEN_FIELDS = ["input_tokens", "output_tokens", "cache_read_tokens", "cache_write_tokens", "reasoning_tokens"] as const;
export type UsageScope = "model_call" | "agent_step" | "task" | "agent_run" | "workflow_run";
export type CostSource = "provider" | "caller" | "price_resolver" | "estimate";

export class CostObservation {
  constructor(readonly amount: number | string, readonly currency: string, readonly source: CostSource, readonly pricingVersion?: string) {}
  asEventValue(): Record<string, unknown> {
    const amount = Number(this.amount);
    if (!Number.isFinite(amount) || amount < 0) throw new Error("cost amount must be a finite non-negative number");
    if (!/^[A-Z]{3}$/.test(this.currency)) throw new Error("cost currency must be a three-letter uppercase ASCII code");
    if (!["provider", "caller", "price_resolver", "estimate"].includes(this.source)) throw new Error("cost source is not supported");
    if (this.pricingVersion === "") throw new Error("pricingVersion must be non-empty");
    return {amount, currency: this.currency, source: this.source, ...(this.pricingVersion === undefined ? {} : {pricing_version: this.pricingVersion})};
  }
}

export interface UsageRecordFields extends EnvelopeFields {
  scope: UsageScope; operation: string; provider?: string; requestModel?: string; responseModel?: string;
  inputTokens?: number; outputTokens?: number; cacheReadTokens?: number; cacheWriteTokens?: number; reasoningTokens?: number;
  cost?: CostObservation;
}

export function usageRecord(factory: EventFactory, fields: UsageRecordFields): NormalizedEvent {
  const tokens = {input_tokens: fields.inputTokens, output_tokens: fields.outputTokens, cache_read_tokens: fields.cacheReadTokens, cache_write_tokens: fields.cacheWriteTokens, reasoning_tokens: fields.reasoningTokens};
  for (const [name, value] of Object.entries(tokens)) if (value !== undefined && (!Number.isSafeInteger(value) || value < 0)) throw new TypeError(`${name} must be a non-negative safe integer`);
  return factory.build("usage.recorded", fields, {
    scope: fields.scope, operation: fields.operation,
    ...present("provider", fields.provider), ...present("request_model", fields.requestModel), ...present("response_model", fields.responseModel),
    ...Object.fromEntries(Object.entries(tokens).filter(([, value]) => value !== undefined)),
    ...(fields.cost ? {cost: fields.cost.asEventValue()} : {}),
  });
}

export class UsageAccumulator {
  readonly #events = new Map<string, NormalizedEvent>();
  constructor(readonly validator: SchemaValidator = SchemaValidator.bundled()) {}

  add(event: NormalizedEvent): boolean {
    this.validator.validate(event);
    if (event.event_type !== "usage.recorded") throw new Error("only usage.recorded events can be accumulated");
    if (event.scope !== "model_call") throw new Error("only model_call leaf events can be accumulated");
    for (const field of TOKEN_FIELDS) { const value = event[field]; if (value !== undefined && (!Number.isSafeInteger(value) || (value as number) < 0)) throw new TypeError(`${field} must be a non-negative safe integer`); }
    const cost = event.cost as Record<string, unknown> | undefined;
    if (cost && (typeof cost.amount !== "number" || !Number.isFinite(cost.amount) || cost.amount < 0)) throw new Error("cost amount must be a finite non-negative number");
    const retained = this.#events.get(event.event_id);
    if (retained) { if (canonicalize(retained) !== canonicalize(event)) throw new Error("event_id was reused with different usage data"); return false; }
    this.#events.set(event.event_id, structuredClone(event));
    return true;
  }

  rollup(factory: EventFactory, fields: {scope: "agent_run" | "workflow_run"; runId: string; operation: string; agentId: string; workflowId?: string}): NormalizedEvent {
    if (fields.scope === "workflow_run" && fields.workflowId === undefined) throw new Error("workflowId is required for workflow_run rollups");
    const matches = [...this.#events.values()].filter((event) => event.run_id === fields.runId && (fields.scope === "workflow_run" || event.agent_id === fields.agentId) && (fields.workflowId === undefined || event.workflow_id === fields.workflowId));
    if (!matches.length) throw new Error("no matching model_call usage events");
    const payload: Record<string, unknown> = {scope: fields.scope, operation: fields.operation};
    const coverage: Record<string, number> = {};
    for (const field of TOKEN_FIELDS) { const observed = matches.flatMap((event) => typeof event[field] === "number" ? [event[field] as number] : []); coverage[field] = observed.length; if (observed.length) { const total = observed.reduce((sum, value) => sum + value, 0); if (!Number.isSafeInteger(total)) throw new Error(`${field} rollup exceeds the JavaScript safe-integer range`); payload[field] = total; } }
    const costs = matches.flatMap((event) => event.cost ? [event.cost as Record<string, unknown>] : []);
    const currencies = new Set(costs.map((cost) => String(cost.currency)));
    if (currencies.size > 1) throw new Error("cannot roll up costs with mixed currencies");
    if (costs.length) payload.cost = {amount: Number(costs.reduce((sum, cost) => sum.plus(String(cost.amount)), new Decimal(0)).toString()), currency: [...currencies][0], source: "aggregate"};
    payload.aggregation = {method: "sum", event_count: matches.length, token_coverage: coverage, cost_coverage: costs.length, cost_sources: [...new Set(costs.map((cost) => String(cost.source)))].sort()};
    return factory.build("usage.recorded", {runId: fields.runId, agentId: fields.agentId, ...(fields.workflowId === undefined ? {} : {workflowId: fields.workflowId})}, payload);
  }
}

function present(key: string, value: string | undefined): Record<string, string> { return value === undefined ? {} : {[key]: value}; }
