"""Validated envelope construction shared by all adapters."""

from __future__ import annotations

import time
import uuid
from copy import deepcopy
from typing import Any, Callable

from ..validation import SchemaValidator


class EventFactory:
    def __init__(
        self,
        validator: SchemaValidator,
        *,
        producer_name: str,
        producer_version: str,
        producer_instance_id: str | None = None,
        clock_ns: Callable[[], int] = time.time_ns,
        event_id_factory: Callable[[], uuid.UUID] = uuid.uuid4,
    ) -> None:
        self._validator = validator
        self._producer = {
            "name": producer_name,
            "version": producer_version,
            **({"instance_id": producer_instance_id} if producer_instance_id else {}),
        }
        self._clock_ns = clock_ns
        self._event_id_factory = event_id_factory

    def build(
        self,
        event_type: str,
        *,
        run_id: str,
        agent_id: str | None = None,
        workflow_id: str | None = None,
        parent_agent_id: str | None = None,
        task_id: str | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
        event_id: str | None = None,
        time_unix_nano: int | None = None,
        **payload: Any,
    ) -> dict[str, Any]:
        reserved = {
            "spec_version", "event_id", "event_type", "time_unix_nano", "run_id",
            "producer", "agent_id", "workflow_id", "parent_agent_id", "task_id",
            "trace_id", "span_id",
        }
        collision = sorted(reserved.intersection(payload))
        if collision:
            raise ValueError(f"payload cannot override envelope fields: {collision}")
        event: dict[str, Any] = {
            "spec_version": "0.1.0-dev",
            "event_id": event_id or str(self._event_id_factory()),
            "event_type": event_type,
            "time_unix_nano": self._clock_ns() if time_unix_nano is None else time_unix_nano,
            "run_id": run_id,
            "producer": deepcopy(self._producer),
            **payload,
        }
        optional = {
            "agent_id": agent_id,
            "workflow_id": workflow_id,
            "parent_agent_id": parent_agent_id,
            "task_id": task_id,
            "trace_id": trace_id,
            "span_id": span_id,
        }
        event.update({key: value for key, value in optional.items() if value is not None})
        self._validator.validate(event)
        return event
