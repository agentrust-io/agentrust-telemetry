# OpenTelemetry GenAI compatibility

Status: pinned compatibility assessment for AgentTrust contract `0.1.0-dev`.

The machine-readable matrix is [`compatibility/otel-genai.json`](../compatibility/otel-genai.json).
It is pinned to OpenTelemetry's dedicated GenAI semantic-conventions repository
at commit `a685613a207a580163353b8e48a7ad88967e7b42` (2026-08-15).
Those conventions are in Development status. At the pinned revision the upstream
schema URL is still unpublished, so AgentTrust does not advertise one.

Primary upstream references:

- [Pinned GenAI repository revision](https://github.com/open-telemetry/semantic-conventions-genai/tree/a685613a207a580163353b8e48a7ad88967e7b42)
- [GenAI agent spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/a685613a207a580163353b8e48a7ad88967e7b42/docs/gen-ai/gen-ai-agent-spans.md)
- [GenAI model spans](https://github.com/open-telemetry/semantic-conventions-genai/blob/a685613a207a580163353b8e48a7ad88967e7b42/docs/gen-ai/gen-ai-spans.md)
- [GenAI metrics](https://github.com/open-telemetry/semantic-conventions-genai/blob/a685613a207a580163353b8e48a7ad88967e7b42/docs/gen-ai/gen-ai-metrics.md)
- [GenAI events](https://github.com/open-telemetry/semantic-conventions-genai/blob/a685613a207a580163353b8e48a7ad88967e7b42/docs/gen-ai/gen-ai-events.md)

## Compatibility meanings

- `exact`: the same field has the same semantics, subject to its stated precondition.
- `extension`: AgentTrust adds a governance or evidence concept OTel does not define.
- `complementary`: both signals may describe the same operation from different layers.
- `non_equivalent`: names or subject matter overlap, but substitution would be incorrect.
- `deferred`: OTel owns the signal or it conflicts with the metadata-only profile.

AgentTrust currently has one exact GenAI attribute mapping: a stable `agent_id` may
project to `gen_ai.agent.id`. It does not use that attribute for a transient process
instance. W3C trace and span context is also native rather than an AgentTrust extension.

The `agentrust.usage.tokens` Counter is deliberately **not** represented as
`gen_ai.client.token.usage`. The pinned OTel convention defines a per-operation
Histogram with `input` and `output` token types. AgentTrust records additive,
attribution-scoped facts and also distinguishes cache and reasoning categories.
Applications should retain their existing GenAI instrumentation and use AgentTrust
events for governance attribution.

Likewise, `action.executed` does not replace `gen_ai.execute_tool` spans: it includes
denied attempts and MCP, A2A, file, HTTP, and database actions. A successful tool action
can correlate with the application's tool span through the active trace context.

## Drift gate

`python tools/check_otel_compatibility.py` parses the shipped projection and metric
instrument definitions and fails if the matrix omits or misstates one. It also checks
the complete normalized event-family set and the pinned upstream metadata. Updating
the upstream commit is a reviewed compatibility decision, not an automatic network
operation in CI.
