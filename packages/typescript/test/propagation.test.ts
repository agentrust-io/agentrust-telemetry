import assert from "node:assert/strict";
import test from "node:test";
import {context, propagation, trace, TraceFlags} from "@opentelemetry/api";
import {W3CTraceContextPropagator} from "@opentelemetry/core";
import {extractContext, injectContext, PropagationError, RUN_ID_HEADER, UPSTREAM_AGENT_ID_HEADER, WORKFLOW_ID_HEADER} from "../src/index.js";

propagation.setGlobalPropagator(new W3CTraceContextPropagator());
const spanContext = {traceId: "4bf92f3577b34da6a3ce929d0e0e4736", spanId: "00f067aa0ba902b7", traceFlags: TraceFlags.SAMPLED, isRemote: false};

test("W3C and durable AgenTrust context round-trip", () => {
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

test("extractContext rejects array-valued and non-string AgenTrust carrier headers and eventFields checks !== undefined", () => {
  assert.throws(
    () => extractContext({"x-agentrust-run-id": ["attacker-run-id", "trusted-run-id"] as unknown as string}),
    PropagationError,
  );
  assert.throws(
    () => extractContext({"x-agentrust-workflow-id": ["wf-1", "wf-2"] as unknown as string}),
    PropagationError,
  );
  assert.throws(
    () => extractContext({"x-agentrust-agent-id": ["agent-1"] as unknown as string}),
    PropagationError,
  );
  assert.throws(
    () => extractContext({"x-agentrust-run-id": 123 as unknown as string}),
    PropagationError,
  );
  const direct = new (extractContext({}).constructor as typeof import("../src/index.js").ExtractedContext)(
    context.active(),
    "",
    "",
    "",
  );
  assert.deepEqual(direct.eventFields("agent-b"), {
    agent_id: "agent-b",
    run_id: "",
    workflow_id: "",
    parent_agent_id: "",
  });
});

const AGENTRUST_HEADERS = [
  [RUN_ID_HEADER, "runId"],
  [WORKFLOW_ID_HEADER, "workflowId"],
  [UPSTREAM_AGENT_ID_HEADER, "upstreamAgentId"],
] as const;

test("injectContext and extractContext reject ASCII control characters in every AgenTrust value", () => {
  for (const bad of ["a\x00b", "a\x1fb", "a\x7fb", "a\tb", "a\x0bb"]) {
    for (const [field, value] of [["run_id", {runId: bad, agentId: "agent-a"}], ["agent_id", {runId: "run-1", agentId: bad}], ["workflow_id", {runId: "run-1", agentId: "agent-a", workflowId: bad}]] as const) {
      assert.throws(() => injectContext({}, value), (error) => error instanceof PropagationError && error.message === `${field} contains a prohibited control character`, `${field} ${JSON.stringify(bad)}`);
    }
    for (const [header] of AGENTRUST_HEADERS) {
      assert.throws(() => extractContext({[header]: bad}), (error) => error instanceof PropagationError && /prohibited control character/.test(error.message), `${header} ${JSON.stringify(bad)}`);
    }
  }
  // Valid twins either side of the rejected range: space and tilde.
  const carrier: Record<string, string> = {};
  injectContext(carrier, {runId: "run 1", agentId: "agent~a", workflowId: "~"});
  assert.deepEqual([carrier[RUN_ID_HEADER], carrier[UPSTREAM_AGENT_ID_HEADER], carrier[WORKFLOW_ID_HEADER]], ["run 1", "agent~a", "~"]);
  for (const [header, field] of AGENTRUST_HEADERS) assert.equal(extractContext({[header]: "a b~"})[field], "a b~");
});

test("extractContext rejects conflicting case-insensitive duplicates and accepts identical ones", () => {
  for (const [header] of AGENTRUST_HEADERS) {
    assert.throws(() => extractContext({[header.toUpperCase()]: "first", [header]: "second"}), (error) => error instanceof PropagationError && error.message === `conflicting duplicate ${header} header values`);
    assert.throws(() => extractContext({[header]: "first", [header.toUpperCase()]: "second", "X-Other": "x"}), /conflicting duplicate/);
    // Every duplicate is validated, so a bad value cannot hide behind an identical twin.
    assert.throws(() => extractContext({[header.toUpperCase()]: "bad\x00", [header]: "bad\x00"}), /prohibited control character/);
  }
  const extracted = extractContext({"X-AgenTrust-Run-Id": "run-1", "x-agentrust-run-id": "run-1", "X-AGENTRUST-WORKFLOW-ID": "workflow-1", "x-agentrust-workflow-id": "workflow-1", "X-Agentrust-Agent-Id": "agent-a", "x-agentrust-agent-id": "agent-a"});
  assert.deepEqual([extracted.runId, extracted.workflowId, extracted.upstreamAgentId], ["run-1", "workflow-1", "agent-a"]);
});

test("AgenTrust values are limited to 512 characters", () => {
  const carrier: Record<string, string> = {};
  injectContext(carrier, {runId: "r".repeat(512), agentId: "a"});
  assert.equal(carrier[RUN_ID_HEADER]!.length, 512);
  assert.throws(() => injectContext({}, {runId: "r".repeat(513), agentId: "a"}), /run_id exceeds 512 characters/);
  for (const [header, field] of AGENTRUST_HEADERS) {
    assert.equal(extractContext({[header]: "v".repeat(512)})[field]!.length, 512);
    assert.throws(() => extractContext({[header]: "v".repeat(513)}), /exceeds 512 characters/);
  }
});

test("extractContext treats an AgenTrust header set to undefined as absent", () => {
  const extracted = extractContext({[RUN_ID_HEADER]: undefined as unknown as string, "X-AgenTrust-Run-Id": "run-1"});
  assert.equal(extracted.runId, "run-1");
  assert.equal(extractContext({[RUN_ID_HEADER]: undefined as unknown as string}).runId, undefined);
});
