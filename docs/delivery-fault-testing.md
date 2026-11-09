# Delivery-fault acceptance tests

The Python and TypeScript tests read the same delivery matrix in
`compatibility/golden/delivery-faults.json` and compare retained evidence with
the existing independently pinned evidence-chain golden digests. Healthy,
dropped, duplicated, reversed and throwing log delivery must leave evidence in
its original acceptance order. Successful emitter return is not acknowledgement
from a collector. Neither delivery success nor failure establishes completeness.

Both SDKs also exercise a callback that records a commit but loses its first
acknowledgement, either by returning false or raising. The local chain and
operational projection remain untouched until the identical event is retried
and acknowledged. An idempotent test store observes one logical entry, and a
subsequent duplicate is refused before reaching the store or projection again.
The store is a test double: no crash recovery or durable persistence is proved.

Python additionally uses the real OpenTelemetry SDK with explicit ALWAYS_OFF
and ALWAYS_ON samplers and an exporter returning FAILURE. The caller-owned
provider is shut down without changing global providers. Evidence remains
available even with no sampled span; an export failure after `add_event` is not
retroactively visible in `EmitResult`. The TypeScript tests cover the shared
SDK contract, not parity of real OpenTelemetry exporter implementations.

Run with the repository's locked test dependencies:

```sh
python -m unittest discover -s tests -p test_delivery_faults.py -v
cd packages/typescript
npm ci --ignore-scripts
npm run check
```

## Remaining collector acceptance

These are executable SDK fault tests, not OTLP wire or collector interoperability
results. A separate run must pin collector/exporter versions and configuration,
retain receiver observations, and exercise retry, queue exhaustion, restart,
out-of-order delivery and partial failure. Its oracle must separately count
accepted evidence, attempted projection, collector receipt and durable backend
acknowledgement. A successful flush or exporter return alone is insufficient.
No production backend, account or network endpoint is required by these tests.
