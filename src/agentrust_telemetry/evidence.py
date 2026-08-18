"""Deterministic, pre-sampling evidence accumulation."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from dataclasses import dataclass
from threading import Lock
from typing import Any, Callable, Literal

from .errors import EvidenceError, EvidencePersistenceError
from .validation import SchemaValidator


Completeness = Literal["complete", "incomplete", "unknown"]
CANONICALIZATION_PROFILE = "agentrust-json-v1"
_GENESIS_DIGEST = bytes(32)


@dataclass(frozen=True)
class EvidenceEntry:
    sequence: int
    event_id: str
    previous_digest: str | None
    digest: str
    event: dict[str, Any]


@dataclass(frozen=True)
class EvidenceSnapshot:
    run_id: str
    entries: tuple[EvidenceEntry, ...]
    chain_digest: str | None
    canonicalization_profile: str
    completeness: Completeness
    sealed: bool


DurableAppend = Callable[[EvidenceEntry], bool]


class EvidenceAccumulator:
    """Accumulate one run's validated events before operational projection.

    A durable callback must be idempotent by ``event_id`` and return ``True`` only
    after the entry is durably committed. Callback failure leaves local state
    unchanged so callers can retry the same event.
    """

    def __init__(
        self,
        run_id: str,
        validator: SchemaValidator,
        *,
        durable_append: DurableAppend | None = None,
        max_events: int = 10_000,
    ) -> None:
        if not isinstance(run_id, str) or not run_id:
            raise EvidenceError("run_id must be a non-empty string")
        if max_events < 1:
            raise EvidenceError("max_events must be at least 1")
        self._run_id = run_id
        self._validator = validator
        self._durable_append = durable_append
        self._max_events = max_events
        self._entries: list[EvidenceEntry] = []
        self._event_ids: set[str] = set()
        self._sealed = False
        self._completeness: Completeness = "unknown"
        self._lock = Lock()

    @property
    def mode(self) -> Literal["memory", "callback"]:
        return "callback" if self._durable_append is not None else "memory"

    def append(self, event: dict[str, Any]) -> EvidenceEntry:
        """Validate, chain, durably acknowledge, then accept an event."""
        self._validator.validate(event)
        event_copy = deepcopy(event)
        if event_copy["run_id"] != self._run_id:
            raise EvidenceError("event run_id does not match accumulator run_id")

        with self._lock:
            if self._sealed:
                raise EvidenceError("evidence run is sealed")
            event_id = event_copy["event_id"]
            if event_id in self._event_ids:
                raise EvidenceError(f"duplicate event_id: {event_id}")
            if len(self._entries) >= self._max_events:
                raise EvidenceError(f"evidence run exceeds max_events={self._max_events}")

            sequence = len(self._entries)
            previous = self._entries[-1].digest if self._entries else None
            try:
                digest = _entry_digest(sequence, previous, event_copy)
            except (TypeError, ValueError) as exc:
                raise EvidenceError(
                    f"event_id={event_id} cannot be canonicalized under "
                    f"{CANONICALIZATION_PROFILE}"
                ) from exc
            entry = EvidenceEntry(sequence, event_id, previous, digest, event_copy)

            if self._durable_append is not None:
                try:
                    acknowledged = self._durable_append(_copy_entry(entry))
                except Exception as exc:
                    raise EvidencePersistenceError(
                        f"durable evidence callback failed for event_id={event_id}"
                    ) from exc
                if acknowledged is not True:
                    raise EvidencePersistenceError(
                        f"durable evidence callback did not acknowledge event_id={event_id}"
                    )

            self._entries.append(_copy_entry(entry))
            self._event_ids.add(event_id)
            return _copy_entry(entry)

    def seal(self, *, completeness: Completeness) -> EvidenceSnapshot:
        """Close the run with a caller-asserted completeness assessment."""
        if completeness not in ("complete", "incomplete", "unknown"):
            raise EvidenceError(f"unsupported completeness: {completeness!r}")
        with self._lock:
            if self._sealed:
                raise EvidenceError("evidence run is already sealed")
            self._sealed = True
            self._completeness = completeness
            return self._snapshot()

    def snapshot(self) -> EvidenceSnapshot:
        with self._lock:
            return self._snapshot()

    def _snapshot(self) -> EvidenceSnapshot:
        entries = tuple(_copy_entry(item) for item in self._entries)
        return EvidenceSnapshot(
            run_id=self._run_id,
            entries=entries,
            chain_digest=entries[-1].digest if entries else None,
            canonicalization_profile=CANONICALIZATION_PROFILE,
            completeness=self._completeness if self._sealed else "unknown",
            sealed=self._sealed,
        )


def _entry_digest(sequence: int, previous_digest: str | None, event: dict[str, Any]) -> str:
    canonical = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")
    previous = bytes.fromhex(previous_digest) if previous_digest else _GENESIS_DIGEST
    material = previous + sequence.to_bytes(8, "big") + canonical
    return hashlib.sha256(material).hexdigest()


def _copy_entry(entry: EvidenceEntry) -> EvidenceEntry:
    return EvidenceEntry(
        entry.sequence,
        entry.event_id,
        entry.previous_digest,
        entry.digest,
        deepcopy(entry.event),
    )
