"""Concrete adapters for caller-owned OpenTelemetry Logs and Metrics APIs."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from .projection import span_attributes


class OTelLogEmitter:
    """Emit normalized events through a caller-provided OTel Logger."""

    def __init__(self, logger: Any) -> None:
        if not callable(getattr(logger, "emit", None)):
            raise TypeError("logger must provide emit()")
        self._logger = logger

    def emit(self, record: dict[str, Any]) -> None:
        event = record["body"]
        self._logger.emit(
            timestamp=record["timestamp_ns"],
            event_name=record["event_name"],
            body=deepcopy(event),
            attributes=span_attributes(event),
        )


class OTelMetricEmitter:
    """Project normalized events into bounded-cardinality OTel instruments."""

    def __init__(
        self,
        meter: Any,
        *,
        classification_values: frozenset[str] = frozenset(),
    ) -> None:
        if len(classification_values) > 64:
            raise ValueError("classification_values cannot contain more than 64 entries")
        if any(not value or len(value) > 128 for value in classification_values):
            raise ValueError("classification_values must be non-empty and at most 128 characters")
        self._classification_values = classification_values
        self._policy_count = meter.create_counter(
            "agentrust.policy.decisions", unit="{decision}", description="Policy decisions"
        )
        self._policy_duration = meter.create_histogram(
            "agentrust.policy.evaluation.duration",
            unit="s",
            description="Policy evaluation duration",
        )
        self._approval_count = meter.create_counter(
            "agentrust.approval.events", unit="{event}", description="Approval lifecycle events"
        )
        self._action_count = meter.create_counter(
            "agentrust.action.executions", unit="{execution}", description="Resolved action attempts"
        )
        self._action_duration = meter.create_histogram(
            "agentrust.action.duration", unit="s", description="Resolved action duration"
        )
        self._data_flow_count = meter.create_counter(
            "agentrust.data_flow.events", unit="{event}", description="Classified data-flow events"
        )
        self._token_count = meter.create_counter(
            "agentrust.usage.tokens", unit="{token}", description="Reported token usage"
        )
        self._cost = meter.create_counter(
            "agentrust.usage.cost", unit="1", description="Reported cost in the currency attribute"
        )

    def emit(self, event: dict[str, Any]) -> bool:
        event_type = event["event_type"]
        if event_type == "policy.decision":
            attributes = {
                "agentrust.policy.decision": event["decision"],
                "agentrust.policy.enforcement_mode": event["enforcement_mode"],
            }
            self._policy_count.add(1, attributes)
            self._policy_duration.record(event["evaluation_duration_ns"] / 1_000_000_000, attributes)
            return True
        if event_type.startswith("approval."):
            self._approval_count.add(
                1,
                {
                    "agentrust.approval.phase": event_type.removeprefix("approval."),
                    "agentrust.approval.actor_type": event["actor_type"],
                },
            )
            return True
        if event_type == "action.executed":
            attributes = {
                "agentrust.action.kind": event["action_kind"],
                "agentrust.action.outcome": event["outcome"],
            }
            self._action_count.add(1, attributes)
            self._action_duration.record(event["duration_ns"] / 1_000_000_000, attributes)
            return True
        if event_type == "data_flow.observed":
            value = event["classification"]["value"]
            classification = value if value in self._classification_values else "_other"
            self._data_flow_count.add(
                1,
                {
                    "agentrust.data_flow.direction": event["direction"],
                    "agentrust.data_flow.policy_decision": event["policy_decision"],
                    "agentrust.data_flow.classification": classification,
                    "agentrust.data_flow.transformation": event.get("transformation", "none"),
                },
            )
            return True
        if event_type == "usage.recorded":
            base = {"agentrust.usage.scope": event["scope"]}
            token_fields = {
                "input_tokens": "input",
                "output_tokens": "output",
                "cache_read_tokens": "cache_read",
                "cache_write_tokens": "cache_write",
                "reasoning_tokens": "reasoning",
            }
            for field, token_type in token_fields.items():
                if field in event:
                    self._token_count.add(
                        event[field], {**base, "gen_ai.token.type": token_type}
                    )
            if "cost" in event:
                cost = event["cost"]
                self._cost.add(
                    cost["amount"],
                    {
                        **base,
                        "agentrust.cost.currency": cost["currency"],
                        "agentrust.cost.source": cost["source"],
                    },
                )
            return True
        return False
