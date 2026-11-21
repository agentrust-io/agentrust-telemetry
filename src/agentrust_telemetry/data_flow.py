"""Closed, metadata-only data-flow classification boundary."""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from itertools import islice
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


@dataclass(frozen=True)
class SourceClassification:
    """Trusted classification metadata for one contributing source."""

    source: DataEndpoint
    classification: ClassificationResult

    def __post_init__(self) -> None:
        if not isinstance(self.source, DataEndpoint):
            raise TypeError("source must be a DataEndpoint")
        if not isinstance(self.classification, ClassificationResult):
            raise TypeError("classification must be a ClassificationResult")


@dataclass(frozen=True)
class ClassificationOrder:
    """Explicit least-to-most restrictive order for one taxonomy."""

    taxonomy: str
    levels: Sequence[str]

    def __post_init__(self) -> None:
        _identifier(self.taxonomy, "classification taxonomy")
        if not isinstance(self.levels, Sequence) or isinstance(self.levels, (str, bytes, bytearray)) or not self.levels:
            raise ValueError("classification levels must be a non-empty sequence")
        levels = tuple(self.levels)
        for level in levels:
            _identifier(level, "classification level")
        if len(set(levels)) != len(levels):
            raise ValueError("classification levels must be unique")
        object.__setattr__(self, "levels", levels)

    def rank(self, result: ClassificationResult) -> int:
        if not isinstance(result, ClassificationResult):
            raise TypeError("classification must be a ClassificationResult")
        if result.taxonomy != self.taxonomy:
            raise ValueError(
                f"taxonomy mismatch: expected {self.taxonomy}, got {result.taxonomy}"
            )
        try:
            return self.levels.index(result.value)
        except ValueError as exc:
            raise ValueError(
                f"unknown classification value for {self.taxonomy}: {result.value}"
            ) from exc


def _validate_source_classifications(
    sources: Iterable[SourceClassification] | None,
    order: ClassificationOrder | None,
) -> tuple[SourceClassification, ...] | None:
    """Validate caller-supplied lineage before invoking an expensive classifier."""
    if sources is None and order is None:
        return None
    if sources is None or order is None:
        raise ValueError(
            "source_classifications and classification_order must be supplied together"
        )
    if not isinstance(order, ClassificationOrder):
        raise TypeError("classification_order must be a ClassificationOrder")
    try:
        records = tuple(islice(iter(sources), 1025))
    except TypeError as exc:
        raise TypeError("source_classifications must be iterable") from exc
    if not records:
        raise ValueError("derived data must identify at least one source")
    if len(records) > 1024:
        raise ValueError("derived data may identify at most 1024 sources")

    seen: set[tuple[str, str | None]] = set()
    for record in records:
        if not isinstance(record, SourceClassification):
            raise TypeError("each source must be a SourceClassification")
        key = (record.source.kind, record.source.id)
        if key in seen:
            raise ValueError("duplicate source reference")
        seen.add(key)
        order.rank(record.classification)
    return records


def _derived_classification_fields(
    observed: ClassificationResult,
    records: tuple[SourceClassification, ...] | None,
    order: ClassificationOrder | None,
) -> dict[str, Any]:
    if records is None and order is None:
        return {}
    if records is None or order is None:
        raise ValueError(
            "source_classifications and classification_order must be supplied together"
        )
    order.rank(observed)
    candidates = [observed]
    event_sources: list[dict[str, Any]] = []
    for record in records:
        candidates.append(record.classification)
        event_sources.append({
            "source": record.source.as_event_value(),
            "classification": {
                "taxonomy": record.classification.taxonomy,
                "value": record.classification.value,
                "producer": record.classification.producer,
            },
        })

    # max() is stable: the observed output wins equal-rank ties, then the first
    # source at a higher rank wins ties with later sources in input order.
    effective = max(candidates, key=order.rank)
    return {
        "classification": {
            "taxonomy": effective.taxonomy,
            "value": effective.value,
            "producer": effective.producer,
        },
        "observed_classification": {
            "taxonomy": observed.taxonomy,
            "value": observed.value,
            "producer": observed.producer,
        },
        "source_classifications": event_sources,
    }


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
    source_classifications: Iterable[SourceClassification] | None = None,
    classification_order: ClassificationOrder | None = None,
    **envelope: Any,
) -> dict[str, Any]:
    """Classify ``value`` and emit only the classifier's closed metadata result."""
    _identifier(purpose, "purpose")
    if not isinstance(source, DataEndpoint) or not isinstance(destination, DataEndpoint):
        raise TypeError("source and destination must be DataEndpoint instances")
    if media_type is not None and (
        not isinstance(media_type, str) or _MEDIA_TYPE.fullmatch(media_type) is None
        or len(media_type) > 255
    ):
        raise ValueError("media_type must be a parameter-free type/subtype identifier")
    for field, amount in (("size_bytes", size_bytes), ("token_count", token_count)):
        if amount is not None and (
            isinstance(amount, bool) or not isinstance(amount, int)
            or amount < 0 or amount > 9007199254740991
        ):
            raise ValueError(f"{field} must be a non-negative safe integer")
    records = _validate_source_classifications(source_classifications, classification_order)

    # Only invoke the adopter-owned classifier after inexpensive argument and
    # lineage checks have passed.
    result = classifier.classify(value)
    if not isinstance(result, ClassificationResult):
        raise TypeError("classifier must return ClassificationResult")
    derived = _derived_classification_fields(result, records, classification_order)
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
        classification=derived.get("classification", {
            "taxonomy": result.taxonomy,
            "value": result.value,
            "producer": result.producer,
        }),
        **{key: item for key, item in derived.items() if key != "classification"},
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
