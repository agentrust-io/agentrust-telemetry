# `@agentrust/telemetry`

TypeScript reference SDK for the AgentTrust Telemetry `0.1.0-dev` contract.

This pre-alpha Node package validates the same closed schemas and metadata-only
privacy profile as the Python SDK. It supplies event construction, caller-owned
OpenTelemetry span/log projection, and W3C plus AgentTrust context propagation.
It never installs an OTel provider, exporter, or global propagator.

This reference surface includes a fail-closed evidence accumulator using the
same RFC 8785 digest profile as Python, conservative usage/cost rollups, and a
caller-owned bounded-cardinality OTel metric emitter. It does not yet include
the Python SDK's source adapters or TRACE finalizer. Those
remain explicit parity work rather than implied compatibility.

Nanosecond timestamps are decimal strings on the JSON wire and `bigint` at the
TypeScript construction boundary, avoiding IEEE-754 precision loss.
