# Acceptance Before Export: A Bounded Evidence Contract for Governance Telemetry

Technical report, version 3, October 1, 2026. Not peer reviewed. Patent Pending.
Version 3 adds the pinned revision's TRACE finalizer defect, which the paper's truncation
argument depends on, and the Internet-Draft that already chains agent audit records over RFC 8785
bytes. Results are unchanged.

Build: `cd telemetry-evidence-acceptance && tectonic paper.tex` (prepared with Tectonic 0.16.9; set
SOURCE_DATE_EPOCH=1790812800 to reproduce the published PDF byte for byte). The fonts and their OFL
licenses are in `_paper-assets/fonts/`, the same relative path the manuscript uses.

Paper text is licensed CC BY 4.0: https://creativecommons.org/licenses/by/4.0/
Project code retains its existing project license; see https://github.com/agentrust-io/agentrust-telemetry.

This package contains the manuscript source, the experiment scripts and the records of the
September 27 and October 1, 2026 reruns. The evaluated code is agentrust-telemetry commit
29c13cfa4047a0f5784a90df63b22a3568453158 (0.1.0-alpha.2): 111 Python unit tests passed and all
13 portable fixtures produced their expected verdicts on both dates. The October 1 README points
to TypeScript and finalizer records kept with the AgenTrust Telemetry report's source package
(https://agentrust-io.com/research/agentrust-telemetry/). No durable store, crash-restart,
multi-process or deployed-exporter experiment was run.
Current implementation guidance: https://agentrust-io.com/telemetry/
