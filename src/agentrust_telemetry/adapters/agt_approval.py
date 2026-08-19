"""Adapters for AGT's action-bound approval protocol objects."""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from .base import EventFactory


_SOURCE_NAMESPACE = uuid.UUID("ea5a1737-5417-4eaa-8bb0-4fc40e4cb837")
_DIGEST = re.compile(r"^(?P<algorithm>sha256):(?P<value>[0-9a-f]{64})$")


def agt_policy_decision_record(
    factory: EventFactory,
    source: Any,
    *,
    run_id: str,
    agent_id: str,
    action_type: str,
    resource_type: str,
    policy_engine_version: str,
    bundle_digest: dict[str, str],
    evaluation_duration_ns: int = 0,
    enforcement_mode: str = "enforce",
    trace_id: str | None = None,
    span_id: str | None = None,
) -> dict[str, Any]:
    """Map an AGT PolicyDecisionRecord that suspended for approval."""
    verdict = _enum_value(_field(source, "verdict"))
    if verdict != "require_approval":
        raise ValueError("AGT PolicyDecisionRecord verdict must be require_approval")
    source_id = _required_string(_field(source, "policy_decision_id"), "policy_decision_id")
    return factory.build(
        "policy.decision",
        run_id=run_id,
        agent_id=agent_id,
        event_id=_source_event_id("policy", source_id),
        time_unix_nano=_datetime_ns(_field(source, "decided_at"), "decided_at"),
        trace_id=trace_id,
        span_id=span_id,
        decision="challenge",
        policy={
            "engine": "agt",
            "engine_version": policy_engine_version,
            "policy_id": _required_string(_field(source, "policy_rule_id"), "policy_rule_id"),
            "bundle_digest": bundle_digest,
        },
        action_type=action_type,
        resource_type=resource_type,
        enforcement_mode=enforcement_mode,
        evaluation_duration_ns=evaluation_duration_ns,
        reason_codes=["agt.verdict:require_approval"],
    )


