# AgenTrust Telemetry

Community updates and contributor highlights: [AgenTrust on LinkedIn](https://www.linkedin.com/company/agentrust-io/).

AgenTrust Telemetry is a shared format for the governance facts an AI agent produces while it runs: which rule allowed or blocked an action, who approved it, how many tokens and how much money it used, what kind of data moved where, and what the agent actually did. It is for teams that build or run agents and want those facts in one consistent, checkable form instead of scattered across separate logs. You get JSON schemas, test fixtures, and Python and TypeScript libraries that attach these facts to the OpenTelemetry traces your application already produces (OpenTelemetry is the common open standard for application traces, logs and metrics).

In technical terms, this repository defines a backend-neutral contract, a fixed set of event formats that works with any monitoring or storage system, for policy decisions, approval lifecycles, usage, classified data flows, and evidence lifecycle events. It works alongside OpenTelemetry. It is not a tracing backend, policy engine, agent framework, or dashboard.

> **Status:** alpha contract `0.1.0-alpha.6`. No stable SDK API or compatibility guarantee exists yet.

## Why

Agent applications can already record their model and tool calls as traces. The governance facts usually live somewhere else: in policy-engine logs, approval databases, cost modules and vendor dashboards. AgenTrust Telemetry puts those facts into one format that leaves out private content such as prompts, outputs and credentials, and links each fact to the OpenTelemetry trace the application already produces.

You keep your own collector, backend, policy engine, workflow framework and UI.

## Event families

Every event belongs to one of six families.

| Family | What it records |
|---|---|
| Policy decision | Whether a rule allowed, denied or challenged an action (or failed with an error), the enforcement mode, which policy decided, and how long it took |
| Approval lifecycle | A human approval from request to final decision and what happened next, tied to a digest (a fingerprint) of the exact action |
| Usage | Tokens and cost per call or per run, with where each cost figure came from |
| Data flow | What kind of data moved from which source to which destination, without copying the data itself |
| Action execution | Each attempted tool, MCP, A2A, file, HTTP or database action and how it ended |
| Evidence lifecycle | Checkpoints for a run, whether its record is complete, and the status of an optional TRACE receipt |

## Current contents

- JSON Schema 2020-12 event contracts in `spec/schema/`.
- Valid and invalid conformance fixtures (sample events the schemas must accept or reject) in `conformance/fixtures/`.
- An independent Python conformance runner in `conformance/runner/`.
- Contract tests in `tests/`.

## Validate fixtures

```shell
python -m pip install -r conformance/requirements.txt
python conformance/runner/validate.py
python -m unittest discover -s tests -v
```

The validator checks that each event matches its schema and carries metadata only, never private content. It does not yet check the OpenTelemetry (OTLP) output or the TRACE mapping.

## Python reference SDK

Install from a checkout while the project is pre-release:

```shell
python -m pip install -e ".[otel]"
```

```python
from agentrust_telemetry import SchemaValidator, TelemetryClient

client = TelemetryClient(SchemaValidator.bundled())
result = client.emit(normalized_event)
```

When `opentelemetry-api` is installed, the SDK attaches each event to the OpenTelemetry span (one timed step in a trace) that is active when you call it. It never installs a provider or exporter, so your existing OpenTelemetry setup stays in charge. You can also pass in your own structured-log emitter.

When one agent calls another in a different process and waits for the answer,
pass along the caller's W3C trace context and the AgenTrust run and agent IDs,
then use the extracted context as the parent of the receiving span:

```python
from agentrust_telemetry import extract_context, inject_context

carrier = {}
inject_context(carrier, run_id="run-123", agent_id="planner")

remote = extract_context(carrier)
with tracer.start_as_current_span("worker", context=remote.otel_context):
    event.update(remote.event_fields(agent_id="worker"))
```

When work goes through a queue instead, start a new trace with
`links=[remote.link()]`. The two traces stay connected, and the queued work is
not shown as a direct child step. Treat propagated metadata as untrusted input:
it does not prove who an agent is or what it is allowed to do.

Run the synthetic example:

```shell
python examples/manual_governance.py
```

## TypeScript reference SDK

The pre-alpha Node package lives in `packages/typescript`:

```shell
cd packages/typescript
npm ci
npm run check
```

It validates the same fixtures and privacy rules as the Python SDK and keeps
nanosecond timestamps as decimal strings, so no precision is lost. It does not
install an OpenTelemetry provider, exporter, or global propagator.

To see the whole path in one run, use the reference workflow. It takes
AGT-compatible governance events, writes them to OpenTelemetry, keeps a durable
evidence chain, and finishes with a signed TRACE record (Python 3.11+ with test
extras installed):

```shell
python -m pip install -e ".[test]"
python examples/governed_workflow.py
```

## Contract principles

- `run_id` ties together everything from one agent run and is kept for the long term; `trace_id` is an optional W3C trace ID for day-to-day operations.
- Where a standard OpenTelemetry field exists, it takes precedence over an AgenTrust extension.
- Raw prompts, output, source code, tool arguments/results, credentials, and authorization tokens are prohibited in the metadata-only profile.
- Operational telemetry can lose data; evidence completeness must never be overstated.
- An event reports something that was observed elsewhere. This project does not decide what is authorized.

## Architecture and project policy

- [Architecture](docs/architecture.md)
- [OpenTelemetry projection](docs/otel-projection.md)
- [OpenTelemetry GenAI compatibility](docs/otel-genai-compatibility.md)
- [Action execution events](docs/action-events.md)
- [Data-flow classification](docs/data-flow-classification.md)
- [Usage and cost attribution](docs/usage-attribution.md)
- [Event factories and policy adapters](docs/adapters.md)
- [Evidence chain profile](docs/evidence-chain.md)
- [TRACE finalization](docs/trace-finalization.md)
- [Privacy](PRIVACY.md)
- [Limitations](LIMITATIONS.md)
- [Roadmap](ROADMAP.md)
- [Security](SECURITY.md)
- [Governance](GOVERNANCE.md)
- [Sponsors](SPONSORS.md)
- [Releasing](RELEASING.md)
- [Contributing](CONTRIBUTING.md)

## What this project does not provide

- A telemetry collector, storage service, dashboard, or SaaS backend.
- Agent/model auto-instrumentation that duplicates OpenTelemetry GenAI or OpenInference.
- Policy evaluation or human-approval workflow execution.
- A model pricing catalog.
- A claim that sampled operational telemetry is durable audit evidence.

## License

MIT. See `LICENSE`.
