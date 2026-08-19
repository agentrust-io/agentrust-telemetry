import sys
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AGT_MESH = ROOT.parent / "agent-governance-toolkit-audit" / "agent-governance-python" / "agent-mesh" / "src"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(AGT_MESH))

from agentrust_telemetry import (  # noqa: E402
    EventFactory,
    SchemaValidator,
    agt_approval_request,
    agt_approval_resolution,
    agt_policy_decision_record,
)

try:  # Local compatibility path; CI uses contract-equivalent fakes below.
    from agentmesh.governance.approval_protocol.models import (  # noqa: E402
        ApprovalRequest,
        ApprovalResolution,
        Outcome,
        PolicyDecisionRecord,
    )
except ImportError:
    from dataclasses import dataclass
    from enum import Enum

    class Outcome(str, Enum):
        ALLOW = "allow"
        DENY = "deny"
        EXPIRED = "expired"

    @dataclass
    class PolicyDecisionRecord:
        action_digest: str
        policy_rule_id: str
        policy_version: str
        approval_chain_id: str
        approval_chain_version: str
        verdict: str
        policy_decision_id: str
        decided_at: datetime

    @dataclass
    class ApprovalRequest:
        policy_decision_id: str
        action_digest: str
        agent_id: str
        operation: str
        policy_version: str
        approval_chain_id: str
        approval_chain_version: str
        expires_at: datetime
        approval_request_id: str
        requested_at: datetime

    @dataclass
    class ApprovalResolution:
        approval_request_id: str
        outcome: Outcome
        action_digest: str
        policy_version: str
        approval_chain_version: str
        approval_resolution_id: str
        resolved_at: datetime
        final_entry_digest: str | None = None


DIGEST = "sha256:" + "a" * 64
BUNDLE = {"algorithm": "sha256", "value": "b" * 64}
NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


class AgtApprovalAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = EventFactory(
            SchemaValidator(ROOT / "spec" / "schema"),
            producer_name="agt-approval-tests",
            producer_version="1.0.0",
        )

    def setUp(self):
        self.policy = PolicyDecisionRecord(
            action_digest=DIGEST,
            policy_rule_id="high-risk-tools",
            policy_version="7",
            approval_chain_id="operators",
            approval_chain_version="3",
            verdict="require_approval",
            policy_decision_id="pd_1",
            decided_at=NOW,
        )
        self.request = ApprovalRequest(
            policy_decision_id="pd_1",
            action_digest=DIGEST,
            agent_id="agent-1",
            operation="deploy",
            policy_version="7",
            approval_chain_id="operators",
            approval_chain_version="3",
            expires_at=NOW + timedelta(minutes=10),
            approval_request_id="ar_1",
            requested_at=NOW + timedelta(seconds=1),
        )
        self.resolution = ApprovalResolution(
            approval_request_id="ar_1",
            outcome=Outcome.ALLOW,
            action_digest=DIGEST,
            policy_version="7",
            approval_chain_version="3",
            approval_resolution_id="apr_1",
            resolved_at=NOW + timedelta(minutes=2),
            final_entry_digest="sha256:" + "c" * 64,
        )

    def test_protocol_chain_preserves_policy_request_and_resolution_links(self):
        policy = agt_policy_decision_record(
            self.factory,
            self.policy,
            run_id="run-1",
            agent_id="agent-1",
            action_type="deploy",
            resource_type="environment",
            policy_engine_version="1.0.0",
            bundle_digest=BUNDLE,
        )
        request = agt_approval_request(
            self.factory, self.request, self.policy, run_id="run-1"
        )
        resolution = agt_approval_resolution(
            self.factory, self.resolution, self.request, run_id="run-1"
        )
        self.assertEqual(policy["decision"], "challenge")
        self.assertEqual(request["policy_event_id"], policy["event_id"])
        self.assertEqual(resolution["policy_event_id"], policy["event_id"])
        self.assertEqual(resolution["approval_id"], request["approval_id"])
        self.assertEqual(resolution["event_type"], "approval.approved")
        self.assertEqual(resolution["approval_evidence_digest"]["value"], "c" * 64)

    def test_resolution_rejects_wrong_request_and_wrong_action(self):
        wrong_request = replace(self.resolution, approval_request_id="ar_other")
        with self.assertRaisesRegex(ValueError, "approval_request_id does not match"):
            agt_approval_resolution(
                self.factory, wrong_request, self.request, run_id="run-1"
            )

    def test_request_rejects_wrong_policy_action_and_chain(self):
        wrong_action = replace(self.request, action_digest="sha256:" + "d" * 64)
        with self.assertRaisesRegex(ValueError, "action_digest does not match"):
            agt_approval_request(
                self.factory, wrong_action, self.policy, run_id="run-1"
            )
        wrong_chain = replace(self.request, approval_chain_version="4")
        with self.assertRaisesRegex(ValueError, "approval_chain_version does not match"):
            agt_approval_request(
                self.factory, wrong_chain, self.policy, run_id="run-1"
            )
        wrong_action = replace(self.resolution, action_digest="sha256:" + "d" * 64)
        with self.assertRaisesRegex(ValueError, "action_digest does not match"):
            agt_approval_resolution(
                self.factory, wrong_action, self.request, run_id="run-1"
            )

    def test_resolution_rejects_pre_request_time_and_malformed_chain_digest(self):
        early = replace(self.resolution, resolved_at=NOW)
        with self.assertRaisesRegex(ValueError, "cannot predate"):
            agt_approval_resolution(self.factory, early, self.request, run_id="run-1")
        bad_digest = replace(self.resolution, final_entry_digest="not-a-digest")
        with self.assertRaisesRegex(ValueError, "sha256"):
            agt_approval_resolution(
                self.factory, bad_digest, self.request, run_id="run-1"
            )

    def test_terminal_outcomes_map_without_treating_votes_as_resolutions(self):
        for outcome, expected in (
            (Outcome.ALLOW, "approval.approved"),
            (Outcome.DENY, "approval.rejected"),
            (Outcome.EXPIRED, "approval.expired"),
        ):
            source = replace(self.resolution, outcome=outcome)
            event = agt_approval_resolution(
                self.factory, source, self.request, run_id="run-1"
            )
            self.assertEqual(event["event_type"], expected)


if __name__ == "__main__":
    unittest.main()