def agt_approval_request(
    factory: EventFactory,
    source: Any,
    policy_decision: Any,
    *,
    run_id: str,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> dict[str, Any]:
    """Map an AGT ApprovalRequest while preserving its policy and chain links."""
    _verify_request_binding(source, policy_decision)
    approval_id = _required_string(_field(source, "approval_request_id"), "approval_request_id")
    policy_id = _required_string(_field(source, "policy_decision_id"), "policy_decision_id")
    return factory.build(
        "approval.requested",
        run_id=run_id,
        agent_id=_required_string(_field(source, "agent_id"), "agent_id"),
        event_id=_source_event_id("approval.requested", approval_id),
        time_unix_nano=_datetime_ns(_field(source, "requested_at"), "requested_at"),
        trace_id=trace_id,
        span_id=span_id,
        approval_id=approval_id,
        policy_event_id=_source_event_id("policy", policy_id),
        chain_id=_required_string(_field(source, "approval_chain_id"), "approval_chain_id"),
        chain_version=_required_string(
            _field(source, "approval_chain_version"), "approval_chain_version"
        ),
        action_digest=_digest(_field(source, "action_digest"), "action_digest"),
        actor_type="policy",
        requested_at_unix_nano=_datetime_ns(_field(source, "requested_at"), "requested_at"),
        expires_at_unix_nano=_datetime_ns(_field(source, "expires_at"), "expires_at"),
        reason_codes=["agt.approval:requested"],
    )


def agt_approval_resolution(
    factory: EventFactory,
    resolution: Any,
    request: Any,
    *,
    run_id: str,
    trace_id: str | None = None,
    span_id: str | None = None,
) -> dict[str, Any]:
    """Map a terminal AGT resolution after verifying its request binding."""
    _verify_resolution_binding(resolution, request)
    outcome = _enum_value(_field(resolution, "outcome"))
    event_type = {
        "allow": "approval.approved",
        "deny": "approval.rejected",
        "expired": "approval.expired",
    }.get(outcome)
    if event_type is None:
        raise ValueError(f"unsupported AGT approval outcome: {outcome!r}")
    approval_id = _required_string(
        _field(resolution, "approval_request_id"), "approval_request_id"
    )
    resolved_at = _datetime_ns(_field(resolution, "resolved_at"), "resolved_at")
    requested_at = _datetime_ns(_field(request, "requested_at"), "requested_at")
    if resolved_at < requested_at:
        raise ValueError("AGT approval resolution cannot predate its request")
    final_digest = _field(resolution, "final_entry_digest")
    optional_evidence = (
        {"approval_evidence_digest": _digest(final_digest, "final_entry_digest")}
        if final_digest is not None
        else {}
    )
    policy_id = _required_string(_field(request, "policy_decision_id"), "policy_decision_id")
    resolution_id = _required_string(
        _field(resolution, "approval_resolution_id"), "approval_resolution_id"
    )
    return factory.build(
        event_type,
        run_id=run_id,
        agent_id=_required_string(_field(request, "agent_id"), "agent_id"),
        event_id=_source_event_id("approval.resolution", resolution_id),
        time_unix_nano=resolved_at,
        trace_id=trace_id,
        span_id=span_id,
        approval_id=approval_id,
        policy_event_id=_source_event_id("policy", policy_id),
        chain_id=_required_string(_field(request, "approval_chain_id"), "approval_chain_id"),
        chain_version=_required_string(
            _field(request, "approval_chain_version"), "approval_chain_version"
        ),
        resolution_id=resolution_id,
        action_digest=_digest(_field(resolution, "action_digest"), "action_digest"),
        actor_type="system",
        requested_at_unix_nano=requested_at,
        expires_at_unix_nano=_datetime_ns(_field(request, "expires_at"), "expires_at"),
        reason_codes=[f"agt.outcome:{outcome}"],
        **optional_evidence,
    )


def _verify_resolution_binding(resolution: Any, request: Any) -> None:
    pairs = (
        ("approval_request_id", "approval_request_id"),
        ("action_digest", "action_digest"),
        ("policy_version", "policy_version"),
        ("approval_chain_version", "approval_chain_version"),
    )
    for resolution_field, request_field in pairs:
        left = _enum_value(_field(resolution, resolution_field))
        right = _enum_value(_field(request, request_field))
        if left != right:
            raise ValueError(
                f"AGT resolution {resolution_field} does not match request {request_field}"
            )


def _verify_request_binding(request: Any, policy_decision: Any) -> None:
    pairs = (
        ("policy_decision_id", "policy_decision_id"),
        ("action_digest", "action_digest"),
        ("policy_version", "policy_version"),
        ("approval_chain_id", "approval_chain_id"),
        ("approval_chain_version", "approval_chain_version"),
    )
    for request_field, policy_field in pairs:
        left = _enum_value(_field(request, request_field))
        right = _enum_value(_field(policy_decision, policy_field))
        if left != right:
            raise ValueError(
                f"AGT request {request_field} does not match policy decision {policy_field}"
            )


def _source_event_id(kind: str, source_id: str) -> str:
    return str(uuid.uuid5(_SOURCE_NAMESPACE, f"{kind}:{source_id}"))


def _field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"AGT {field} must be a non-empty string")
    return value


def _digest(value: Any, field: str) -> dict[str, str]:
    value = _required_string(value, field)
    match = _DIGEST.fullmatch(value)
    if match is None:
        raise ValueError(f"AGT {field} must use sha256:<lowercase-hex>")
    return match.groupdict()


def _datetime_ns(value: Any, field: str) -> int:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError(f"AGT {field} must be a timezone-aware datetime")
    utc = value.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = utc - epoch
    return (
        delta.days * 86_400_000_000_000
        + delta.seconds * 1_000_000_000
        + delta.microseconds * 1_000
    )
