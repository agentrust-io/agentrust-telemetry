import assert from "node:assert/strict";
import {readFileSync, readdirSync} from "node:fs";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {ContextMismatchError, EventFactory, EventValidationError, SchemaValidator, TelemetryClient, spanAttributes} from "../src/index.js";
import type {NormalizedEvent, SpanLike} from "../src/index.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const validator = SchemaValidator.bundled();
const fixture = (kind: "valid" | "invalid", name: string): NormalizedEvent => JSON.parse(readFileSync(`${root}/conformance/fixtures/${kind}/${name}`, "utf8")) as NormalizedEvent;

test("valid and invalid shared conformance fixtures have identical verdict classes", () => {
  for (const name of readdirSync(`${root}/conformance/fixtures/valid`).filter((item) => item.endsWith(".json"))) assert.doesNotThrow(() => validator.validate(fixture("valid", name)), name);
  for (const name of readdirSync(`${root}/conformance/fixtures/invalid`).filter((item) => item.endsWith(".json"))) assert.throws(() => validator.validate(fixture("invalid", name)), EventValidationError, name);
});

test("event construction matches the cross-language golden bytes semantically", () => {
  const factory = new EventFactory(validator, {name: "parity-test", version: "1.0.0"}, () => 1787079000000000000n, () => "018f0f7d-7a13-7cc2-8000-000000000042");
  const event = factory.build("usage.recorded", {runId: "run-1", agentId: "agent-1", workflowId: "workflow-1"}, {scope: "model_call", operation: "chat", input_tokens: 7});
  const golden = JSON.parse(readFileSync(`${root}/compatibility/golden/event-factory.json`, "utf8"));
  assert.deepEqual(event, golden);
});

test("uint64-scale nanoseconds survive construction exactly", () => {
  const factory = new EventFactory(validator, {name: "test", version: "1"});
  const event = factory.build("usage.recorded", {runId: "run-1", agentId: "agent-1", timeUnixNano: 18446744073709551615n}, {scope: "model_call", operation: "chat", input_tokens: 1});
  assert.equal(event.time_unix_nano, "18446744073709551615");
  assert.throws(() => factory.build("usage.recorded", {runId: "run-1", agentId: "agent-1", timeUnixNano: "01"}, {scope: "model_call", operation: "chat", input_tokens: 1}), /canonical/);
});

test("projection matches Python allowlist and does not flatten nested content", () => {
  const event = fixture("valid", "policy-decision.json");
  const attributes = spanAttributes(event);
  assert.equal(attributes["gen_ai.agent.id"], event.agent_id);
  assert.equal(attributes["agentrust.policy.decision"], "deny");
  assert.equal(attributes.trace_id, undefined);
  assert.equal(attributes.policy, undefined);
});

test("client validates context before all caller-owned projections", () => {
  const events: unknown[] = [];
  const span: SpanLike = {spanContext: () => ({traceId: "4bf92f3577b34da6a3ce929d0e0e4736", spanId: "00f067aa0ba902b7", traceFlags: 1}), addEvent: (...args) => events.push(args)};
  const event = {...fixture("valid", "policy-decision.json"), span_id: "1111111111111111"};
  assert.throws(() => new TelemetryClient(validator, {spanResolver: () => span}).emit(event), ContextMismatchError);
  assert.deepEqual(events, []);
});

test("invalid all-zero OTel context is treated as absent", () => {
  const events: unknown[] = [];
  const span: SpanLike = {spanContext: () => ({traceId: "0".repeat(32), spanId: "0".repeat(16), traceFlags: 1}), addEvent: (...args) => events.push(args)};
  const result = new TelemetryClient(validator, {spanResolver: () => span}).emit(fixture("valid", "usage.json"));
  assert.equal(result.spanEventEmitted, false);
  assert.equal(result.context, undefined);
  assert.deepEqual(events, []);
});

test("log body and evidence input are defensive copies", () => {
  const records: Record<string, unknown>[] = []; const evidence: NormalizedEvent[] = [];
  const event = fixture("valid", "usage.json");
  const result = new TelemetryClient(validator, {spanResolver: () => undefined, logEmitter: {emit: (record) => records.push(record)}, evidenceSink: {append: (item) => evidence.push(item)}}).emit(event);
  event.run_id = "mutated";
  assert.equal((records[0]!.body as NormalizedEvent).run_id, "run-governed-sdlc-001");
  assert.equal(evidence[0]!.run_id, "run-governed-sdlc-001");
  assert.equal(result.logEmitted, true); assert.equal(result.evidencePersisted, true);
});
