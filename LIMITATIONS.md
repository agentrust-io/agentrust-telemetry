# Limitations

Current `0.1.0-alpha.3` limitations:

- The contract and SDK are experimental and may change incompatibly.
- A Python reference SDK and a TypeScript reference SDK (`packages/typescript/`)
  exist, with shared-schema and golden-event parity; no other language binding
  exists yet.
- OTel span events, Logs, and basic metrics are implemented against caller-owned
  providers; collector/backend interoperability is not yet exercised.
- No factory helper emits `approval.cancelled`, the `approval.execution_*`
  outcomes, or the `evidence.*` lifecycle events; these event types exist in
  the schema but nothing in either SDK produces them yet.
- TRACE finalization is software-only and requires explicitly complete evidence
  plus trusted caller configuration.
- Action telemetry records resolved attempts only; it does not expose in-flight
  lifecycle transitions.
- Evidence memory mode is not durable. Callback mode defines acknowledgement and
  retry behavior but the adopter owns storage, idempotency, and recovery.
- Propagation currently supports mutable string mappings; framework-specific HTTP,
  RPC, and messaging carrier adapters are not yet included.
- The SDK validates declared metadata but cannot prove a producer's policy decision, identity, classification, token count, or cost is truthful.
- Operational OTel delivery may be sampled or dropped and is not durable audit evidence.
- The current schemas do not provide a general content-capture profile.
- Interoperability has been exercised locally with OpenTelemetry Python, not across collectors, backends, or languages.
