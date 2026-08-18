"""Open Policy Agent decision-log adapter."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from .base import EventFactory


DecisionMapper = Callable[[Any], str]
_OPA_EVENT_NAMESPACE = uuid.UUID("881f86d8-7573-4d35-98cb-c00b934cc04f")
_TIMESTAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(?P<fraction>\d{1,9}))?Z$"
)


def opa_decision_log(
    factory: EventFactory,
    decision_log: dict[str, Any],
    *,
    run_id: str,
    agent_id: str,
    action_type: str,
    resource_type: str,
    bundle_digest: dict[str, str],
    opa_version: str | None = None,
    enforcement_mode: str = "enforce",
    result_mapper: DecisionMapper | None = None,
) -> dict[str, Any]:
    source_id = decision_log.get("decision_id")
    if not isinstance(source_id, str) or not source_id:
        raise ValueError("OPA decision log requires a non-empty decision_id")
    mapper = result_mapper or _boolean_decision
    decision = mapper(decision_log.get("result"))
    if decision not in {"allow", "deny", "challenge", "not_applicable", "error"}:
        raise ValueError(f"OPA result mapper returned unsupported decision: {decision!r}")
    labels = decision_log.get("labels", {})
    if not isinstance(labels, dict):
        raise ValueError("OPA labels must be an object")
    version = opa_version or labels.get("version")
    if not isinstance(version, str) or not version:
        raise ValueError("OPA version is required explicitly or in labels.version")
    metrics = decision_log.get("metrics", {})
    if not isinstance(metrics, dict):
        raise ValueError("OPA metrics must be an object")
    duration = metrics.get("timer_rego_query_eval_ns", 0)
    if not isinstance(duration, int) or isinstance(duration, bool) or duration < 0:
        raise ValueError("OPA timer_rego_query_eval_ns must be a non-negative integer")
    path = decision_log.get("path")
    policy: dict[str, Any] = {
        "engine": "opa",
        "engine_version": version,
        "bundle_digest": bundle_digest,
        **({"policy_id": path.lstrip("/")} if isinstance(path, str) and path else {}),
    }
    ids = decision_log.get("ids", [])
    if not isinstance(ids, list) or any(not isinstance(value, str) or not value for value in ids):
        raise ValueError("OPA ids must be an array of non-empty strings")
    if len(ids) > 32:
        raise ValueError("OPA ids exceed the 32-code contract limit")
    return factory.build(
        "policy.decision",
        run_id=run_id,
        agent_id=agent_id,
        event_id=str(uuid.uuid5(_OPA_EVENT_NAMESPACE, source_id)),
        time_unix_nano=_timestamp_ns(decision_log["timestamp"])
        if "timestamp" in decision_log
        else None,
        trace_id=decision_log.get("trace_id"),
        span_id=decision_log.get("span_id"),
        decision=decision,
        policy=policy,
        action_type=action_type,
        resource_type=resource_type,
        enforcement_mode=enforcement_mode,
        evaluation_duration_ns=duration,
        reason_codes=[f"opa.rule:{value}" for value in ids],
    )


def _boolean_decision(result: Any) -> str:
    if result is True:
        return "allow"
    if result is False:
        return "deny"
    if result is None:
        return "not_applicable"
    raise ValueError("OPA non-boolean result requires an explicit result_mapper")


def _timestamp_ns(value: Any) -> int:
    if not isinstance(value, str):
        raise ValueError("OPA timestamp must be an RFC 3339 UTC string")
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError("OPA timestamp must use RFC 3339 UTC form ending in Z")
    base = datetime.fromisoformat(match.group("date")).replace(tzinfo=timezone.utc)
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return int(base.timestamp()) * 1_000_000_000 + int(fraction or "0")
