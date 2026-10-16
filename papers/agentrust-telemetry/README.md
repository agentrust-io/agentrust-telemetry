# From Agent Observability to Governance Evidence: A Privacy-Constrained Telemetry Contract

Technical report, version 2, October 1, 2026. Not peer reviewed. Patent Pending.
Version 2 corrects the statement that approval digests prevent an approval from being attached to
another action, which the reference finalizer does not check, and restores the bold type that
the version 1 build dropped. Results are unchanged.

Build: `tectonic paper.tex` (prepared with Tectonic 0.16.9; set SOURCE_DATE_EPOCH=1790812800
to reproduce the published PDF byte for byte).

Paper text is licensed CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
Project code retains its existing project license; see https://github.com/agentrust-io/agentrust-telemetry.

This package contains the manuscript source and the rerun records. The evaluated code is
agentrust-telemetry 0.1.0-alpha.2, commit 29c13cfa4047a0f5784a90df63b22a3568453158.
`experiments/results/rerun-2026-09-27.txt` records the September 27 rerun and
`experiments/results/rerun-2026-10-01/` the October 1 audit rerun at that commit, a later
revision and main, with the probe scripts it used. It is not an independently replicated
reproduction package.
Current implementation guidance: https://agentrust-io.com/telemetry/
