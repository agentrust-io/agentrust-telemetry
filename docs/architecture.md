# Architecture

## Boundary

AgentTrust Telemetry is a schema-first instrumentation layer between governance sources and adopter-owned telemetry/evidence destinations.

```text
policy / approval / usage / data hooks
                 │
                 v
        normalized event contract
                 │
          schema + privacy gate
                 │
        ┌────────┴─────────┐
        v                  v
 OTel projection     evidence projection
 (best effort)       (future, durable)
        │                  │
 adopter's OTLP       TRACE finalizer
 collector/backend      (future)
```

## Current components

### Normative contract

JSON Schema 2020-12 files in `spec/schema` define the five event families. Closed schemas reject unknown top-level fields. A shared envelope supplies event, run, workflow, agent, task, producer, trace, and span correlation.

### Conformance suite

Valid and invalid fixtures exercise each family, privacy rejection, missing measurements, and malformed trace context. The runner resolves schemas from an offline registry and never retrieves remote schema URLs.

### Python reference SDK

The SDK validates an event before any projection. Under the default profile it rejects known content fields and all extension attributes unless each key is explicitly allowlisted.

If OpenTelemetry is installed, the SDK uses the caller's current span and adds a normalized span event. It does not create a tracer provider, processor, exporter, or duplicate agent/tool/model span.

A caller-owned structured-log emitter may receive a defensive deep copy of the validated event. Projection failures are reported independently in `EmitResult`.

## Correlation semantics

- `run_id` is the durable execution correlation key.
- `trace_id` and `span_id` are optional lowercase W3C identifiers.
- When an active span exists, supplied IDs must match it.
- Without an active span, the SDK never fabricates context; logs remain correlated by `run_id`.
- Synchronous cross-process work will use remote-parent continuation.
- Asynchronous handoff/fan-in will use OTel span links and explicit agent delegation metadata.

The propagation helpers in the last two points are designed but not implemented in this revision.

## Delivery semantics

Operational OTel signals are best effort and may be sampled or dropped. Future evidence accumulation will occur before OTel sampling through an explicit durability callback. A TRACE record must never be reconstructed from an observability backend while claiming completeness.

## Dependency boundary

- Core runtime: JSON Schema validation and standard library.
- OTel integration: optional `opentelemetry-api`, caller configured.
- Test integration: `opentelemetry-sdk` only.
- No dependency on AGT, an agent framework, collector, backend, or TRACE package in core.

## Version axes

Contract, SDK, OpenTelemetry semantic-convention profile, and TRACE schema versions evolve independently. Releases must state the supported combination and include golden fixtures for wire behavior.
