# GitHub repository creation checklist

Verified on 2026-08-18: `agentrust-io/agentrust-telemetry` does not exist and the name is available.

PyPI also returned no matching distribution for `agentrust-telemetry` on 2026-08-18. Availability is not reservation; re-check immediately before the first publish.

## Creation parameters

- Owner: `agentrust-io`
- Name: `agentrust-telemetry`
- Visibility: public
- Default branch: `main`
- Description: `Backend-neutral governance telemetry and verifiable evidence for AI-agent runtimes.`
- Topics: `ai-agents`, `governance`, `opentelemetry`, `observability`, `telemetry`, `trace`
- Initialize remotely: no README, license, or gitignore; this repository already supplies them.

## Settings immediately after first push

- Enable private vulnerability reporting.
- Enable secret scanning and push protection where available.
- Enable Dependabot security updates.
- Enable automatic branch deletion after merge.
- Disable merge commits; allow squash merge with PR title as the default message.
- Protect `main` with pull requests, one approving review, CODEOWNER review, dismissal of stale approvals, conversation resolution, and required status checks.
- Required checks after their first run: all CI matrix jobs, CodeQL, and OpenSSF Scorecard where GitHub permits it.
- Prevent force pushes and branch deletion.
- Require signed commits if that matches organization-wide practice; do not enable until maintainers can comply.
- Configure the `pypi` environment and trusted publishing only when the package name and first release are approved.

## First push sequence

1. Review the complete staged diff and generated schema copies.
2. Run `python tools/check_versions.py`.
3. Run `python tools/check_schemas.py`.
4. Run `python conformance/runner/validate.py`.
5. Run `python -m unittest discover -s tests -v`.
6. Run `python -m build` and `python tools/smoke_wheel.py <wheel>`.
7. Create one DCO-signed initial commit.
8. Create the empty GitHub repository with the parameters above.
9. Add `origin`, push `main`, then apply the settings above.

Repository creation, initial commit, push, package-name reservation, and publishing are intentionally not performed by readiness work.
