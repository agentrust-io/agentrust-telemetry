"""AgentTrust governance telemetry reference SDK."""

from .adapters import (
    AgtGovernanceEventSink,
    EventFactory,
    agt_approval_request,
    agt_approval_resolution,
    agt_policy_decision,
    agt_policy_decision_record,
    cedar_policy_decision,
    opa_decision_log,
)
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
from .otel import OTelLogEmitter, OTelMetricEmitter
from .trace_adapter import TraceConfiguration, finalize_trace
from .validation import SchemaValidator

__all__ = [
    "ContextIds",
    "ContextMismatchError",
    "AgtGovernanceEventSink",
    "EmitResult",
    "EventValidationError",
    "EventFactory",
    "EvidenceAccumulator",
    "EvidenceEntry",
    "EvidenceError",
    "EvidencePersistenceError",
    "EvidenceSnapshot",
    "ExtractedContext",
    "ProjectionError",
    "OTelLogEmitter",
    "OTelMetricEmitter",
    "PropagationError",
    "SchemaValidator",
    "TelemetryClient",
    "TraceConfiguration",
    "TraceFinalizationError",
    "active_context_ids",
    "agt_approval_request",
    "agt_approval_resolution",
    "agt_policy_decision",
    "agt_policy_decision_record",
    "cedar_policy_decision",
    "extract_context",
    "inject_context",
    "opa_decision_log",
    "finalize_trace",
]

__version__ = "0.1.0.dev0"
