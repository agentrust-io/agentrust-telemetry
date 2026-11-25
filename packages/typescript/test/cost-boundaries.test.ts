import assert from "node:assert/strict";
import test from "node:test";
import {CostObservation} from "../src/index.js";

test("cost accepts numeric zero and explicit numeric strings", () => {
  for (const amount of [0, "0", 1.25, "1.25"]) {
    assert.equal(new CostObservation(amount, "USD", "provider").asEventValue().amount, Number(amount));
  }
});

test("cost refuses values that Number would silently coerce", () => {
  for (const amount of [true, false, null, [], [1], {}, "", " ", "\t\n"]) {
    assert.throws(() => new CostObservation(amount as number, "USD", "provider").asEventValue(), /finite non-negative/);
  }
});
