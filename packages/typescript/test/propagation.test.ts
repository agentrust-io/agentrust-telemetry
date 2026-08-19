import assert from "node:assert/strict";
import test from "node:test";
import {context, propagation, trace, TraceFlags} from "@opentelemetry/api";
import {W3CTraceContextPropagator} from "@opentelemetry/core";
import {extractContext, injectContext, PropagationError} from "../src/index.js";

propagation.setGlobalPropagator(new W3CTraceContextPropagator());
const spanContext = {traceId: "4bf92f3577b34da6a3ce929d0e0e4736", spanId: "00f067aa0ba902b7", traceFlags: TraceFlags.SAMPLED, isRemote: false};

test("W3C and durable AgentTrust context round-trip", () => {
  const carrier: Record<string, string> = {};
  injectContext(carrier, {runId: "run-1", workflowId: "workflow-1", agentId: "agent-a", otelContext: trace.setSpanContext(context.active(), spanContext)});
  assert.match(carrier.traceparent!, /^00-4bf92f/);
  const extracted = extractContext(carrier);
  assert.deepEqual(extracted.eventFields("agent-b"), {agent_id: "agent-b", run_id: "run-1", workflow_id: "workflow-1", parent_agent_id: "agent-a"});
  assert.equal(extracted.link().context.traceId, spanContext.traceId);
});

test("headers are case-insensitive and reject line breaks", () => {
  assert.equal(extractContext({"X-AgenTrust-Run-Id": "run-1"}).runId, "run-1");
  assert.throws(() => injectContext({}, {runId: "run\r\nattack", agentId: "agent-a"}), PropagationError);
});
