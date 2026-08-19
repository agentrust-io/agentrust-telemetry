"""Validated usage facts and conservative per-agent/workflow rollups."""

from __future__ import annotations

import math
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

from .adapters import EventFactory
from .validation import SchemaValidator

TOKEN_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_read_tokens",
    "cache_write_tokens",
    "reasoning_tokens",
)


@dataclass(frozen=True)
class CostObservation:
    """A cost reported or calculated outside this package."""

    amount: int | float | Decimal
    currency: str
    source: Literal["provider", "caller", "price_resolver", "estimate"]
    pricing_version: str | None = None

    def as_event_value(self) -> dict[str, Any]:
        if isinstance(self.amount, bool):
            raise TypeError("cost amount must be a finite non-negative number")
        amount = float(self.amount)
        if not math.isfinite(amount) or amount < 0:
            raise ValueError("cost amount must be a finite non-negative number")
        if len(self.currency) != 3 or not self.currency.isascii() or not self.currency.isupper():
            raise ValueError("cost currency must be a three-letter uppercase ASCII code")
        if self.source not in {"provider", "caller", "price_resolver", "estimate"}:
            raise ValueError("cost source is not supported")
        value = {"amount": amount, "currency": self.currency, "source": self.source}
        if self.pricing_version is not None:
            if not self.pricing_version:
                raise ValueError("pricing_version must be non-empty")
            value["pricing_version"] = self.pricing_version
        return value


def usage_record(
    factory: EventFactory,
    *,
    run_id: str,
    agent_id: str,
    scope: Literal["model_call", "agent_step", "task", "agent_run", "workflow_run"],
    operation: str,
    workflow_id: str | None = None,
    parent_agent_id: str | None = None,
    task_id: str | None = None,
    provider: str | None = None,
    request_model: str | None = None,
    response_model: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    cache_read_tokens: int | None = None,
    cache_write_tokens: int | None = None,
    reasoning_tokens: int | None = None,
    cost: CostObservation | None = None,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> dict[str, Any]:
    """Build a usage event without resolving prices or interpreting missing values as zero."""

    payload: dict[str, Any] = {"scope": scope, "operation": operation}
    optional = {
        "provider": provider,
        "request_model": request_model,
        "response_model": response_model,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_read_tokens": cache_read_tokens,
        "cache_write_tokens": cache_write_tokens,
        "reasoning_tokens": reasoning_tokens,
    }
    for field in TOKEN_FIELDS:
        value = optional[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
            raise TypeError(f"{field} must be a non-negative integer")
    payload.update({key: value for key, value in optional.items() if value is not None})
    if cost is not None:
        payload["cost"] = cost.as_event_value()
    return factory.build(
        "usage.recorded",
        run_id=run_id,
        agent_id=agent_id,
        workflow_id=workflow_id,
        parent_agent_id=parent_agent_id,
        task_id=task_id,
        trace_id=trace_id,
        span_id=span_id,
        **payload,
    )


class UsageAccumulator:
    """Deduplicate leaf usage facts and produce coverage-labelled rollup events."""

    def __init__(self, validator: SchemaValidator | None = None) -> None:
        self._validator = validator or SchemaValidator.bundled()
        self._events: dict[str, dict[str, Any]] = {}

    def add(self, event: dict[str, Any]) -> bool:
        self._validator.validate(event)
        if event.get("event_type") != "usage.recorded":
            raise ValueError("only usage.recorded events can be accumulated")
        if event.get("scope") != "model_call":
            raise ValueError("only model_call leaf events can be accumulated")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            raise ValueError("usage event must have a non-empty event_id")
        for field in TOKEN_FIELDS:
            value = event.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, int)):
                raise TypeError(f"{field} must be a non-negative integer")
        if "cost" in event:
            amount = event["cost"]["amount"]
            if isinstance(amount, bool) or not isinstance(amount, (int, float)):
                raise TypeError("cost amount must be a finite non-negative number")
            if not math.isfinite(amount) or amount < 0:
                raise ValueError("cost amount must be a finite non-negative number")
        if event_id in self._events:
            if self._events[event_id] != event:
                raise ValueError("event_id was reused with different usage data")
            return False
        self._events[event_id] = deepcopy(event)
        return True

    def rollup(
        self,
        factory: EventFactory,
        *,
        scope: Literal["agent_run", "workflow_run"],
        run_id: str,
        operation: str,
        agent_id: str,
        workflow_id: str | None = None,
    ) -> dict[str, Any]:
        if scope == "workflow_run" and workflow_id is None:
            raise ValueError("workflow_id is required for workflow_run rollups")
        matches = [
            event for event in self._events.values()
            if event["run_id"] == run_id
            and (scope == "workflow_run" or event.get("agent_id") == agent_id)
            and (workflow_id is None or event.get("workflow_id") == workflow_id)
        ]
        if not matches:
            raise ValueError("no matching model_call usage events")

        payload: dict[str, Any] = {"scope": scope, "operation": operation}
        coverage: dict[str, int] = {}
        for field in TOKEN_FIELDS:
            observed = [event[field] for event in matches if field in event]
            coverage[field] = len(observed)
            if observed:
                payload[field] = sum(observed)

        costs = [event["cost"] for event in matches if "cost" in event]
        currencies = {cost["currency"] for cost in costs}
        if len(currencies) > 1:
            raise ValueError("cannot roll up costs with mixed currencies")
        if costs:
            payload["cost"] = {
                "amount": float(sum((Decimal(str(cost["amount"])) for cost in costs), Decimal())),
                "currency": next(iter(currencies)),
                "source": "aggregate",
            }
        payload["aggregation"] = {
            "method": "sum",
            "event_count": len(matches),
            "token_coverage": coverage,
            "cost_coverage": len(costs),
            "cost_sources": sorted({cost["source"] for cost in costs}),
        }
        return factory.build(
            "usage.recorded",
            run_id=run_id,
            agent_id=agent_id,
            workflow_id=workflow_id,
            **payload,
        )
