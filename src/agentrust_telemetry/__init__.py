"""AgentTrust governance telemetry reference SDK."""

from .client import EmitResult, TelemetryClient
from .context import ContextIds, active_context_ids
from .errors import (
    ContextMismatchError,
    EventValidationError,
    EvidenceError,
    EvidencePersistenceError,
    ProjectionError,
    PropagationError,
    TraceFinalizationError,
)
from .evidence import EvidenceAccumulator, EvidenceEntry, EvidenceSnapshot
from .propagation import ExtractedContext, extract_context, inject_context
from .trace_adapter import TraceConfiguration, finalize_trace
from .validation import SchemaValidator

__all__ = [
    "ContextIds",
    "ContextMismatchError",
    "EmitResult",
    "EventValidationError",
    "EvidenceAccumulator",
    "EvidenceEntry",
    "EvidenceError",
    "EvidencePersistenceError",
    "EvidenceSnapshot",
    "ExtractedContext",
    "ProjectionError",
    "PropagationError",
    "SchemaValidator",
    "TelemetryClient",
    "TraceConfiguration",
    "TraceFinalizationError",
    "active_context_ids",
    "extract_context",
    "inject_context",
    "finalize_trace",
]

__version__ = "0.1.0.dev0"
