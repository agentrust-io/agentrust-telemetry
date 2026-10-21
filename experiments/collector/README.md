# Collector fault harness — host validation pending

This experimental harness wires the real Python and TypeScript telemetry SDKs
through a real OpenTelemetry Collector to a synthetic loopback receiver backed by
SQLite. It is not production delivery evidence and is not a release gate yet.

## Reproduction

Use Linux amd64, Python 3.12 and Node >=22.15. From the repository root:

```sh
uv venv --python 3.12 ../collector-env
uv pip install --python ../collector-env/bin/python -r experiments/collector/environment.txt
(cd packages/typescript && npm ci --ignore-scripts && npm run build)
(cd experiments/collector && npm ci --ignore-scripts)
PYTHONPATH=src ../collector-env/bin/python experiments/collector/run.py --collector /absolute/path/to/otelcol --output ../collector-results-new
```

Use the official core collector v0.163.2 Linux amd64 release:
https://github.com/open-telemetry/opentelemetry-collector-releases/releases/tag/v0.163.2

Archive `otelcol_0.163.2_linux_amd64.tar.gz` SHA256:
`9fbf3101331c88aab4b7f4cfd7c788b252e91e193793e39bd2154971c87f88a7`.
The runner enforces binary SHA256
`d4fa834fae73cb37e6058955a3833894d1ec815a1fc3529b0c2aaa99d8b22a2e`.
Use a fresh output directory. Clear HTTP(S)/ALL proxy environment variables for
the Python emitter if your environment exports them; child processes clear these.

## Intended assertions (not yet validated on a supported host)

For both SDKs: healthy delivery, first-response 503, commit then lost ACK, partial
rejection, duplicate event ID, and collector idle restart. SQLite stores local
evidence, observed requests, and committed rows separately. The synthetic backend
uses a unique constraint for idempotency; the test must not be interpreted as a
collector exactly-once guarantee. Retry observations cover the whole pipeline,
not a unique attribution to collector retry versus exporter retry. The restart
case restarts an idle collector before emission; it does not test in-flight recovery.
Queues are disabled; queue saturation and out-of-order delivery remain uncovered.
Only event IDs are checked at the receiver today, not full projection fidelity.

## Actual validation and blocker

Python compilation, JavaScript syntax, dependency installation, and the repository
TypeScript build succeeded. The downloaded archive matched the release digest and
`otelcol components` succeeded. The host then failed before receiver startup:

```
Error: failed to register process metrics: process does not exist
```

Setting `service.telemetry.metrics.level: none` did not bypass the error. Upstream
collector v0.163.0 `service/service.go` calls `registerProcessMetrics` on Linux
regardless of that setting; `service/internal/proctelemetry/process_telemetry.go`
initializes gopsutil with `os.Getpid()`. No collector delivery case has passed on
this host. Run this draft on a supported host and fix any discovered integration
issues before claiming acceptance. No production endpoint or cloud resource was used.
