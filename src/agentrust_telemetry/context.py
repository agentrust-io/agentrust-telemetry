"""Optional OpenTelemetry context integration without global configuration."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class ContextIds:
    trace_id: str
    span_id: str


def current_span() -> Any | None:
    try:
        from opentelemetry import trace
    except ImportError:
        return None
    return trace.get_current_span()


def active_context_ids(span_resolver: Callable[[], Any | None] = current_span) -> ContextIds | None:
    span = span_resolver()
    if span is None:
        return None
    context = span.get_span_context()
    if not getattr(context, "is_valid", False):
        return None
    return ContextIds(trace_id=f"{context.trace_id:032x}", span_id=f"{context.span_id:016x}")
