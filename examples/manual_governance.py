"""Emit a synthetic policy event without configuring a telemetry backend."""

from __future__ import annotations

import time
import uuid

from agentrust_telemetry import SchemaValidator, TelemetryClient


class PrintLogEmitter:
    def emit(self, record):
        print(record)


event = {
    "spec_version": "0.1.0-dev",
    "event_id": str(uuid.uuid4()),
    "event_type": "policy.decision",
    "time_unix_nano": str(time.time_ns()),
    "run_id": "run-example-001",
    "agent_id": "spiffe://example.test/agent/reviewer",
    "producer": {"name": "manual-example", "version": "0.1.0"},
    "decision": "allow",
    "policy": {"engine": "example", "engine_version": "1"},
    "action_type": "document.review",
    "resource_type": "document",
    "enforcement_mode": "enforce",
    "evaluation_duration_ns": 1000,
}

client = TelemetryClient(SchemaValidator.bundled(), log_emitter=PrintLogEmitter())
print(client.emit(event))
