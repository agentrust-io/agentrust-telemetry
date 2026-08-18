"""Pure normalized-event projections for spans and structured logs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .context import ContextIds


DIRECT_ATTRIBUTES = {
    "spec_version": "agentrust.telemetry.spec_version",
    "event_id": "agentrust.event.id",
    "run_id": "agentrust.run.id",
    "workflow_id": "agentrust.workflow.id",
    "agent_id": "gen_ai.agent.id",
    "parent_agent_id": "agentrust.agent.parent.id",
    "task_id": "agentrust.task.id",
    "decision": "agentrust.policy.decision",
    "approval_id": "agentrust.approval.id",
    "scope": "agentrust.usage.scope",
    "direction": "agentrust.data_flow.direction",
    "policy_decision": "agentrust.data_flow.policy_decision",
    "capture_profile": "agentrust.evidence.capture_profile",
    "completeness": "agentrust.evidence.completeness",
}


def span_attributes(event: dict[str, Any]) -> dict[str, str | int | float | bool]:
    projected: dict[str, str | int | float | bool] = {}
    for source, destination in DIRECT_ATTRIBUTES.items():
        value = event.get(source)
        if isinstance(value, (str, int, float, bool)):
            projected[destination] = value
    return projected


def log_record(event: dict[str, Any], context: ContextIds | None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "event_name": event["event_type"],
        "timestamp_ns": event["time_unix_nano"],
        "body": deepcopy(event),
    }
    if context:
        record["trace_id"] = context.trace_id
        record["span_id"] = context.span_id
    return record
