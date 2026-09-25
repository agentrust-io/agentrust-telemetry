#!/usr/bin/python3
"""Fuzz the adapters that ingest policy decisions from other engines.

opa_decision_log reads an OPA decision-log entry and agt_policy_decision reads
an AGT governance event. Both arrive as JSON from a process this package does
not control. Each adapter documents ValueError (EventValidationError is one)
for input it refuses; a KeyError, TypeError or OverflowError reaching the
caller means a field was trusted before it was checked.

When an adapter accepts, the event it returns must pass the bundled schema
and must be deterministic in its event_id, because that id is what makes a
re-delivered source record idempotent downstream.
"""
import copy
import sys

import atheris

with atheris.instrument_imports():
    from agentrust_telemetry import (
        EventFactory,
        SchemaValidator,
        agt_policy_decision,
        opa_decision_log,
    )

    import _fuzz_build

_VALIDATOR = SchemaValidator.bundled()
_FACTORY = EventFactory(
    _VALIDATOR,
    producer_name="fuzz",
    producer_version="0",
    clock_ns=lambda: 1_787_079_600_000_000_000,
)
_BUNDLE = {"algorithm": "sha256", "value": "a" * 64}

_OPA_SEED = {
    "decision_id": "4ca636c1-55e4-417a-b1d8-4aceb67960d1",
    "path": "repo/write",
    "result": False,
    "timestamp": "2026-08-18T10:20:00.123456789Z",
    "labels": {"version": "0.68.0", "id": "opa-1"},
    "metrics": {"timer_rego_query_eval_ns": 182000},
    "ids": ["deny_protected_branch"],
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
}
_AGT_SEED = {
    "kind": "policy_violation",
    "decision": "blocked",
    "agent_id": "spiffe://example.test/agent/coder",
    "action": "repository.write",
    "event_id": "018f0f7d-7a13-7cc2-8000-000000000001",
    "occurred_at": "2026-08-18T10:20:00.5+00:00",
    "latency_ms": 0.182,
    "policy_name": "repo-write",
    "attributes": {"resource_type": "git.repository", "reason_codes": ["BRANCH_PROTECTED"]},
    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    "span_id": "00f067aa0ba902b7",
}


def _opa(source):
    return opa_decision_log(
        _FACTORY,
        source,
        run_id="run-fuzz",
        agent_id="spiffe://example.test/agent/coder",
        action_type="repository.write",
        resource_type="git.repository",
        bundle_digest=_BUNDLE,
    )


def _agt(source):
    return agt_policy_decision(
        _FACTORY,
        source,
        run_id="run-fuzz",
        policy_engine_version="3.1.0",
        bundle_digest=_BUNDLE,
    )


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    use_opa = fdp.ConsumeBool()
    source = copy.deepcopy(_OPA_SEED if use_opa else _AGT_SEED)
    _fuzz_build.mutate(fdp, source)
    adapter = _opa if use_opa else _agt
    try:
        event = adapter(copy.deepcopy(source))
    except ValueError:
        return
    _VALIDATOR.validate(event)
    again = adapter(copy.deepcopy(source))
    assert again["event_id"] == event["event_id"], "source event_id mapping is not deterministic"


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
