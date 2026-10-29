# Projection boundary corpus

Both SDK test suites consume projection-boundaries.json. This slice covers six canonical timestamps, thirteen noncanonical spellings, and five scalar projection cases. Nonfinite values use local special-value tags because they have no JSON representation. These projection inputs are not assertions that arbitrary event fields pass the event schema.

This companion is based on telemetry #119. Other adapter timestamp/duration and EventFactory corrections remain in #116–120; it neither replaces those fixes nor claims their acceptance. The 20-digit tuple is an explicit positive boundary; logs, delivery, collector behavior and hardware are separate.
