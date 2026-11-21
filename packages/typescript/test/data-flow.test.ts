import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {fileURLToPath} from "node:url";
import {agtDataAccessFlow, ClassificationOrder, ClassificationResult, classifiedDataFlow, DataEndpoint, EventFactory, SchemaValidator, SourceClassification} from "../src/index.js";

const root = fileURLToPath(new URL("../../../", import.meta.url));
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


test("classification metadata objects are immutable at runtime", () => {
  const taxonomy = "example.enterprise.v1";
  const classification = new ClassificationResult(taxonomy, "confidential", "trusted-store");
  const endpoint = new DataEndpoint("document", "staff-notes");
  const source = new SourceClassification(endpoint, classification);
  const order = new ClassificationOrder(taxonomy, ["public", "confidential"]);
  for (const value of [classification, endpoint, source, order]) assert.equal(Object.isFrozen(value), true);
  assert.equal(Object.isFrozen(order.levels), true);
  assert.equal(Reflect.set(classification, "value", "public"), false);
  assert.equal(Reflect.set(endpoint, "id", "replacement"), false);
  assert.equal(Reflect.set(order, "taxonomy", "other.taxonomy"), false);
  assert.deepEqual(order.levels, ["public", "confidential"]);
});

test("cheap lineage validation runs before the classifier", () => {
  const taxonomy = "example.enterprise.v1";
  const order = new ClassificationOrder(taxonomy, ["public", "confidential"]);
  const classification = new ClassificationResult(taxonomy, "confidential", "trusted-store");
  const duplicate = new SourceClassification(new DataEndpoint("document", "same"), classification);
  let called = false;
  const options = {
    runId: "run-1", agentId: "agent-1", direction: "output",
    source: new DataEndpoint("transform"), destination: new DataEndpoint("memory"),
    purpose: "memory-compaction",
    sourceClassifications: [duplicate, duplicate],
    classificationOrder: order,
  };
  assert.throws(() => classifiedDataFlow(factory, {classify: () => {
    called = true;
    return new ClassificationResult(taxonomy, "public", "dlp");
  }}, "summary", options), /duplicate source/);
  assert.equal(called, false);
});

test("SchemaValidator enforces data-flow lineage, identifier, and integer invariants", () => {
  const taxonomy = "example.enterprise.v1";
  const order = new ClassificationOrder(taxonomy, ["public", "confidential"]);
  const sources = [
    new SourceClassification(new DataEndpoint("document", "public-faq"),
      new ClassificationResult(taxonomy, "public", "source-dlp")),
    new SourceClassification(new DataEndpoint("document", "staff-notes"),
      new ClassificationResult(taxonomy, "confidential", "trusted-store")),
  ];
  const event = classifiedDataFlow(factory,
    {classify: () => new ClassificationResult(taxonomy, "public", "output-dlp")},
    "summary", {
      runId: "run-1", agentId: "agent-1", direction: "output",
      source: new DataEndpoint("transform", "summarizer"),
      destination: new DataEndpoint("memory", "summary-1"),
      purpose: "memory-compaction",
      sourceClassifications: sources,
      classificationOrder: order,
    });
  const validator = SchemaValidator.bundled();
  const clone = () => JSON.parse(JSON.stringify(event)) as Record<string, unknown>;

  const duplicate = clone();
  const duplicateSources = duplicate.source_classifications as Array<Record<string, unknown>>;
  duplicateSources[1]!.source = {...duplicateSources[0]!.source as Record<string, unknown>};
  assert.throws(() => validator.validate(duplicate), /duplicates a prior/);

  const mixed = clone();
  const mixedSources = mixed.source_classifications as Array<Record<string, unknown>>;
  (mixedSources[0]!.classification as Record<string, unknown>).taxonomy = "other.taxonomy";
  assert.throws(() => validator.validate(mixed), /same taxonomy/);

  const badIdentifier = clone();
  const badSources = badIdentifier.source_classifications as Array<Record<string, unknown>>;
  (badSources[0]!.source as Record<string, unknown>).kind = "customer data";
  assert.throws(() => validator.validate(badIdentifier), /metadata identifier profile/);

  const unsafe = clone();
  unsafe.size_bytes = Number.MAX_SAFE_INTEGER + 1;
  assert.throws(() => validator.validate(unsafe));
});


test("derived flow matches the shared Python/TypeScript golden event", () => {
  const expected = JSON.parse(readFileSync(
    `${root}/compatibility/golden/derived-data-flow.json`, "utf8"
  )) as Record<string, unknown>;
  const goldenFactory = new EventFactory(
    SchemaValidator.bundled(),
    {name: "derived-flow-golden", version: "1.0.0"},
    () => 1n,
    () => "018f0f7d-7a13-7cc2-8000-000000000042",
  );
  const taxonomy = "example.enterprise.v1";
  const event = classifiedDataFlow(
    goldenFactory,
    {classify: () => new ClassificationResult(taxonomy, "public", "output-dlp")},
    "summary",
    {
      runId: "run-golden-derived-flow",
      agentId: "agent-1",
      direction: "output",
      source: new DataEndpoint("transform", "summarizer"),
      destination: new DataEndpoint("memory", "summary-1"),
      purpose: "memory-compaction",
      policyDecision: "allow",
      transformation: "aggregated",
      sourceClassifications: [
        new SourceClassification(
          new DataEndpoint("knowledge_graph", "public-faq"),
          new ClassificationResult(taxonomy, "public", "source-dlp"),
        ),
        new SourceClassification(
          new DataEndpoint("document", "staff-notes"),
          new ClassificationResult(taxonomy, "confidential", "trusted-label-store"),
        ),
      ],
      classificationOrder: new ClassificationOrder(
        taxonomy, ["public", "internal", "confidential", "restricted"]
      ),
      envelope: {
        eventId: "018f0f7d-7a13-7cc2-8000-000000000042",
        timeUnixNano: "1787079400000000000",
      },
    },
  );
  assert.deepEqual(event, expected);
});
