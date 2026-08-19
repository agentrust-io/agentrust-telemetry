import {randomUUID} from "node:crypto";
import type {NormalizedEvent} from "./types.js";
import {SchemaValidator} from "./validation.js";

const RESERVED = new Set(["spec_version", "event_id", "event_type", "time_unix_nano", "run_id", "producer", "agent_id", "workflow_id", "parent_agent_id", "task_id", "trace_id", "span_id"]);

export interface EnvelopeFields {
  runId: string; agentId?: string; workflowId?: string; parentAgentId?: string;
  taskId?: string; traceId?: string; spanId?: string; eventId?: string;
  timeUnixNano?: bigint | string;
}

export class EventFactory {
  readonly #producer: NormalizedEvent["producer"];
  constructor(
    readonly validator: SchemaValidator,
    producer: {name: string; version: string; instanceId?: string},
    readonly clockNs: () => bigint = () => BigInt(Date.now()) * 1_000_000n,
    readonly eventIdFactory: () => string = randomUUID,
  ) {
    this.#producer = {name: producer.name, version: producer.version, ...(producer.instanceId ? {instance_id: producer.instanceId} : {})};
  }

  build(eventType: string, fields: EnvelopeFields, payload: Record<string, unknown>): NormalizedEvent {
    const collisions = Object.keys(payload).filter((key) => RESERVED.has(key)).sort();
    if (collisions.length) throw new Error(`payload cannot override envelope fields: ${collisions.join(", ")}`);
    const normalizedPayload = Object.fromEntries(Object.entries(payload).map(([key, value]) => [key, key.endsWith("_at_unix_nano") ? unixNano(value) : value]));
    const event = {
      spec_version: "0.1.0-dev" as const,
      event_id: fields.eventId ?? this.eventIdFactory(), event_type: eventType,
      time_unix_nano: unixNano(fields.timeUnixNano ?? this.clockNs()),
      run_id: fields.runId, producer: structuredClone(this.#producer), ...normalizedPayload,
      ...optional("agent_id", fields.agentId), ...optional("workflow_id", fields.workflowId),
      ...optional("parent_agent_id", fields.parentAgentId), ...optional("task_id", fields.taskId),
      ...optional("trace_id", fields.traceId), ...optional("span_id", fields.spanId),
    };
    this.validator.validate(event);
    return event;
  }
}

export function unixNano(value: unknown): string {
  if (typeof value !== "bigint" && typeof value !== "string") throw new TypeError("Unix nanosecond timestamps must be bigint values or decimal strings");
  const text = String(value);
  if (!/^(0|[1-9][0-9]{0,19})$/.test(text)) throw new Error("Unix nanosecond timestamps must be canonical non-negative decimals of at most 20 digits");
  return text;
}
function optional(key: string, value: string | undefined): Record<string, string> {return value === undefined ? {} : {[key]: value};}
