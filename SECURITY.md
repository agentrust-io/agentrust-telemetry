# Security

# Security Policy

## Scope

Security issues include schema or validator bypasses, privacy-control bypasses, incorrect trace correlation, misleading evidence claims, exporter behavior that changes governance outcomes, package compromise, and release automation weaknesses.

## Reporting

Do not report vulnerabilities in public issues. Once the repository exists, use GitHub Security Advisories at:

`https://github.com/agentrust-io/agentrust-telemetry/security/advisories/new`

Before repository creation, report privately to the AgentTrust maintainers.

Include the affected contract/SDK version, an executable reproducer where safe, the violated invariant, and expected impact.

## Response targets

| Severity | Initial response | Fix target |
|---|---:|---:|
| Critical | 24 hours | 7 days |
| High | 48 hours | 14 days |
| Medium / Low | 5 business days | next patch |

## Supported versions

No stable release exists. Only the latest `0.1.0-dev` revision will receive fixes until the first published release.

## Runtime boundary

Telemetry is not authorization. Export failure must not turn a denied action into an allowed action. Content capture is prohibited by default, and downstream collectors remain responsible for transport security, retention, and access control.

Never use a fixture containing a real credential, token, user record, prompt, source file, or production identifier.
