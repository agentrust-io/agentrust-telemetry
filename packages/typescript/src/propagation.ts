import {context, isSpanContextValid, propagation, trace, type Context, type Link} from "@opentelemetry/api";

export const RUN_ID_HEADER = "x-agentrust-run-id";
export const WORKFLOW_ID_HEADER = "x-agentrust-workflow-id";
export const UPSTREAM_AGENT_ID_HEADER = "x-agentrust-agent-id";
const MAX = 512;
const CONTROL = /[\x00-\x1f\x7f]/;
export class PropagationError extends Error {}

export class ExtractedContext {
  constructor(readonly otelContext: Context, readonly runId?: string, readonly workflowId?: string, readonly upstreamAgentId?: string) {}
  eventFields(agentId: string): Record<string, string> {return {agent_id: safe("agent_id", agentId), ...(this.runId !== undefined ? {run_id: this.runId} : {}), ...(this.workflowId !== undefined ? {workflow_id: this.workflowId} : {}), ...(this.upstreamAgentId !== undefined ? {parent_agent_id: this.upstreamAgentId} : {})};}
  link(attributes?: Record<string, string | number | boolean>): Link {const spanContext = trace.getSpanContext(this.otelContext); if (!spanContext || !isSpanContextValid(spanContext)) throw new PropagationError("extracted context has no valid remote span to link"); return {context: spanContext, ...(attributes ? {attributes} : {})};}
}
export function injectContext(carrier: Record<string, string>, fields: {runId: string; agentId: string; workflowId?: string; otelContext?: Context}): void {
  propagation.inject(fields.otelContext ?? context.active(), carrier);
  carrier[RUN_ID_HEADER] = safe("run_id", fields.runId); carrier[UPSTREAM_AGENT_ID_HEADER] = safe("agent_id", fields.agentId);
  if (fields.workflowId !== undefined) carrier[WORKFLOW_ID_HEADER] = safe("workflow_id", fields.workflowId);
}
export function extractContext(carrier: Record<string, string>): ExtractedContext {
  return new ExtractedContext(propagation.extract(context.active(), carrier, {keys: (c) => Object.keys(c), get: (c, key) => header(c, key)}), value(carrier, RUN_ID_HEADER), value(carrier, WORKFLOW_ID_HEADER), value(carrier, UPSTREAM_AGENT_ID_HEADER));
}
function value(carrier: Record<string, string>, name: string): string | undefined {
  const found = Object.keys(carrier).filter((key) => key.toLowerCase() === name.toLowerCase() && carrier[key] !== undefined).map((key) => safe(name, carrier[key]));
  if (new Set(found).size > 1) throw new PropagationError(`conflicting duplicate ${name} header values`);
  return found[0];
}
function header(carrier: Record<string, string>, name: string): string | string[] | undefined {const key = Object.keys(carrier).find((candidate) => candidate.toLowerCase() === name.toLowerCase()); return key ? carrier[key] : undefined;}
function safe(name: string, value: unknown): string {if (typeof value !== "string" || !value) throw new PropagationError(`${name} must be a non-empty string`); if (value.length > MAX) throw new PropagationError(`${name} exceeds ${MAX} characters`); if (/\r|\n/.test(value)) throw new PropagationError(`${name} contains a prohibited line break`); if (CONTROL.test(value)) throw new PropagationError(`${name} contains a prohibited control character`); return value;}
