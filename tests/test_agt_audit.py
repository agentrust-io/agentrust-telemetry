import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    EventFactory,
    SchemaValidator,
    agt_audit_action,
    agt_audit_policy_decision,
)


NOW = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)
DIGEST = {"algorithm": "sha256", "value": "a" * 64}
BUNDLE = {"algorithm": "sha256", "value": "b" * 64}


def audit_entry(**overrides):
    values = {
        "entry_id": "audit_123",
        "timestamp": NOW,
        "issued_at": NOW - timedelta(milliseconds=5),
        "completed_at": NOW,
        "event_type": "policy_evaluation",
        "agent_did": "did:agt:agent-1",
        "action": "tool.invoke",
        "arguments_hash": "c" * 64,
        "resource": "/customer/42",
        "target_did": None,
        "data": {"prompt": "must not cross"},
        "outcome": "success",
        "policy_decision": "require_approval",
        "matched_rule": "high-risk-tools",
        "policy_version": "7",
        "entry_hash": "d" * 64,
        "previous_hash": "e" * 64,
        "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


class AgtAuditAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = EventFactory(
            SchemaValidator(ROOT / "spec" / "schema"),
            producer_name="agt-audit-tests",
            producer_version="1.0.0",
        )

    def test_policy_audit_maps_without_free_form_data_or_resource(self):
        event = agt_audit_policy_decision(
            self.factory,
            audit_entry(),
            run_id="run-1",
            policy_engine_version="5.0.0",
            bundle_digest=BUNDLE,
            resource_type="tool",
        )
        self.assertEqual(event["decision"], "challenge")
        self.assertEqual(event["policy"]["policy_id"], "high-risk-tools")
        serialized = repr(event)
        self.assertNotIn("/customer/42", serialized)
        self.assertNotIn("must not cross", serialized)
        self.assertNotIn("arguments_hash", serialized)
        self.assertNotIn("entry_hash", serialized)

    def test_action_audit_requires_full_action_digest_and_computes_duration(self):
        source = audit_entry(event_type="tool_invocation", policy_decision=None)
        event = agt_audit_action(
            self.factory,
            source,
            run_id="run-1",
            action_digest=DIGEST,
            action_kind="tool",
            operation="invoke",
        )
        self.assertEqual(event["duration_ns"], 5_000_000)
        self.assertEqual(event["action_digest"], DIGEST)
        self.assertNotEqual(event["action_digest"]["value"], source.arguments_hash)

    def test_blocked_action_is_denied_even_if_source_outcome_is_success(self):
        event = agt_audit_action(
            self.factory,
            audit_entry(event_type="tool_blocked", outcome="success"),
            run_id="run-1",
            action_digest=DIGEST,
            action_kind="tool",
            operation="invoke",
        )
        self.assertEqual(event["outcome"], "denied")

    def test_action_rejects_missing_or_reversed_timing(self):
        with self.assertRaisesRegex(ValueError, "requires duration_ns"):
            agt_audit_action(
                self.factory,
                audit_entry(event_type="tool_invocation", issued_at=None),
                run_id="run-1",
                action_digest=DIGEST,
                action_kind="tool",
                operation="invoke",
            )
        with self.assertRaisesRegex(ValueError, "cannot predate"):
            agt_audit_action(
                self.factory,
                audit_entry(
                    event_type="tool_invocation",
                    issued_at=NOW,
                    completed_at=NOW - timedelta(seconds=1),
                ),
                run_id="run-1",
                action_digest=DIGEST,
                action_kind="tool",
                operation="invoke",
            )


if __name__ == "__main__":
    unittest.main()
