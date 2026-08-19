# Releasing

Releases publish the Python and TypeScript SDKs from one GitHub release event.
Do not build or upload either package from a maintainer workstation.

## One-time registry setup

Create protected GitHub environments named `pypi` and `npm`, each with a
required maintainer review and deployment restricted to protected tags.

Configure PyPI pending trusted publishing with:

- project: `agentrust-telemetry`
- owner/repository: `agentrust-io/agentrust-telemetry`
- workflow: `release.yml`
- environment: `pypi`

Configure the npm trusted publisher for `@agentrust/telemetry` with:

- organization/repository: `agentrust-io/agentrust-telemetry`
- workflow: `release.yml`
- environment: `npm`
- allowed action: `npm publish`

The npm package must be owned by the AgentTrust npm organization before its
trusted publisher can be configured. If npm does not expose publisher settings
until the first version exists, bootstrap only that first package ownership
using npm's interactive 2FA flow, then configure trusted publishing before any
subsequent release. Never store an npm publish token in GitHub.

## Release procedure

1. Move the changelog entries from `Unreleased` into the new dated version.
2. Update `spec/VERSION`; the Python and npm spellings are checked by
   `tools/check_versions.py`.
3. Run the complete CI and artifact smoke tests through a pull request.
4. Merge the release-preparation pull request to `main`.
5. Create a GitHub prerelease or release targeting `main`, with tag
   `v<contract-version>`.
6. Approve the `pypi` and `npm` deployment jobs after inspecting their exact
   source commit and built artifacts.
7. Confirm both registry versions, GitHub release assets, and provenance before
   announcing the release.

The workflow fails closed if the tag differs from the contract version. It
builds each distribution once, sends the same artifacts to the registries, and
attaches them to the GitHub release. PyPI and npm create registry provenance
through trusted publishing; GitHub also attests the downloadable release assets.
