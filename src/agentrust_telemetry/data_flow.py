"""Closed, metadata-only data-flow classification boundary."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,255}")
_MEDIA_TYPE = re.compile(r"[A-Za-z0-9!#$&^_.+-]+/[A-Za-z0-9!#$&^_.+-]+")


@dataclass(frozen=True)
class ClassificationResult:
    taxonomy: str
    value: str
    producer: str

    def __post_init__(self) -> None:
        _identifier(self.taxonomy, "classification taxonomy")
        _identifier(self.value, "classification value")
        _identifier(self.producer, "classification producer")


@dataclass(frozen=True)
class DataEndpoint:
    kind: str
    id: str | None = None

    def __post_init__(self) -> None:
        _identifier(self.kind, "endpoint kind")
        if self.id is not None:
            _identifier(self.id, "endpoint id")

    def as_event_value(self) -> dict[str, str]:
        return {"kind": self.kind, **({"id": self.id} if self.id else {})}


class DataClassifier(Protocol):
    def classify(self, value: Any) -> ClassificationResult: ...


class EventFactoryLike(Protocol):
    def build(self, event_type: str, **fields: Any) -> dict[str, Any]: ...


def classified_data_flow(
    factory: EventFactoryLike,
    classifier: DataClassifier,
    value: Any,
    *,
    run_id: str,
    agent_id: str,
    direction: str,
    source: DataEndpoint,
    destination: DataEndpoint,
    purpose: str,
    policy_decision: str = "not_evaluated",
    content_digest: dict[str, str] | None = None,
    size_bytes: int | None = None,
    token_count: int | None = None,
    media_type: str | None = None,
    transformation: str | None = None,
    **envelope: Any,
) -> dict[str, Any]:
    """Classify ``value`` and emit only the classifier's closed metadata result."""
    result = classifier.classify(value)
    if not isinstance(result, ClassificationResult):
        raise TypeError("classifier must return ClassificationResult")
    _identifier(purpose, "purpose")
    if media_type is not None and (
        not isinstance(media_type, str) or _MEDIA_TYPE.fullmatch(media_type) is None
        or len(media_type) > 255
    ):
        raise ValueError("media_type must be a parameter-free type/subtype identifier")
    optional = {
        "content_digest": content_digest,
        "size_bytes": size_bytes,
        "token_count": token_count,
        "media_type": media_type,
        "transformation": transformation,
    }
    return factory.build(
        "data_flow.observed",
        run_id=run_id,
        agent_id=agent_id,
        direction=direction,
        source=source.as_event_value(),
        destination=destination.as_event_value(),
        classification={
            "taxonomy": result.taxonomy,
            "value": result.value,
            "producer": result.producer,
        },
        purpose=purpose,
        policy_decision=policy_decision,
        **{key: item for key, item in optional.items() if item is not None},
        **envelope,
    )


def _identifier(value: Any, field: str) -> str:
    if (
        not isinstance(value, str)
        or _IDENTIFIER.fullmatch(value) is None
        or "://" in value
    ):
        raise ValueError(
            f"{field} must be a 1-256 character metadata identifier without whitespace, "
            "query strings, fragments, or key/value delimiters"
        )
    return value
