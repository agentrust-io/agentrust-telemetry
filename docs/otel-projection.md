# OpenTelemetry projection profile

Status: experimental for contract `0.1.0-dev`.

The normalized JSON event is the source contract. OpenTelemetry is a projection, not an alternative event model.

## Span events

When a recording span is active, the SDK calls `add_event` with:

- name: normalized `event_type`;
- timestamp: `time_unix_nano`;
- attributes: the allowlisted flattened mapping below.

| Normalized field | OTel attribute |
|---|---|
| `spec_version` | `agentrust.telemetry.spec_version` |
| `event_id` | `agentrust.event.id` |
| `run_id` | `agentrust.run.id` |
| `workflow_id` | `agentrust.workflow.id` |
| `agent_id` | `gen_ai.agent.id` |
| `parent_agent_id` | `agentrust.agent.parent.id` |
| `task_id` | `agentrust.task.id` |
| `decision` | `agentrust.policy.decision` |
| `approval_id` | `agentrust.approval.id` |
| `scope` | `agentrust.usage.scope` |
| `direction` | `agentrust.data_flow.direction` |
| `policy_decision` | `agentrust.data_flow.policy_decision` |
| `capture_profile` | `agentrust.evidence.capture_profile` |
| `completeness` | `agentrust.evidence.completeness` |

Nested normalized objects are projected only through explicit mappings. They are never serialized wholesale into span attributes. Raw content fields are prohibited before projection.

Trace and span IDs are not duplicated as event attributes. OTel attaches them through context. If normalized IDs are supplied, the SDK verifies they match the active span and rejects a mismatch.

## Structured logs

Every accepted event may also be sent to a caller-owned log emitter. The record contains:

- `event_name`;
- `timestamp_ns`;
- the validated normalized event as `body`;
- active `trace_id` and `span_id` when available.

The SDK does not install a logger provider or exporter. Adapters may translate this projection to an OTel log record without changing the normalized body.

## No active span

An event remains valid without a span. It may be emitted as a structured log using `run_id`. The result reports `span_event_emitted=false`. The SDK never fabricates trace or span IDs.

## Failure behavior

- Schema or privacy failure: reject before all projections.
- Supplied context disagrees with active context: reject.
- Span exporter failure during `add_event`: report projection failure and do not claim emission.
- Log emitter failure: report projection failure independently.
- One projection failure does not rewrite or mutate the normalized event.
