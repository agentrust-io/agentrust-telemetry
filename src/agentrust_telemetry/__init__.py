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
)
from .evidence import EvidenceAccumulator, EvidenceEntry, EvidenceSnapshot
from .propagation import ExtractedContext, extract_context, inject_context
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
    "active_context_ids",
    "extract_context",
    "inject_context",
]

__version__ = "0.1.0.dev0"
