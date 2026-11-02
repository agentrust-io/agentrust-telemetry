# Collector fault harness

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

## Assertions validated on an Ubuntu CI host

For both SDKs: healthy delivery, first-response 503, commit then lost ACK, partial
rejection, duplicate event ID, and collector idle restart. SQLite stores local
evidence, observed requests, and committed rows separately. The synthetic backend
uses a unique constraint for idempotency; the test must not be interpreted as a
collector exactly-once guarantee. Retry observations cover the whole pipeline,
not a unique attribution to collector retry versus exporter retry. The restart
case restarts an idle collector before emission; it does not test in-flight recovery.
In these twelve baseline cases queues are disabled and assertions compare row counts.
The eight stress cases below add queue pressure, reordering and full projection checks.

## Validation and local host limitation

Python compilation, JavaScript syntax, dependency installation, and the repository
TypeScript build succeeded. The downloaded archive matched the release digest and
`otelcol components` succeeded. The host then failed before receiver startup:

```
Error: failed to register process metrics: process does not exist
```

Setting `service.telemetry.metrics.level: none` did not bypass the error. Upstream
collector v0.163.0 `service/service.go` calls `registerProcessMetrics` on Linux
regardless of that setting; `service/internal/proctelemetry/process_telemetry.go`
initializes gopsutil with `os.Getpid()`. No collector delivery case passed on the local sandbox host. The supported Ubuntu
CI run below completed all twelve cases after correcting the SDK v3 processor
constructor. No production endpoint or separately provisioned cloud resource was used.

## Recorded supported-host run

[Run 39665288508](https://github.com/agentrust-io/agentrust-telemetry/actions/runs/39665288508),
head `42fa91f0194741a1a1c7102d08142e7925fc86cb`, Ubuntu 24.04,
Python 3.12.15 and Node 22.23.3: all twelve cases passed. For both languages:

| Case | Local evidence rows | Observed attempts | Backend commits |
| --- | ---: | ---: | ---: |
| Healthy | 1 | 1 | 1 |
| First 503 | 1 | 2 | 1 |
| Lost acknowledgement | 1 | 2 | 1 |
| Partial rejection | 1 | 1 | 0 |
| Duplicate event | 2 | 2 | 1 |
| Idle restart | 1 | 1 | 1 |

The run retains configs, collector/emitter logs, synthetic inputs, SQLite observer
and per-case summary in the `collector-experiment-evidence` artifact. These
measurements establish the listed synthetic pipeline behaviors only.

## Added stress and fidelity checks (new head)

`stress.py` adds four cases for each SDK: an eight-event healthy queue control,
an eight-event blocked-consumer/one-slot queue saturation case, a collector kill
between backend commit and acknowledgement followed by a fresh post-restart event,
and three events emitted with descending source timestamps. The sending queue is
in memory; this does not claim persistent queue recovery. The receiver retains
complete normalized bodies, event names and nanosecond timestamps in SQLite.
Every observed body is compared to its submitted event, and every non-saturation
case must account for all committed event IDs. Saturation requires both positive
commits and independently observed loss relative to local evidence.

The TypeScript experiment emitter now passes the normalized event timestamp to
the OTel SDK as an integer seconds/nanoseconds pair. This is experiment wiring,
not a change to the reference SDK or a claim about all exporters/backends.

Six local observer tests catch changed nested fields, numeric type changes,
wrong event names/timestamps, missing observations, dropped local evidence,
a non-descending input control and a vacuous saturation result. The pinned collector validates
the generated configuration. Local collector startup still fails at process
metrics registration before any delivery case. The supported-host run below
validates the added cases; the twelve-case historical run above remains evidence
only for its original head.

## Recorded stress run

[Run 40204045774](https://github.com/agentrust-io/agentrust-telemetry/actions/runs/40204045774),
code head `02d5c64572ee8341f3a4d54c10e8a400a51d76f8`, Ubuntu,
Python 3.12.15: all twelve baseline cases, six observer unit tests, and all eight
stress cases passed. Each language produced the same counts:

| Case | Local evidence | Observed attempts | Backend commits |
| --- | ---: | ---: | ---: |
| Healthy queue | 8 | 8 | 8 |
| Saturation | 8 | 1 | 1 |
| In-flight restart | 2 | 2 | 2 |
| Reversed timestamp input | 3 | 3 | 3 |

Every observed stress record retained its complete normalized body, event name
and nanosecond timestamp. Saturation waits for the seeded request to reach the
blocked receiver before submitting pressure. Collector 0.163.2 counts that
in-flight request against this one-slot queue capacity, so the seeded event alone
committed; the runner also requires the Collector's explicit queue-full log.
These are observed counts for this run, not universal retry/delivery guarantees.

The first two stress workflow attempts exposed harness assumptions about consumer
scheduling and queue capacity. Both were corrected before the successful run.
The artifact includes full inputs, configs, Collector/emitter logs, SQLite
observations and both summary files. No runtime delivery policy was changed.

## Transport-order control correction

The documentation confirmation run 40204226853 observed all three TypeScript
reversed-input events with intact bodies/timestamps, but their concurrent HTTP
exports arrived in reverse order of emission. The original arrival-order
assertion was too strong and failed. The corrected harness verifies descending
input timestamps, the exact input event-ID sequence in local evidence, complete
backend delivery and per-event projection fidelity. It records submitted and
observed event-ID sequences separately, allowing transport reordering and
retries. It does not claim an SDK or Collector arrival-order guarantee. The
recorded twenty-case run above predates this observer correction.

[Run 40204492721](https://github.com/agentrust-io/agentrust-telemetry/actions/runs/40204492721)
confirmed the corrected observer contract on code head
`3cf135ad1698d9157e99ff1396e8c1665bb0b4a3`: all twelve baseline cases,
six observer unit tests and all eight stress cases passed on Ubuntu. This
records evidence for that code head; this documentation update adds no new
execution result. In the baseline `lost_ack` case, the receiver commits before
dropping the acknowledgement, then a retry of the same event identity yields
one backend commit across multiple attempts. That is synthetic backend
deduplication, not an exactly-once Collector guarantee. The stress
`inflight_restart` case commits before acknowledgement, kills the Collector,
and emits a different event after restart; it does not replay the unacknowledged
identity or establish persistent queue recovery.
