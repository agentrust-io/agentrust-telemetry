import assert from "node:assert/strict";
import test from "node:test";
import {agtDataAccessFlow, ClassificationResult, classifiedDataFlow, DataEndpoint, EventFactory, SchemaValidator} from "../src/index.js";

const factory = new EventFactory(SchemaValidator.bundled(), {name: "data-tests", version: "1"}, () => 1n, () => "018f0f7d-7a13-7cc2-8000-000000000042");
test("classifier sees content while the event contains only closed metadata", () => {
  const secret = {prompt: "customer@example.test token=secret", source_code: "private"}; let seen: unknown;
  const event = classifiedDataFlow(factory, {classify: (value) => { seen = value; return new ClassificationResult("example.enterprise.v1", "confidential", "dlp.v2"); }}, secret, {runId: "run-1", agentId: "agent-1", direction: "read", source: new DataEndpoint("repository", "application-source"), destination: new DataEndpoint("agent", "builder"), purpose: "architecture-generation", contentDigest: {algorithm: "sha256", value: "a".repeat(64)}, transformation: "metadata_only"});
  assert.equal(seen, secret); const serialized = JSON.stringify(event); for (const value of ["customer@example", "token=secret", "source_code", "private"]) assert.equal(serialized.includes(value), false);
});
test("classification boundary rejects arbitrary results and prose identifiers", () => {
  assert.throws(() => classifiedDataFlow(factory, {classify: () => ({taxonomy: "x", value: "confidential", producer: "x"}) as ClassificationResult}, "secret", {runId: "r", agentId: "a", direction: "read", source: new DataEndpoint("repository"), destination: new DataEndpoint("agent"), purpose: "review"}), /ClassificationResult/);
  for (const value of ["customer secret", "/customers/42.txt", "https://example.test/secret", "token=secret", "x?key=y"]) assert.throws(() => new DataEndpoint("source", value), /metadata identifier/);
  assert.throws(() => new ClassificationResult("example", "customer secret", "classifier"), /metadata identifier/);
  assert.throws(() => classifiedDataFlow(factory, {classify: () => new ClassificationResult("example", "internal", "classifier")}, null, {runId: "r", agentId: "a", direction: "read", source: new DataEndpoint("repository"), destination: new DataEndpoint("agent"), purpose: "review", sizeBytes: Number.MAX_SAFE_INTEGER + 1}), /safe integer/);
});
test("AGT access maps only tier, decision, agent, and time", () => {
  const decision = {allowed: false, reason: "SSN 123-45-6789 denied", agent_id: "agent-1", data_label: {classification: 2, categories: ["PII", "customer@example.test"], owner: "alice@example.test", geography: "EU"}, matched_policy: "secret", evaluated_at: "2026-08-18T12:00:00Z"};
  const event = agtDataAccessFlow(factory, decision, {runId: "run-1", direction: "read", source: new DataEndpoint("database", "customer-records"), destination: new DataEndpoint("agent", "builder"), purpose: "requirements-analysis"});
  assert.equal((event.classification as Record<string, unknown>).value, "confidential"); assert.equal(event.policy_decision, "deny");
  const serialized = JSON.stringify(event); for (const value of ["PII", "customer@example", "alice@example", "123-45-6789", "geography", "matched_policy"]) assert.equal(serialized.includes(value), false);
});
