"""Source adapters for normalized AgentTrust telemetry events."""

from .base import EventFactory
from .agt import AgtGovernanceEventSink, agt_policy_decision
from .agt_approval import (
    agt_approval_request,
    agt_approval_resolution,
    agt_policy_decision_record,
)
from .agt_audit import agt_audit_action, agt_audit_policy_decision
from .cedar import cedar_policy_decision
from .opa import opa_decision_log

__all__ = [
    "AgtGovernanceEventSink",
    "EventFactory",
    "agt_policy_decision",
    "agt_policy_decision_record",
    "agt_approval_request",
    "agt_approval_resolution",
    "agt_audit_action",
    "agt_audit_policy_decision",
    "cedar_policy_decision",
    "opa_decision_log",
]
