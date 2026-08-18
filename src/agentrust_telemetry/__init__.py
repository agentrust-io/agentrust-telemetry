"""AgentTrust governance telemetry reference SDK."""

from .client import EmitResult, TelemetryClient
from .context import ContextIds, active_context_ids
from .errors import ContextMismatchError, EventValidationError, ProjectionError
from .validation import SchemaValidator

__all__ = [
    "ContextIds",
    "ContextMismatchError",
    "EmitResult",
    "EventValidationError",
    "ProjectionError",
    "SchemaValidator",
    "TelemetryClient",
    "active_context_ids",
]

__version__ = "0.1.0.dev0"
