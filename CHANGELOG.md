# Changelog

## Unreleased

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
