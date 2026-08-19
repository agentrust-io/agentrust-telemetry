# AgentTrust Telemetry

Portable governance telemetry and verifiable evidence for AI-agent runtimes.

This repository defines a backend-neutral contract for policy decisions, approval lifecycles, usage, classified data flows, and evidence lifecycle events. It composes with OpenTelemetry; it is not a tracing backend, policy engine, agent framework, or dashboard.

> **Status:** alpha contract `0.1.0-alpha.1`. No stable SDK API or compatibility guarantee exists yet.

## Why

Agent applications can already emit model and tool traces, but governance facts are often trapped in policy-engine logs, approval databases, cost modules, and proprietary dashboards. AgentTrust Telemetry gives those facts one privacy-conscious contract and correlates them with the OpenTelemetry trace already produced by the application.

The application keeps its collector, backend, policy engine, workflow framework, and UI.

## Event families

| Family | Purpose |
|---|---|
| Policy decision | Allow, deny, challenge, error, enforcement mode, policy identity and timing |
| Approval lifecycle | Requested through terminal decision and execution outcome, bound to an action digest |
| Usage | Per-call/run token and cost facts with explicit cost provenance |
| Data flow | Classified source-to-destination metadata without payload capture |
| Action execution | Resolved tool, MCP, A2A, file, HTTP, and database attempts |
| Evidence lifecycle | Run checkpoints, completeness, and optional TRACE finalization status |

## Current contents

- JSON Schema 2020-12 event contracts in `spec/schema/`.
- Valid and invalid conformance fixtures in `conformance/fixtures/`.
- An independent Python conformance runner in `conformance/runner/`.
- Contract tests in `tests/`.

## Validate fixtures

```shell
python -m pip install -r conformance/requirements.txt
python conformance/runner/validate.py
python -m unittest discover -s tests -v
```

The validator checks schema conformance and the metadata-only privacy invariant. It does not yet validate OTLP projection or TRACE mapping.

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

The SDK uses the caller's current OpenTelemetry span when `opentelemetry-api` is installed. It never installs a provider or exporter. A caller may additionally supply a structured-log emitter.

For synchronous cross-process agent calls, propagate the caller's W3C context and
durable AgenTrust identifiers, then use the extracted context as the receiving
span's remote parent:

```python
from agentrust_telemetry import extract_context, inject_context

carrier = {}
inject_context(carrier, run_id="run-123", agent_id="planner")

remote = extract_context(carrier)
with tracer.start_as_current_span("worker", context=remote.otel_context):
    event.update(remote.event_fields(agent_id="worker"))
```

For asynchronous queue handoffs, start a new trace with
`links=[remote.link()]`. This preserves causality without representing queued
work as a synchronous child span. Propagated metadata is untrusted input and
does not establish agent identity or authorization.

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

It validates the same fixtures and privacy profile as Python and preserves
nanosecond wire timestamps as decimal strings. It does not install an OTel
provider, exporter, or global propagator.

Run the complete AGT-compatible governance, OTel, durable-evidence, and TRACE
reference workflow (Python 3.11+ with test extras installed):

```shell
python -m pip install -e ".[test]"
python examples/governed_workflow.py
```

## Contract principles

- `run_id` is durable execution correlation; `trace_id` is an optional W3C operational trace context.
- Standard OpenTelemetry fields take precedence over AgentTrust extensions.
- Raw prompts, output, source code, tool arguments/results, credentials, and authorization tokens are prohibited in the metadata-only profile.
- Operational telemetry can be lossy; evidence completeness must never be overstated.
- An event reports a fact observed elsewhere. This project does not make authorization decisions.

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
