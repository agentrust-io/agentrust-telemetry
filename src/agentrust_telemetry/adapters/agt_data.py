"""AGT DataLabel and DataAccessDecision adapters."""

from __future__ import annotations

from enum import Enum
from typing import Any

from ..data_flow import (
    ClassificationResult,
    DataEndpoint,
    classified_data_flow,
)
from .base import EventFactory


_LEVELS = {
    0: "public",
    1: "internal",
    2: "confidential",
    3: "restricted",
    4: "top_secret",
}


def agt_data_classification(source: Any) -> ClassificationResult:
    """Map only AGT's ordered sensitivity tier; omit auxiliary label content."""
    classification = _field(source, "classification")
    raw = classification.value if isinstance(classification, Enum) else classification
    if isinstance(raw, bool) or raw not in _LEVELS:
        raise ValueError(f"unsupported AGT data classification: {raw!r}")
    return ClassificationResult(
        taxonomy="agt.data_classification.v1",
        value=_LEVELS[raw],
        producer="agt.data_label",
    )


def agt_data_access_flow(
    factory: EventFactory,
    decision: Any,
    *,
    run_id: str,
    direction: str,
    source: DataEndpoint,
    destination: DataEndpoint,
    purpose: str,
    content_digest: dict[str, str] | None = None,
    size_bytes: int | None = None,
    token_count: int | None = None,
    media_type: str | None = None,
    transformation: str | None = None,
    **envelope: Any,
) -> dict[str, Any]:
    """Map an AGT DataAccessDecision without copying labels or free-form reason."""
    allowed = _field(decision, "allowed")
    if not isinstance(allowed, bool):
        raise ValueError("AGT data access allowed must be a boolean")
    result = agt_data_classification(_field(decision, "data_label"))
    agent_id = _field(decision, "agent_id")
    if not isinstance(agent_id, str) or not agent_id:
        raise ValueError("AGT data access agent_id must be a non-empty string")
    class FixedClassifier:
        def classify(self, value: Any) -> ClassificationResult:
            return result

    return classified_data_flow(
        factory,
        FixedClassifier(),
        None,
        run_id=run_id,
        agent_id=agent_id,
        time_unix_nano=_datetime_ns(_field(decision, "evaluated_at")),
        direction=direction,
        source=source,
        destination=destination,
        purpose=purpose,
        policy_decision="allow" if allowed else "deny",
        content_digest=content_digest,
        size_bytes=size_bytes,
        token_count=token_count,
        media_type=media_type,
        transformation=transformation,
        **envelope,
    )


def _field(source: Any, name: str) -> Any:
    if isinstance(source, dict):
        return source.get(name)
    return getattr(source, name, None)


def _datetime_ns(value: Any) -> int:
    from datetime import datetime, timezone

    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("AGT data access evaluated_at must be a timezone-aware datetime")
    utc = value.astimezone(timezone.utc)
    epoch = datetime(1970, 1, 1, tzinfo=timezone.utc)
    delta = utc - epoch
    return (
        delta.days * 86_400_000_000_000
        + delta.seconds * 1_000_000_000
        + delta.microseconds * 1_000
    )
