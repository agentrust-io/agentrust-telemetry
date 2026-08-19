# Versioning

The telemetry contract uses semantic versioning independently from SDK versions, OpenTelemetry semantic-convention versions, and TRACE versions.

- Patch: clarification or fixture change with no wire behavior change.
- Minor: backward-compatible optional field, event, or enum addition with defined older-consumer behavior.
- Major: removal, changed meaning, new required field, or incompatible canonicalization.

The current contract version is `0.1.0-alpha.1`. Python publishes the equivalent
PEP 440 version `0.1.0a1`; npm and the Git tag use `0.1.0-alpha.1` and
`v0.1.0-alpha.1`. Pre-1.0 changes may be incompatible and must be called out
explicitly.
