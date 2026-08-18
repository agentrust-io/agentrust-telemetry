"""Optional bridge from AGT governance events to AgentTrust telemetry."""

from __future__ import annotations

import math
import re
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Iterable, Protocol, Sequence

from .base import EventFactory


_IDENTIFIER = re.compile(r"[A-Za-z0-9_.:-]{1,128}")
_TIMESTAMP = re.compile(
    r"^(?P<date>\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})(?:\.(?P<fraction>\d{1,9}))?(?:Z|\+00:00)$"
)


class TelemetryEmitter(Protocol):
    def emit(self, event: dict[str, Any]) -> Any: ...


AgtEventMapper = Callable[[Any], Iterable[dict[str, Any]]]


class AgtGovernanceEventSink:
    """AGT-compatible batch sink without a mandatory AGT dependency.

    Construct directly with the source runtime's result sentinels, or use
    :meth:`from_agent_os` when ``agent-os`` is installed.
    """

    def __init__(
        self,
        client: TelemetryEmitter,
        mapper: AgtEventMapper,
        *,
        success_result: Any,
        failure_result: Any,
    ) -> None:
        self._client = client
        self._mapper = mapper
        self._success = success_result
        self._failure = failure_result

    @classmethod
    def from_agent_os(
        cls,
        client: TelemetryEmitter,
        mapper: AgtEventMapper,
    ) -> "AgtGovernanceEventSink":
        try:
            from agent_os.event_sink import SinkExportResult
        except ImportError as exc:
            raise ImportError(
                "AgtGovernanceEventSink.from_agent_os requires the agent-os package"
            ) from exc
        return cls(
            client,
            mapper,
            success_result=SinkExportResult.SUCCESS,
            failure_result=SinkExportResult.FAILURE,
        )

    def emit(self, events: Sequence[Any]) -> Any:
        """Normalize then emit a batch, returning the configured AGT result."""
        try:
            normalized = [item for source in events for item in self._mapper(source)]
            for event in normalized:
                result = self._client.emit(event)
                if not getattr(result, "accepted", False):
                    return self._failure
                if getattr(result, "projection_errors", ()):
                    return self._failure
            return self._success
        except Exception:
            return self._failure

    def shutdown(self, timeout_ms: int = 5000) -> bool:
        return True

    def force_flush(self, timeout_ms: int = 30000) -> bool:
        return True


def agt_policy_decision(
    factory: EventFactory,
    source: Any,
    *,
    run_id: str,
    policy_engine_version: str,
    bundle_digest: dict[str, str],
    resource_type: str | None = None,
    enforcement_mode: str = "enforce",
) -> dict[str, Any]:
    """Normalize one AGT policy event without copying free-form source content."""
    kind = _enum_value(_field(source, "kind"))
    if kind not in {"policy_check", "policy_violation"}:
        raise ValueError(f"AGT event kind is not a policy decision: {kind!r}")
    decision = _decision(_field(source, "decision"))
    agent_id = _required_string(_field(source, "agent_id"), "agent_id")
    action_type = _required_string(_field(source, "action"), "action")
    attributes = _field(source, "attributes", {})
    if not isinstance(attributes, dict):
        raise ValueError("AGT attributes must be an object")
    resolved_resource_type = resource_type or attributes.get("resource_type")
    resolved_resource_type = _required_string(resolved_resource_type, "resource_type")
    event_id = _event_id(_field(source, "event_id"))
    reason_codes = _reason_codes(attributes.get("reason_codes", []))
    latency_ms = _field(source, "latency_ms", 0.0)
    if (
        not isinstance(latency_ms, (int, float))
        or isinstance(latency_ms, bool)
        or not math.isfinite(latency_ms)
        or latency_ms < 0
    ):
        raise ValueError("AGT latency_ms must be a finite non-negative number")
    policy: dict[str, Any] = {
        "engine": "agt",
        "engine_version": _required_string(policy_engine_version, "policy_engine_version"),
        "bundle_digest": bundle_digest,
    }
    policy_name = _field(source, "policy_name")
    if policy_name is not None:
        policy["policy_id"] = _required_string(policy_name, "policy_name")
    return factory.build(
        "policy.decision",
        run_id=run_id,
        agent_id=agent_id,
        event_id=event_id,
        time_unix_nano=_timestamp_ns(_field(source, "occurred_at")),
        trace_id=_field(source, "trace_id"),
        span_id=_field(source, "span_id"),
        decision=decision,
        policy=policy,
        action_type=action_type,
        resource_type=resolved_resource_type,
        enforcement_mode=enforcement_mode,
        evaluation_duration_ns=round(latency_ms * 1_000_000),
        reason_codes=reason_codes,
    )


def _field(source: Any, name: str, default: Any = None) -> Any:
    if isinstance(source, dict):
        return source.get(name, default)
    return getattr(source, name, default)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _decision(value: Any) -> str:
    normalized = _enum_value(value)
    mapping = {
        "allow": "allow",
        "allowed": "allow",
        "deny": "deny",
        "denied": "deny",
        "block": "deny",
        "blocked": "deny",
        "require_approval": "challenge",
        "requires_approval": "challenge",
        "review": "challenge",
    }
    if normalized not in mapping:
        raise ValueError(f"unsupported AGT policy decision: {normalized!r}")
    return mapping[normalized]


def _required_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"AGT {field} must be a non-empty string")
    return value


def _reason_codes(values: Any) -> list[str]:
    if not isinstance(values, list):
        raise ValueError("AGT reason_codes must be an array")
    if len(values) > 32 or any(
        not isinstance(value, str) or _IDENTIFIER.fullmatch(value) is None
        for value in values
    ):
        raise ValueError("AGT reason_codes must contain at most 32 identifiers")
    if len(values) != len(set(values)):
        raise ValueError("AGT reason_codes must be unique")
    return list(values)


def _event_id(value: Any) -> str:
    try:
        return str(uuid.UUID(_required_string(value, "event_id")))
    except (ValueError, AttributeError) as exc:
        raise ValueError("AGT event_id must be a UUID") from exc


def _timestamp_ns(value: Any) -> int:
    value = _required_string(value, "occurred_at")
    match = _TIMESTAMP.fullmatch(value)
    if match is None:
        raise ValueError("AGT occurred_at must be an RFC 3339 UTC timestamp")
    base = datetime.fromisoformat(match.group("date")).replace(tzinfo=timezone.utc)
    fraction = (match.group("fraction") or "").ljust(9, "0")
    return int(base.timestamp()) * 1_000_000_000 + int(fraction or "0")
