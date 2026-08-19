import type {ContextIds, NormalizedEvent, Scalar} from "./types.js";

export const DIRECT_ATTRIBUTES: Readonly<Record<string, string>> = {
  spec_version: "agentrust.telemetry.spec_version", event_id: "agentrust.event.id",
  run_id: "agentrust.run.id", workflow_id: "agentrust.workflow.id", agent_id: "gen_ai.agent.id",
  parent_agent_id: "agentrust.agent.parent.id", task_id: "agentrust.task.id",
  decision: "agentrust.policy.decision", approval_id: "agentrust.approval.id",
  scope: "agentrust.usage.scope", direction: "agentrust.data_flow.direction",
  policy_decision: "agentrust.data_flow.policy_decision", capture_profile: "agentrust.evidence.capture_profile",
  completeness: "agentrust.evidence.completeness", action_kind: "agentrust.action.kind",
  outcome: "agentrust.action.outcome",
};
export function spanAttributes(event: NormalizedEvent): Record<string, Scalar> {
  const result: Record<string, Scalar> = {};
  for (const [source, destination] of Object.entries(DIRECT_ATTRIBUTES)) {
    const value = event[source];
    if (["string", "number", "boolean"].includes(typeof value)) result[destination] = value as Scalar;
  }
  return result;
}
export function logRecord(event: NormalizedEvent, context?: ContextIds): Record<string, unknown> {
  return {event_name: event.event_type, timestamp_ns: event.time_unix_nano, body: structuredClone(event), ...(context ? {trace_id: context.traceId, span_id: context.spanId} : {})};
}
export function hrTime(value: string): [number, number] {
  const timestamp = BigInt(value); return [Number(timestamp / 1_000_000_000n), Number(timestamp % 1_000_000_000n)];
}
