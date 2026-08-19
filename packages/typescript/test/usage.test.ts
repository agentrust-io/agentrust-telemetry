import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {CostObservation, EventFactory, SchemaValidator, UsageAccumulator, usageRecord} from "../src/index.js";

const validator = SchemaValidator.bundled();
const root = fileURLToPath(new URL("../../../", import.meta.url));
let id = 0;
const factory = new EventFactory(validator, {name: "usage-tests", version: "1"}, () => 1n, () => `00000000-0000-4000-8000-${String(++id).padStart(12, "0")}`);
const leaf = (overrides: Partial<Parameters<typeof usageRecord>[1]> = {}) => usageRecord(factory, {runId: "run-1", agentId: "agent-1", workflowId: "workflow-1", scope: "model_call", operation: "chat", inputTokens: 10, outputTokens: 2, ...overrides});

test("unknown cost stays absent and observations validate provenance", () => {
  assert.equal(leaf().cost, undefined);
  const event = leaf({cost: new CostObservation(0, "USD", "provider", "invoice-v1")});
  assert.deepEqual(event.cost, {amount: 0, currency: "USD", source: "provider", pricing_version: "invoice-v1"});
  assert.throws(() => leaf({cost: new CostObservation(Number.NaN, "USD", "estimate")}), /finite/);
  assert.throws(() => leaf({inputTokens: Number.MAX_SAFE_INTEGER + 1}), /safe integer/);
});

test("rollups deduplicate leaves, preserve partial coverage, and add costs decimally", () => {
  const first = leaf({cost: new CostObservation(0.1, "USD", "provider")});
  const second = leaf({inputTokens: 5, outputTokens: undefined, cost: new CostObservation(0.2, "USD", "caller")});
  const accumulator = new UsageAccumulator(validator);
  assert.equal(accumulator.add(first), true);
  assert.equal(accumulator.add(structuredClone(first)), false);
  assert.equal(accumulator.add(second), true);
  const rollup = accumulator.rollup(factory, {scope: "agent_run", runId: "run-1", agentId: "agent-1", workflowId: "workflow-1", operation: "chat"});
  assert.equal(rollup.input_tokens, 15); assert.equal(rollup.output_tokens, 2);
  assert.equal((rollup.cost as Record<string, unknown>).amount, 0.3);
  assert.deepEqual(rollup.aggregation, {method: "sum", event_count: 2, token_coverage: {input_tokens: 2, output_tokens: 1, cache_read_tokens: 0, cache_write_tokens: 0, reasoning_tokens: 0}, cost_coverage: 2, cost_sources: ["caller", "provider"]});
});

test("rollups reject changed duplicate IDs, non-leaves, mixed currency, and unsafe totals", () => {
  const accumulator = new UsageAccumulator(validator); const first = leaf({cost: new CostObservation(1, "USD", "caller")}); accumulator.add(first);
  assert.throws(() => accumulator.add({...first, input_tokens: 99}), /reused/);
  assert.throws(() => accumulator.add(leaf({scope: "agent_run"})), /model_call/);
  accumulator.add(leaf({cost: new CostObservation(1, "EUR", "caller")}));
  assert.throws(() => accumulator.rollup(factory, {scope: "workflow_run", runId: "run-1", agentId: "orchestrator", workflowId: "workflow-1", operation: "build"}), /mixed currencies/);

  const overflow = new UsageAccumulator(validator); overflow.add(leaf({inputTokens: Number.MAX_SAFE_INTEGER, outputTokens: undefined})); overflow.add(leaf({inputTokens: 1, outputTokens: undefined}));
  assert.throws(() => overflow.rollup(factory, {scope: "agent_run", runId: "run-1", agentId: "agent-1", operation: "chat"}), /safe-integer/);
});

test("agent and workflow rollups match the shared Python and TypeScript vector", () => {
  const vector = JSON.parse(readFileSync(`${root}/compatibility/golden/usage-rollup.json`, "utf8")) as {run_id: string; workflow_id: string; leaves: Array<{event_id: string; agent_id: string; input_tokens: number; output_tokens?: number; cost?: {amount: number; currency: string; source: "provider" | "caller"}}>; expected: Record<"agent_run" | "workflow_run", Record<string, unknown>>};
  const accumulator = new UsageAccumulator(validator);
  for (const item of vector.leaves) accumulator.add(usageRecord(factory, {runId: vector.run_id, workflowId: vector.workflow_id, agentId: item.agent_id, eventId: item.event_id, scope: "model_call", operation: "chat", inputTokens: item.input_tokens, ...(item.output_tokens === undefined ? {} : {outputTokens: item.output_tokens}), ...(item.cost ? {cost: new CostObservation(item.cost.amount, item.cost.currency, item.cost.source)} : {})}));
  for (const [scope, agentId] of [["agent_run", "agent-a"], ["workflow_run", "orchestrator"]] as const) {
    const actual = accumulator.rollup(factory, {scope, runId: vector.run_id, workflowId: vector.workflow_id, agentId, operation: "build"});
    for (const [field, expected] of Object.entries(vector.expected[scope])) assert.deepEqual(actual[field], expected, `${scope}.${field}`);
  }
});
