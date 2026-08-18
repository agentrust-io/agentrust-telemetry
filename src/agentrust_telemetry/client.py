"""Validated, caller-owned telemetry emission."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from .context import ContextIds, active_context_ids, current_span
from .errors import ContextMismatchError
from .projection import log_record, span_attributes
from .validation import SchemaValidator


class SpanLike(Protocol):
    def add_event(self, name: str, attributes: dict[str, Any], timestamp: int) -> None: ...
    def get_span_context(self) -> Any: ...


class LogEmitter(Protocol):
    def emit(self, record: dict[str, Any]) -> None: ...


class EvidenceSink(Protocol):
    def append(self, event: dict[str, Any]) -> Any: ...


class MetricEmitter(Protocol):
    def emit(self, event: dict[str, Any]) -> bool: ...


@dataclass(frozen=True)
class EmitResult:
    accepted: bool
    span_event_emitted: bool
    log_emitted: bool
    context: ContextIds | None
    projection_errors: tuple[str, ...] = ()
    evidence_persisted: bool = False
    metrics_emitted: bool = False


class TelemetryClient:
    def __init__(
        self,
        validator: SchemaValidator,
        *,
        span_resolver: Callable[[], SpanLike | None] | None = None,
        log_emitter: LogEmitter | None = None,
        evidence_sink: EvidenceSink | None = None,
        metric_emitter: MetricEmitter | None = None,
    ):
        self._validator = validator
        self._span_resolver = span_resolver
        self._log_emitter = log_emitter
        self._evidence_sink = evidence_sink
        self._metric_emitter = metric_emitter

    def emit(self, event: dict[str, Any]) -> EmitResult:
        self._validator.validate(event)
        resolver = self._span_resolver or current_span
        span = resolver()
        context = active_context_ids(lambda: span)
        if context:
            if event.get("trace_id") not in (None, context.trace_id):
                raise ContextMismatchError("event trace_id disagrees with active span")
            if event.get("span_id") not in (None, context.span_id):
                raise ContextMismatchError("event span_id disagrees with active span")

        evidence_persisted = False
        if self._evidence_sink is not None:
            # Evidence is accepted after correlation validation and before any
            # best-effort operational projection.
            self._evidence_sink.append(deepcopy(event))
            evidence_persisted = True

        errors: list[str] = []
        span_emitted = False
        if span is not None and context is not None:
            try:
                span.add_event(
                    event["event_type"],
                    attributes=span_attributes(event),
                    timestamp=event["time_unix_nano"],
                )
                span_emitted = True
            except Exception as exc:  # exporter implementations are external
                errors.append(f"span projection failed: {type(exc).__name__}: {exc}")

        log_emitted = False
        if self._log_emitter is not None:
            try:
                self._log_emitter.emit(log_record(event, context))
                log_emitted = True
            except Exception as exc:  # exporter implementations are external
                errors.append(f"log projection failed: {type(exc).__name__}: {exc}")

        metrics_emitted = False
        if self._metric_emitter is not None:
            try:
                metrics_emitted = self._metric_emitter.emit(deepcopy(event))
            except Exception as exc:
                errors.append(f"metric projection failed: {type(exc).__name__}: {exc}")

        return EmitResult(
            True,
            span_emitted,
            log_emitted,
            context,
            tuple(errors),
            evidence_persisted,
            metrics_emitted,
        )
