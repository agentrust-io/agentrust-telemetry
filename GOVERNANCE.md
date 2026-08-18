# Governance

AgentTrust Telemetry is governed under the AgentTrust organization. Maintainers approve releases, normative contract changes, security-sensitive changes, and compatibility claims.

## Decision process

- Routine fixes require maintainer review and passing required checks.
- Contract changes require an ADR or equivalent design record, valid and invalid fixtures, and conformance coverage.
- Breaking changes require migration notes and a major contract version change, including during pre-1.0 development when practical.
- Security and privacy defaults require explicit maintainer approval.
- Widely applicable telemetry conventions should be proposed upstream to OpenTelemetry rather than permanently duplicated here.

Consensus is preferred. If consensus cannot be reached, maintainers record the decision and dissent in the relevant issue or ADR.

## Releases

Releases are cut from protected `main`, use signed tags where available, and publish provenance and an SBOM. Publishing credentials must use GitHub trusted publishing or another short-lived identity mechanism; long-lived package tokens are prohibited.
