import {readFileSync, readdirSync} from "node:fs";
import {createRequire} from "node:module";
import {fileURLToPath} from "node:url";
import {Ajv2020, type ErrorObject, type ValidateFunction} from "ajv/dist/2020.js";
import type {FormatsPlugin} from "ajv-formats";
import type {NormalizedEvent} from "./types.js";

const EVENT_SCHEMAS: Record<string, string> = {
  "action.executed": "action.schema.json",
  "policy.decision": "policy-decision.schema.json",
  "usage.recorded": "usage.schema.json",
  "data_flow.observed": "data-flow.schema.json",
};
const METADATA_IDENTIFIER = /^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}$/;\nconst PROHIBITED = new Set([
  "prompt", "completion", "source_code", "tool_arguments", "tool_result",
  "authorization", "credential", "secret", "access_token", "refresh_token",
]);
const addFormats = createRequire(import.meta.url)("ajv-formats") as FormatsPlugin;

export class EventValidationError extends Error {}

export class SchemaValidator {
  readonly #validators = new Map<string, ValidateFunction>();
  readonly #allowedAttributes: ReadonlySet<string>;

  static bundled(options: {allowedAttributeKeys?: Iterable<string>} = {}): SchemaValidator {
    const directory = fileURLToPath(new URL("../schemas/", import.meta.url));
    const schemas = readdirSync(directory)
      .filter((name) => name.endsWith(".schema.json"))
      .map((name) => JSON.parse(readFileSync(new URL(`../schemas/${name}`, import.meta.url), "utf8")) as object);
    return new SchemaValidator(schemas, options);
  }

  constructor(schemas: object[], options: {allowedAttributeKeys?: Iterable<string>} = {}) {
    // The normative schemas compose object constraints through allOf; Ajv's
    // non-standard strictTypes lint rejects that valid Draft 2020-12 pattern.
    const ajv = new Ajv2020({allErrors: true, strictSchema: true, strictTypes: false});
    addFormats(ajv);
    for (const schema of schemas) ajv.addSchema(schema);
    for (const [eventType, name] of Object.entries(EVENT_SCHEMAS)) {
      this.#validators.set(eventType, this.#compile(ajv, name));
    }
    this.#validators.set("approval.*", this.#compile(ajv, "approval.schema.json"));
    this.#validators.set("evidence.*", this.#compile(ajv, "evidence.schema.json"));
    this.#allowedAttributes = new Set(options.allowedAttributeKeys ?? []);
  }

  #compile(ajv: InstanceType<typeof Ajv2020>, name: string): ValidateFunction {
    const id = `https://agentrust-io.com/telemetry/v0.2/schema/${name}`;
    const validator = ajv.getSchema(id);
    if (!validator) throw new EventValidationError(`required schema is missing: ${name}`);
    return validator;
  }

  validate(value: unknown): asserts value is NormalizedEvent {
    if (!isRecord(value)) throw new EventValidationError("event must be an object");
    const eventType = String(value.event_type ?? "");
    const key = EVENT_SCHEMAS[eventType] ? eventType : eventType.startsWith("approval.") ? "approval.*" : eventType.startsWith("evidence.") ? "evidence.*" : undefined;
    if (!key) throw new EventValidationError(`unsupported event_type: ${JSON.stringify(eventType)}`);
    const validator = this.#validators.get(key)!;
    const messages: string[] = [];
    if (!validator(value)) messages.push(...formatErrors(validator.errors));
    findProhibited(value, "$", messages);
    if (eventType === "data_flow.observed") messages.push(...dataFlowSemanticErrors(value));
    if (isRecord(value.attributes)) {
      for (const key of Object.keys(value.attributes).sort()) {
        if (!this.#allowedAttributes.has(key)) messages.push(`$.attributes.${key} is not in the metadata_only attribute allowlist`);
      }
    }
    if (messages.length) throw new EventValidationError(messages.join("; "));
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function dataFlowSemanticErrors(event: Record<string, unknown>): string[] {
  const messages: string[] = [];
  const taxonomies: string[] = [];
  const identifier = (value: unknown, path: string): void => {
    if (typeof value !== "string" || !METADATA_IDENTIFIER.test(value) || value.includes("://")) {
      messages.push(`${path} must use the metadata identifier profile`);
    }
  };
  const endpoint = (value: unknown, path: string): void => {
    if (!isRecord(value)) return;
    if ("kind" in value) identifier(value.kind, `${path}.kind`);
    if ("id" in value) identifier(value.id, `${path}.id`);
  };
  const classification = (value: unknown, path: string): void => {
    if (!isRecord(value)) return;
    for (const field of ["taxonomy", "value", "producer"] as const) {
      if (field in value) identifier(value[field], `${path}.${field}`);
    }
    if (typeof value.taxonomy === "string") taxonomies.push(value.taxonomy);
  };

  identifier(event.purpose, "$.purpose");
  endpoint(event.source, "$.source");
  endpoint(event.destination, "$.destination");
  classification(event.classification, "$.classification");
  classification(event.observed_classification, "$.observed_classification");

  if (Array.isArray(event.source_classifications)) {
    const seen = new Set<string>();
    event.source_classifications.forEach((item, index) => {
      if (!isRecord(item)) return;
      const path = `$.source_classifications[${index}]`;
      endpoint(item.source, `${path}.source`);
      classification(item.classification, `${path}.classification`);
      if (isRecord(item.source) && typeof item.source.kind === "string") {
        const id = typeof item.source.id === "string" ? item.source.id : "";
        const key = `${item.source.kind}\\u0000${id}`;
        if (seen.has(key)) messages.push(`${path}.source duplicates a prior (kind, id) reference`);
        seen.add(key);
      }
    });
  }
  if (new Set(taxonomies).size > 1) {
    messages.push("all data-flow classifications must use the same taxonomy");
  }
  return messages;
}
function formatErrors(errors: ErrorObject[] | null | undefined): string[] {
  return (errors ?? []).map((error) => `${error.instancePath || "$"} ${error.message ?? "is invalid"}`);
}
function findProhibited(value: unknown, path: string, messages: string[]): void {
  if (Array.isArray(value)) value.forEach((child, index) => findProhibited(child, `${path}[${index}]`, messages));
  else if (isRecord(value)) for (const [key, child] of Object.entries(value)) {
    const childPath = `${path}.${key}`;
    if (PROHIBITED.has(key.toLowerCase())) messages.push(`${childPath} is prohibited by metadata_only`);
    findProhibited(child, childPath, messages);
  }
}
