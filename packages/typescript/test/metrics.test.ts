import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {fileURLToPath} from "node:url";
import type {Attributes, Meter} from "@opentelemetry/api";
import {OTelMetricEmitter} from "../src/index.js";
import type {NormalizedEvent} from "../src/index.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
const fixture = (name: string): NormalizedEvent => JSON.parse(readFileSync(`${root}/conformance/fixtures/valid/${name}`, "utf8")) as NormalizedEvent;
class Instrument { calls: Array<{value: number; attributes?: Attributes}> = []; add(value: number, attributes?: Attributes) { this.calls.push({value, ...(attributes ? {attributes} : {})}); } record(value: number, attributes?: Attributes) { this.calls.push({value, ...(attributes ? {attributes} : {})}); } }
class RecordingMeter { instruments = new Map<string, Instrument>(); createCounter(name: string) { const value = new Instrument(); this.instruments.set(name, value); return value; } createHistogram(name: string) { const value = new Instrument(); this.instruments.set(name, value); return value; } }

test("usage metrics record totals without high-cardinality identity dimensions", () => {
  const meter = new RecordingMeter(); const emitter = new OTelMetricEmitter(meter as unknown as Meter);
  assert.equal(emitter.emit(fixture("usage.json")), true);
  assert.equal(meter.instruments.get("agentrust.usage.tokens")!.calls.reduce((sum, call) => sum + call.value, 0), 5012);
  assert.equal(meter.instruments.get("agentrust.usage.cost")!.calls[0]!.value, 0.0124);
  const forbidden = new Set(["agentrust.run.id", "agentrust.workflow.id", "agentrust.event.id", "gen_ai.agent.id"]);
  for (const instrument of meter.instruments.values()) for (const call of instrument.calls) for (const key of Object.keys(call.attributes ?? {})) assert.equal(forbidden.has(key), false);
});

test("classification dimensions are bounded by an explicit allowlist", () => {
  const meter = new RecordingMeter(); const emitter = new OTelMetricEmitter(meter as unknown as Meter, {classificationValues: ["public"]});
  emitter.emit(fixture("data-flow.json"));
  assert.equal(meter.instruments.get("agentrust.data_flow.events")!.calls[0]!.attributes!["agentrust.data_flow.classification"], "_other");
  assert.throws(() => new OTelMetricEmitter(new RecordingMeter() as unknown as Meter, {classificationValues: Array.from({length: 65}, (_, i) => `class-${i}`)}), /more than 64/);
});

test("policy, approval, and action metrics expose only bounded semantic dimensions", () => {
  const meter = new RecordingMeter(); const emitter = new OTelMetricEmitter(meter as unknown as Meter);
  for (const name of ["policy-decision.json", "approval.json", "action.json"]) assert.equal(emitter.emit(fixture(name)), true);
  assert.deepEqual(Object.keys(meter.instruments.get("agentrust.action.executions")!.calls[0]!.attributes!).sort(), ["agentrust.action.kind", "agentrust.action.outcome"]);
});
