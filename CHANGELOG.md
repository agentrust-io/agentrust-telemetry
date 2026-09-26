# Changelog

## Unreleased

## 0.1.0-alpha.5 - 2026-09-26

### Fixed

- TRACE finalization in both SDKs (`finalize_trace` in `trace_adapter.py`, and
  `trace-finalizer.ts`) now recomputes the evidence chain from the snapshot entries
  (sequence, previous digest, entry digest, `event_id`, `run_id`, `chain_digest`) and
  refuses to sign on any mismatch. Before, an `EvidenceSnapshot` edited after sealing
  could produce a signed record whose appraisal disagreed with the measurement it
  carried. A malformed event inside a consistent chain now raises
  `TraceFinalizationError` instead of `KeyError`. (#65)
- Python event validation rejects nesting deeper than 32 levels, non-string keys, and
  NaN or Infinity with `EventValidationError`. These previously raised `RecursionError`
  or `AttributeError`, or were accepted. NaN now fails at validation rather than at the
  chain, as it already did in the TypeScript SDK. (#65)
- The AGT adapters (`agt.py`, `agt_audit.py`, `agt_approval.py`, `agt_data.py`) raise
  `ValueError` for a list or object where a decision, kind, outcome or classification
  belongs, and for an out-of-range `latency_ms`. These previously surfaced as
  `TypeError` or `OverflowError`. (#65)

### Changed

- Add ClusterFuzzLite with three fuzz targets: event validation and projection, the
  OPA and AGT policy adapters, and sealed evidence to signed TRACE. (#65)
- The OTel GenAI compatibility notes now say that the pinned upstream revision already
  defines cache-read, cache-creation and reasoning token attributes. (#63)
- The version string is inside the hashed envelope, so this release moves every
  evidence digest. `compatibility/golden/evidence-chain.json` and the cross-language
  `tool_transcript` assertions are regenerated for it.
- CI and governance only: CODEOWNERS maintainer alignment (#64), CodeQL and CycloneDX
  action bumps (#57, #59, #60, #61), `build` 1.6.1 in the release lock (#56).

## 0.1.0-alpha.4 - 2026-09-14

### Fixed

- `release.yml` passed the built tarball to `npm publish` as `npm-dist/*.tgz`, and npm
  parses any `a/b` argument as a GitHub shorthand rather than a path. It resolved the
  tarball's own filename as a repository and failed on `git ls-remote`, so the npm half
  of a release could never publish. The step now passes `./npm-dist/*.tgz`.

### Changed

- No SDK behaviour changes. The Python and TypeScript packages are identical to
  0.1.0-alpha.3 apart from the version string, which is inside the hashed envelope and
  therefore moves every evidence digest. `compatibility/golden/evidence-chain.json` and
  the cross-language `tool_transcript` assertions are regenerated for it.

## 0.1.0-alpha.3 - 2026-09-07

### Fixed

- The Python `EvidenceAccumulator` deadlocked forever if `append` or `seal` was
  called reentrantly on the same thread, for example from inside a
  `durable_append` callback. Both now raise `EvidenceError`, matching the
  TypeScript SDK's existing protection. `snapshot` remains safely callable
  reentrantly.
- Patch four `fast-uri` advisories in the TypeScript lockfile and stop tag
  interpolation in `release.yml`.
- `test_trace_adapter_refusals` used a duck-typed signer double, which
  `agentrust-trace` 0.10.0 rejects. It now builds a real `Ed25519PrivateKey`, so
  a clean install of this release runs the full suite against either 0.9 or
  0.10.

### Changed

- Install CI dependencies from hash-pinned lock files, and add `actionlint`
  plus a test-environment guard to the workflow gates.

## 0.1.0-alpha.2 - 2026-09-02

- Align the wire `spec_version` with `spec/VERSION`; the schema previously
  pinned a const that appeared nowhere in the packaging.
- Move the schema `$id` off `agentrust.io`, a domain we do not own, to
  `agentrust-io.com`.
- Derive the npm dist-tag from `spec/VERSION` so a prerelease can never publish
  under `latest`.

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

- Initial `0.1.0-alpha.1` event contract and conformance fixtures.
- Initial Python reference SDK with schema/privacy validation and OTel span-event projection.
