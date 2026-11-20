import assert from "node:assert/strict";
import test from "node:test";
import {agtDataAccessFlow, ClassificationOrder, ClassificationResult, classifiedDataFlow, DataEndpoint, EventFactory, SchemaValidator, SourceClassification} from "../src/index.js";

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
  assert.throws(() => agtDataAccessFlow(factory, {...decision, evaluated_at: "1969-12-31T23:59:59Z"}, {runId: "run-1", direction: "read", source: new DataEndpoint("database", "customer-records"), destination: new DataEndpoint("agent", "builder"), purpose: "requirements-analysis"}), /evaluated_at is invalid/);
  assert.throws(() => agtDataAccessFlow(factory, null as unknown as Record<string, unknown>, {runId: "run-1", direction: "read", source: new DataEndpoint("database", "customer-records"), destination: new DataEndpoint("agent", "builder"), purpose: "requirements-analysis"}), /must be an object/);
});


test("derived flow inherits the strictest source label and emits metadata only", () => {
  const taxonomy = "example.enterprise.v1";
  const order = new ClassificationOrder(taxonomy, ["public", "internal", "confidential", "restricted"]);
  const observed = new ClassificationResult(taxonomy, "public", "output-dlp");
  const event = classifiedDataFlow(factory, {classify: () => observed}, "summary text", {
    runId: "run-1", agentId: "agent-1", direction: "output",
    source: new DataEndpoint("transform", "summarizer"),
    destination: new DataEndpoint("memory", "summary-1"), purpose: "memory-compaction",
    transformation: "aggregated", classificationOrder: order,
    sourceClassifications: [
      new SourceClassification(new DataEndpoint("document", "public-faq"), new ClassificationResult(taxonomy, "public", "source-dlp")),
      new SourceClassification(new DataEndpoint("document", "staff-notes"), new ClassificationResult(taxonomy, "confidential", "trusted-label-store")),
    ],
  });
  assert.equal((event.classification as Record<string, unknown>).value, "confidential");
  assert.equal((event.observed_classification as Record<string, unknown>).value, "public");
  assert.equal((event.source_classifications as unknown[]).length, 2);
  assert.equal(JSON.stringify(event).includes("summary text"), false);
});
test("derived flow rejects missing, duplicate, and incomparable source labels", () => {
  const taxonomy = "example.enterprise.v1";
  const order = new ClassificationOrder(taxonomy, ["public", "confidential"]);
  const output = new ClassificationResult(taxonomy, "public", "dlp");
  const options = {runId: "r", agentId: "a", direction: "output", source: new DataEndpoint("transform"), destination: new DataEndpoint("memory"), purpose: "compaction"};
  assert.throws(() => classifiedDataFlow(factory, {classify: () => output}, "summary", {...options, sourceClassifications: []}), /supplied together/);
  assert.throws(() => classifiedDataFlow(factory, {classify: () => output}, "summary", {...options, sourceClassifications: [], classificationOrder: order}), /at least one source/);
  const duplicate = new SourceClassification(new DataEndpoint("document", "same"), new ClassificationResult(taxonomy, "confidential", "dlp"));
  assert.throws(() => classifiedDataFlow(factory, {classify: () => output}, "summary", {...options, sourceClassifications: [duplicate, duplicate], classificationOrder: order}), /duplicate source/);
  const mismatched = new SourceClassification(new DataEndpoint("document", "other"), new ClassificationResult("example.other.v1", "confidential", "dlp"));
  assert.throws(() => classifiedDataFlow(factory, {classify: () => output}, "summary", {...options, sourceClassifications: [mismatched], classificationOrder: order}), /taxonomy mismatch/);
  const unknown = new SourceClassification(new DataEndpoint("document", "unknown"), new ClassificationResult(taxonomy, "top_secret", "dlp"));
  assert.throws(() => classifiedDataFlow(factory, {classify: () => output}, "summary", {...options, sourceClassifications: [unknown], classificationOrder: order}), /unknown classification value/);
  const tooMany = Array.from({length: 1025}, (_, index) => new SourceClassification(new DataEndpoint("document", `source-${index}`), new ClassificationResult(taxonomy, "public", "dlp")));
  assert.throws(() => classifiedDataFlow(factory, {classify: () => output}, "summary", {...options, sourceClassifications: tooMany, classificationOrder: order}), /at most 1024/);
  const exactlyLimit = Array.from({length: 1024}, (_, index) => new SourceClassification(new DataEndpoint("document", `source-${index}`), new ClassificationResult(taxonomy, "public", "dlp")));
  const atLimit = classifiedDataFlow(factory, {classify: () => output}, "summary", {...options, sourceClassifications: exactlyLimit, classificationOrder: order});
  assert.equal((atLimit.source_classifications as unknown[]).length, 1024);
});


test("output classification is not downgraded and wins ties", () => {
  const taxonomy = "example.enterprise.v1";
  const order = new ClassificationOrder(taxonomy, ["public", "confidential", "restricted"]);
  const source = new SourceClassification(
    new DataEndpoint("document", "staff-notes"),
    new ClassificationResult(taxonomy, "confidential", "trusted-label-store"),
  );
  const options = {
    runId: "run-1", agentId: "agent-1", direction: "output",
    source: new DataEndpoint("transform", "summarizer"),
    destination: new DataEndpoint("memory", "summary-1"),
    purpose: "memory-compaction",
    sourceClassifications: [source],
    classificationOrder: order,
  };

  const stricterOutput = new ClassificationResult(taxonomy, "restricted", "output-dlp");
  const event = classifiedDataFlow(factory, {classify: () => stricterOutput}, "summary", options);
  assert.equal((event.classification as Record<string, unknown>).value, "restricted");
  assert.equal((event.classification as Record<string, unknown>).producer, "output-dlp");

  const tiedOutput = new ClassificationResult(taxonomy, "confidential", "output-dlp");
  const tiedEvent = classifiedDataFlow(factory, {classify: () => tiedOutput}, "summary", options);
  assert.equal((tiedEvent.classification as Record<string, unknown>).value, "confidential");
  assert.equal((tiedEvent.classification as Record<string, unknown>).producer, "output-dlp");
});

