"""Strict adapters for Agent Mesh audit entries shipped by AGT core."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from .base import EventFactory


_AUDIT_NAMESPACE = uuid.UUID("398428fd-2730-498f-8ed8-6b4290668171")
_POLICY_EVENTS = {"policy_evaluation", "policy_violation"}
_ACTION_EVENTS = {"tool_invocation", "tool_blocked", "action"}
_DIGEST_OBJ = re.compile(r"^sha(256:[0-9a-f]{64}|384:[0-9a-f]{96})$")
_MAX_SAFE_INTEGER = 9007199254740991


def _validate_digest_obj(digest_obj: Any, field: str) -> dict[str, str]:
    if not isinstance(digest_obj, dict):
        raise ValueError(f"AGT audit {field} must be a digest object")
    alg = digest_obj.get("algorithm")
    val = digest_obj.get("value")
    if (
        not isinstance(alg, str)
        or not isinstance(val, str)
        or _DIGEST_OBJ.fullmatch(f"{alg}:{val}") is None
    ):
        raise ValueError(f"AGT audit {field} must be a valid sha256 or sha384 digest object")
    return {"algorithm": alg, "value": val}


def _safe_duration(value: Any, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= _MAX_SAFE_INTEGER:
        raise ValueError(f"{field} must be a non-negative safe integer")
    return value


def agt_audit_policy_decision(
    factory: EventFactory,
    source: Any,
    *,
    run_id: str,
    policy_engine_version: str,
    bundle_digest: dict[str, str],
    resource_type: str,
    evaluation_duration_ns: int = 0,
    enforcement_mode: str = "enforce",
) -> dict[str, Any]:
    """Map a policy-oriented Agent Mesh AuditEntry without copying its data."""
    event_type = _required_string(_field(source, "event_type"), "event_type")
    if event_type not in _POLICY_EVENTS:
        raise ValueError(f"AGT audit event is not a policy event: {event_type!r}")
    decision = _policy_decision(_field(source, "policy_decision"))
    entry_id = _required_string(_field(source, "entry_id"), "entry_id")
    duration = _safe_duration(evaluation_duration_ns, "evaluation_duration_ns")
    checked_bundle = _validate_digest_obj(bundle_digest, "bundle_digest")
    policy: dict[str, Any] = {
        "engine": "agt",
        "engine_version": _required_string(policy_engine_version, "policy_engine_version"),
        "bundle_digest": checked_bundle,
    }
    matched_rule = _field(source, "matched_rule")
    if matched_rule is not None:
        policy["policy_id"] = _required_string(matched_rule, "matched_rule")
    return factory.build(
        "policy.decision",
        run_id=run_id,
        agent_id=_required_string(_field(source, "agent_did"), "agent_did"),
        event_id=_source_event_id("policy", entry_id),
        time_unix_nano=_datetime_ns(_field(source, "timestamp"), "timestamp"),
        trace_id=_optional_string(_field(source, "trace_id"), "trace_id"),
        decision=decision,
        policy=policy,
        action_type=_required_string(_field(source, "action"), "action"),
        resource_type=_required_string(resource_type, "resource_type"),
        enforcement_mode=enforcement_mode,
        evaluation_duration_ns=duration,
        reason_codes=[f"agt.audit:{event_type}"],
    )


def agt_audit_action(
    factory: EventFactory,
    source: Any,
    *,
    run_id: str,
    action_digest: dict[str, str],
    action_kind: str,
    operation: str,
    duration_ns: int | None = None,
) -> dict[str, Any]:
    """Map an action audit row using a caller-computed full action digest."""
    event_type = _required_string(_field(source, "event_type"), "event_type")
    if event_type not in _ACTION_EVENTS:
        raise ValueError(f"AGT audit event is not an action event: {event_type!r}")
    entry_id = _required_string(_field(source, "entry_id"), "entry_id")
    outcome = "denied" if event_type == "tool_blocked" else _action_outcome(
        _field(source, "outcome")
    )
    resolved_duration = duration_ns
    if resolved_duration is None:
        resolved_duration = _audit_duration(source)
    else:
        resolved_duration = _safe_duration(resolved_duration, "duration_ns")
    checked_action_digest = _validate_digest_obj(action_digest, "action_digest")
    target: dict[str, str] | None = None
    target_did = _field(source, "target_did")
    if target_did is not None:
        target = {"kind": "agent", "id": _required_string(target_did, "target_did")}
    return factory.build(
        "action.executed",
        run_id=run_id,
        agent_id=_required_string(_field(source, "agent_did"), "agent_did"),
        event_id=_source_event_id("action", entry_id),
        time_unix_nano=_datetime_ns(_field(source, "timestamp"), "timestamp"),
        trace_id=_optional_string(_field(source, "trace_id"), "trace_id"),
        action_id=entry_id,
        action_kind=action_kind,
        action_name=_required_string(_field(source, "action"), "action"),
        operation=_required_string(operation, "operation"),
        outcome=outcome,
        duration_ns=resolved_duration,
        action_digest=checked_action_digest,
        **({"target": target} if target else {}),
    )


def _policy_decision(value: Any) -> str:
    mapping = {
        "allow": "allow",
        "allowed": "allow",
        "deny": "deny",
        "denied": "deny",
        "require_approval": "challenge",
        "requires_approval": "challenge",
        "review": "challenge",
        "not_applicable": "not_applicable",
        "error": "error",
    }
    if not isinstance(value, str) or value not in mapping:
        raise ValueError(f"unsupported AGT audit policy decision: {value!r}")
    return mapping[value]


def _action_outcome(value: Any) -> str:
    mapping = {
        "success": "success",
        "failure": "error",
        "error": "error",
        "denied": "denied",
        "cancelled": "cancelled",
        "timeout": "timeout",
    }
    if not isinstance(value, str) or value not in mapping:
        raise ValueError(f"unsupported AGT audit action outcome: {value!r}")
    return mapping[value]


def _audit_duration(source: Any) -> int:
    issued = _field(source, "issued_at")
    completed = _field(source, "completed_at")
    if issued is None or completed is None:
        raise ValueError(
            "AGT action audit requires duration_ns or both issued_at and completed_at"
        )
    issued_ns = _datetime_ns(issued, "issued_at")
    completed_ns = _datetime_ns(completed, "completed_at")
    if completed_ns < issued_ns:
        raise ValueError("AGT completed_at cannot predate issued_at")
    diff = completed_ns - issued_ns
    if diff > _MAX_SAFE_INTEGER:
        raise ValueError("AGT audit duration exceeds the safe integer range")
    return diff


def _source_event_id(kind: str, source_id: str) -> str:
    return str(uuid.uuid5(_AUDIT_NAMESPACE, f"{kind}:{source_id}"))


def _field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"AGT audit {field} must be a non-empty string")
    return value


def _optional_string(value: Any, field: str) -> str | None:
    return None if value is None else _required_string(value, field)


def _datetime_ns(value: Any, field: str) -> int:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"AGT audit {field} must be a timezone-aware datetime")
    utc = value.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = utc - epoch
    return (
        delta.days * 86_400_000_000_000
        + delta.seconds * 1_000_000_000
        + delta.microseconds * 1_000
    )
