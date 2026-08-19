import json
import sys
import unittest
import uuid
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    EventFactory,
    SchemaValidator,
    cedar_policy_decision,
    opa_decision_log,
)


DIGEST = {"algorithm": "sha256", "value": "a" * 64}


class AdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = EventFactory(
            SchemaValidator(ROOT / "spec" / "schema"),
            producer_name="adapter-tests",
            producer_version="1.0.0",
            clock_ns=lambda: 1787079000000000000,
            event_id_factory=lambda: uuid.UUID("018f0f7d-7a13-7cc2-8000-000000000042"),
        )

    def test_factory_builds_and_validates_any_supported_family(self):
        event = self.factory.build(
            "usage.recorded",
            run_id="run-1",
            agent_id="agent-1",
            scope="workflow_run",
            operation="build",
            cost={"amount": 1.25, "currency": "USD", "source": "caller"},
        )
        self.assertEqual(event["event_id"], "018f0f7d-7a13-7cc2-8000-000000000042")
        self.assertEqual(event["producer"]["name"], "adapter-tests")
        self.assertEqual(event["time_unix_nano"], "1787079000000000000")

    def test_factory_prevents_envelope_override(self):
        with self.assertRaisesRegex(ValueError, "cannot override"):
            self.factory.build(
                "usage.recorded",
                run_id="run-1",
                agent_id="agent-1",
                scope="agent_run",
                operation="build",
                input_tokens=1,
                producer={"name": "spoofed", "version": "9"},
            )

    def test_factory_matches_cross_language_golden_event(self):
        parity_factory = EventFactory(
            SchemaValidator(ROOT / "spec" / "schema"),
            producer_name="parity-test", producer_version="1.0.0",
            clock_ns=lambda: 1787079000000000000,
            event_id_factory=lambda: uuid.UUID("018f0f7d-7a13-7cc2-8000-000000000042"),
        )
        event = parity_factory.build(
            "usage.recorded", run_id="run-1", agent_id="agent-1",
            workflow_id="workflow-1", scope="model_call", operation="chat",
            input_tokens=7,
        )
        expected = json.loads(
            (ROOT / "compatibility" / "golden" / "event-factory.json").read_text()
        )
        self.assertEqual(event, expected)

    def test_factory_serializes_nanoseconds_without_precision_loss(self):
        event = self.factory.build(
            "usage.recorded", run_id="run-1", agent_id="agent-1",
            scope="model_call", operation="chat", input_tokens=1,
            time_unix_nano="18446744073709551615",
        )
        self.assertEqual(event["time_unix_nano"], "18446744073709551615")
        with self.assertRaisesRegex(ValueError, "canonical"):
            self.factory.build(
                "usage.recorded", run_id="run-1", agent_id="agent-1",
                scope="model_call", operation="chat", input_tokens=1,
                time_unix_nano="01",
            )

    def test_opa_boolean_log_maps_without_copying_input_or_result(self):
        source = {
            "decision_id": "decision-123",
            "labels": {"version": "1.8.0"},
            "path": "/agents/allow",
            "input": {"secret": "must-not-copy"},
            "result": True,
            "timestamp": "2026-08-18T12:34:56.123456789Z",
            "metrics": {"timer_rego_query_eval_ns": 4200},
            "ids": ["allow-agent"],
            "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
            "span_id": "00f067aa0ba902b7",
        }
        event = opa_decision_log(
            self.factory,
            source,
            run_id="run-1",
            agent_id="agent-1",
            action_type="agent.invoke",
            resource_type="agent",
            bundle_digest=DIGEST,
        )
        self.assertEqual(event["decision"], "allow")
        self.assertEqual(event["time_unix_nano"], "1787056496123456789")
        self.assertEqual(event["evaluation_duration_ns"], 4200)
        self.assertNotIn("input", event)
        self.assertNotIn("result", event)
        self.assertEqual(event["reason_codes"], ["opa.rule:allow-agent"])

    def test_opa_complex_result_requires_explicit_mapper(self):
        source = {"decision_id": "d-1", "result": {"allow": True}}
        arguments = dict(
            run_id="run-1",
            agent_id="agent-1",
            action_type="agent.invoke",
            resource_type="agent",
            bundle_digest=DIGEST,
            opa_version="1.8.0",
        )
        with self.assertRaisesRegex(ValueError, "explicit result_mapper"):
            opa_decision_log(self.factory, source, **arguments)
        event = opa_decision_log(
            self.factory,
            source,
            result_mapper=lambda value: "allow" if value["allow"] else "deny",
            **arguments,
        )
        self.assertEqual(event["decision"], "allow")

    def test_opa_rejects_malformed_source_collections(self):
        arguments = dict(
            run_id="run-1",
            agent_id="agent-1",
            action_type="agent.invoke",
            resource_type="agent",
            bundle_digest=DIGEST,
            opa_version="1.8.0",
        )
        with self.assertRaisesRegex(ValueError, "metrics must be an object"):
            opa_decision_log(
                self.factory,
                {"decision_id": "d-1", "result": True, "metrics": []},
                **arguments,
            )
        with self.assertRaisesRegex(ValueError, "ids must be an array"):
            opa_decision_log(
                self.factory,
                {"decision_id": "d-1", "result": True, "ids": "permit"},
                **arguments,
            )

    def test_cedar_preserves_final_decision_and_reports_skipped_errors(self):
        event = cedar_policy_decision(
            self.factory,
            run_id="run-1",
            agent_id="agent-1",
            decision="Allow",
            cedar_version="4.11.2",
            bundle_digest=DIGEST,
            action_type="Document::read",
            resource_type="Document",
            evaluation_duration_ns=900,
            determining_policy_ids=["permit-read"],
            error_codes=["entity_attribute_missing"],
        )
        self.assertEqual(event["decision"], "allow")
        self.assertEqual(event["policy"]["policy_id"], "permit-read")
        self.assertEqual(
            event["reason_codes"],
            ["cedar.policy:permit-read", "cedar.error:entity_attribute_missing"],
        )

    def test_cedar_rejects_error_messages_as_codes(self):
        with self.assertRaisesRegex(ValueError, "not error messages"):
            cedar_policy_decision(
                self.factory,
                run_id="run-1",
                agent_id="agent-1",
                decision="Deny",
                cedar_version="4.11.2",
                bundle_digest=DIGEST,
                action_type="Document::read",
                resource_type="Document",
                evaluation_duration_ns=1,
                error_codes=["failed to read secret /customer/42"],
            )

    def test_cedar_rejects_string_as_identifier_collection(self):
        with self.assertRaisesRegex(ValueError, "iterable of strings"):
            cedar_policy_decision(
                self.factory,
                run_id="run-1",
                agent_id="agent-1",
                decision="Deny",
                cedar_version="4.11.2",
                bundle_digest=DIGEST,
                action_type="Document::read",
                resource_type="Document",
                evaluation_duration_ns=1,
                determining_policy_ids="deny-secret",
            )


if __name__ == "__main__":
    unittest.main()
