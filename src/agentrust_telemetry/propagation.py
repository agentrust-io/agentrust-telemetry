"""W3C trace-context propagation with minimal AgentTrust correlation metadata."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, MutableMapping

from .errors import PropagationError


RUN_ID_HEADER = "x-agentrust-run-id"
WORKFLOW_ID_HEADER = "x-agentrust-workflow-id"
UPSTREAM_AGENT_ID_HEADER = "x-agentrust-agent-id"
_MAX_VALUE_LENGTH = 512


@dataclass(frozen=True)
class ExtractedContext:
    """Remote OTel context plus untrusted AgentTrust correlation metadata."""

    otel_context: Any
    run_id: str | None
    workflow_id: str | None
    upstream_agent_id: str | None

    def event_fields(self, *, agent_id: str) -> dict[str, str]:
        """Build envelope fields for work performed by ``agent_id``."""
        fields = {"agent_id": _safe_value("agent_id", agent_id, required=True)}
        if self.run_id is not None:
            fields["run_id"] = self.run_id
        if self.workflow_id is not None:
            fields["workflow_id"] = self.workflow_id
        if self.upstream_agent_id is not None:
            fields["parent_agent_id"] = self.upstream_agent_id
        return fields

    def link(self, *, attributes: dict[str, Any] | None = None) -> Any:
        """Create an OTel Link for asynchronous handoff or fan-in."""
        _, trace = _otel()
        span_context = trace.get_current_span(self.otel_context).get_span_context()
        if not span_context.is_valid:
            raise PropagationError("extracted context has no valid remote span to link")
        return trace.Link(span_context, attributes=attributes)


def inject_context(
    carrier: MutableMapping[str, str],
    *,
    run_id: str,
    agent_id: str,
    workflow_id: str | None = None,
    context: Any | None = None,
) -> None:
    """Inject standard W3C context and minimal AgentTrust headers into ``carrier``."""
    propagate, _ = _otel()
    propagate.inject(carrier, context=context)
    carrier[RUN_ID_HEADER] = _safe_value("run_id", run_id, required=True)
    carrier[UPSTREAM_AGENT_ID_HEADER] = _safe_value("agent_id", agent_id, required=True)
    if workflow_id is not None:
        carrier[WORKFLOW_ID_HEADER] = _safe_value("workflow_id", workflow_id, required=True)


def extract_context(carrier: MutableMapping[str, str]) -> ExtractedContext:
    """Extract a remote parent and validate optional AgentTrust headers."""
    propagate, _ = _otel()
    context = propagate.extract(carrier)
    return ExtractedContext(
        otel_context=context,
        run_id=_header(carrier, RUN_ID_HEADER),
        workflow_id=_header(carrier, WORKFLOW_ID_HEADER),
        upstream_agent_id=_header(carrier, UPSTREAM_AGENT_ID_HEADER),
    )


def _header(carrier: MutableMapping[str, str], name: str) -> str | None:
    value = carrier.get(name)
    if value is None:
        # HTTP field names are case-insensitive even when a plain mapping is used.
        value = next((item for key, item in carrier.items() if key.lower() == name), None)
    return None if value is None else _safe_value(name, value, required=True)


def _safe_value(name: str, value: Any, *, required: bool) -> str:
    if not isinstance(value, str):
        raise PropagationError(f"{name} must be a string")
    if required and not value:
        raise PropagationError(f"{name} must not be empty")
    if len(value) > _MAX_VALUE_LENGTH:
        raise PropagationError(f"{name} exceeds {_MAX_VALUE_LENGTH} characters")
    if "\r" in value or "\n" in value:
        raise PropagationError(f"{name} contains a prohibited line break")
    return value


def _otel() -> tuple[Any, Any]:
    try:
        from opentelemetry import propagate, trace
    except ImportError as exc:  # pragma: no cover - exercised in minimal installs
        raise PropagationError(
            "OpenTelemetry propagation requires the 'otel' optional dependency"
        ) from exc
    return propagate, trace
