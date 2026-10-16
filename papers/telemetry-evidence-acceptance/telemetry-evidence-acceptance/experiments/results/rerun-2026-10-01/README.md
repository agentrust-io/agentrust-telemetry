# October 1, 2026 rerun

Fresh virtual environment, Python 3.12.10 on Windows 11, with the package versions recorded in
`pinned/results.json` (the same set as the September 27 rerun: cryptography 50.0.0,
jsonschema 4.26.0, cbor2 5.9.0, agentrust-trace 0.9.0, opentelemetry-sdk 1.44.0).

- `pinned/`: `reproduce.py --prepare-from` against fresh clones, so every source is a
  `git archive` extract of its pin with the tar commit id checked, then `boundary_probes.py`.
  agentrust-telemetry 111 tests OK; 13 of 13 fixtures; memory tests 35 passed; approval tests
  74 passed. The four telemetry logs match the September 27 logs except for timings. All
  eleven probes match September 27.
- `later-revision/`: `boundary_probes.py` against the commits in
  `../rerun-2026-09-27/later-revision/COMMITS.txt`. All eleven probes match September 27.
- `current-main/`: `boundary_probes.py` against origin/main on October 1 (agentrust-telemetry
  c86753cad6bbe9f00c5080489a12e0f94df34899, weight-custody-manifest
  5ef8c122479f5df79ad8a7c04b70f4a43bbdb313, agent-manifest
  fed9aeb091e4c77e0b40e12e959bee30b52e3c75). The four telemetry probes this paper relies on
  give the same result as at the pin.

Also checked on October 1 and recorded in
`../../../agentrust-telemetry/experiments/results/rerun-2026-10-01/`: the TypeScript suite at
the pin (41 of 41 pass), and the TRACE finalizer defect fixed in agentrust-telemetry PR 65
(the pinned Python and TypeScript finalizers sign an edited, truncated or digest-substituted
snapshot).
