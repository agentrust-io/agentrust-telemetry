// Compiled in a temporary consumer of the packed artifact, never the checkout.
import {EventFactory, EventValidationError, SchemaValidator} from "@agentrust-io/telemetry";
import type {EnvelopeFields, NormalizedEvent} from "@agentrust-io/telemetry";

const validator: SchemaValidator = SchemaValidator.bundled();
const fields: EnvelopeFields = {runId: "run-1", timeUnixNano: 1787079000000000000n};
const factory = new EventFactory(validator, {name: "consumer", version: "1.0.0"});
const event: NormalizedEvent = factory.build("usage.recorded", fields,
  {scope: "model_call", operation: "chat", input_tokens: 7});
const runId: string = event.run_id;
const candidate: unknown = event;
validator.validate(candidate);
const validated: NormalizedEvent = candidate;
const error: Error = new EventValidationError("invalid event");
void [runId, validated, error];

// Guard against declarations silently widening the consumer API to any.
// @ts-expect-error runId must be a string
factory.build("usage.recorded", {runId: 42}, {});
// @ts-expect-error the envelope requires runId
factory.build("usage.recorded", {}, {});
// @ts-expect-error normalized event IDs are strings
const numericRunId: number = event.run_id;
void numericRunId;
