# Changelog

## Unreleased

## 0.1.0-alpha.1 - 2026-08-19

- Add TypeScript TRACE finalization through a caller-supplied official codec and
  standardize tool-transcript hashing on RFC 8785 JCS across both SDKs.
- Add TypeScript metadata-only data-flow primitives plus AGT data-access,
  audit-policy, and completed-action adapters.
- Enforce the documented no-URL metadata identifier boundary in both SDKs.
- Add TypeScript action-bound AGT policy, approval-request, and terminal
  approval-resolution adapters with deterministic cross-language linkage.
- Require every AGT approval binding field to be present before comparing it,
  preventing two absent values from being treated as a valid binding.
- Add TypeScript OPA, Cedar, and generic AGT policy-decision adapters plus an
  AGT-compatible fail-closed batch sink.
- Add TypeScript usage/cost construction, coverage-labelled rollups, and
  bounded-cardinality OpenTelemetry metric projection.
- Add a TypeScript evidence accumulator and adopt RFC 8785 JCS for reproducible
  evidence digests across Python and TypeScript.
- Encode nanosecond Unix timestamps as canonical decimal strings for exact
  cross-language JSON behavior.
- Add the pre-alpha TypeScript reference SDK and shared conformance gates.

- Initial `0.1.0-dev` event contract and conformance fixtures.
- Initial Python reference SDK with schema/privacy validation and OTel span-event projection.
