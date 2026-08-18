# Versioning

The telemetry contract uses semantic versioning independently from SDK versions, OpenTelemetry semantic-convention versions, and TRACE versions.

- Patch: clarification or fixture change with no wire behavior change.
- Minor: backward-compatible optional field, event, or enum addition with defined older-consumer behavior.
- Major: removal, changed meaning, new required field, or incompatible canonicalization.

The current contract version is `0.1.0-dev`. Pre-1.0 changes may be incompatible and must be called out explicitly.
