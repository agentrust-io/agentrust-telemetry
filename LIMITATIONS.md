# Limitations

Current `0.1.0-dev` limitations:

- The contract and SDK are experimental and may change incompatibly.
- Only a Python reference SDK exists.
- OTel span events are implemented; the structured-log path is an emitter protocol rather than a concrete OTel Logs adapter.
- No metrics projector, distributed propagation helper, evidence accumulator, TRACE finalizer, or AGT adapter is implemented.
- The SDK validates declared metadata but cannot prove a producer's policy decision, identity, classification, token count, or cost is truthful.
- Operational OTel delivery may be sampled or dropped and is not durable audit evidence.
- The current schemas do not provide a general content-capture profile.
- Interoperability has been exercised locally with OpenTelemetry Python, not across collectors, backends, or languages.
