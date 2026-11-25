import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {hrTime, spanAttributes} from "../src/projection.js";
import type {NormalizedEvent} from "../src/types.js";

const corpus = JSON.parse(readFileSync(
  new URL("../../../conformance/parity/projection-boundaries.json", import.meta.url), "utf8",
));
for (const row of corpus.timestamps) {
  test("shared timestamp " + row.input, () => assert.deepEqual(hrTime(row.input), row.tuple));
}
for (const value of corpus.invalid_timestamps) {
  test("shared noncanonical timestamp " + JSON.stringify(value), () => {
    assert.throws(() => hrTime(value));
  });
}
const special: Record<string, number> = {
  nan: Number.NaN, positive_infinity: Number.POSITIVE_INFINITY,
  negative_infinity: Number.NEGATIVE_INFINITY,
};
for (const row of corpus.projections) {
  test("shared scalar projection " + row.id, () => {
    const event = {...row.event};
    for (const [key, value] of Object.entries(row.special ?? {})) {
      event[key] = special[value as string];
    }
    assert.deepEqual(spanAttributes(event as NormalizedEvent), row.expected);
  });
}
