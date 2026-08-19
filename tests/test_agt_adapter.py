import sys
import unittest
import uuid
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    AgtGovernanceEventSink,
    EventFactory,
    SchemaValidator,
    agt_policy_decision,
)


DIGEST = {"algorithm": "sha256", "value": "b" * 64}


class Kind(str, Enum):
    POLICY_CHECK = "policy_check"


@dataclass
class FakeAgtEvent:
    event_id: str = "018f0f7d7a137cc28000000000000042"
    occurred_at: str = "2026-08-18T12:34:56.123456789+00:00"
    kind: Kind = Kind.POLICY_CHECK
    agent_id: str = "agent-1"
    action: str = "tool.invoke"
    decision: str = "require_approval"
    reason: str = "secret customer text must not cross the boundary"
    resource: str = "/customer/42"
    policy_name: str = "tool-policy"
    latency_ms: float = 1.25
    trace_id: str = "4bf92f3577b34da6a3ce929d0e0e4736"
    span_id: str = "00f067aa0ba902b7"
    attributes: dict = field(
        default_factory=lambda: {
            "resource_type": "tool",
            "reason_codes": ["approval.required"],
            "prompt": "must not copy",
        }
    )


class Result(Enum):
    SUCCESS = 0
    FAILURE = 1


class RecordingClient:
    def __init__(self, *, errors=()):
        self.events = []
        self.errors = errors

    def emit(self, event):
        self.events.append(event)
        return SimpleNamespace(accepted=True, projection_errors=self.errors)


class AgtAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = EventFactory(
            SchemaValidator(ROOT / "spec" / "schema"),
            producer_name="agt-bridge-tests",
            producer_version="1.0.0",
        )

    def map(self, source):
        return [
            agt_policy_decision(
                self.factory,
                source,
                run_id="run-1",
                policy_engine_version="1.2.3",
                bundle_digest=DIGEST,
            )
        ]

    def test_policy_event_maps_challenge_and_excludes_free_form_content(self):
        event = self.map(FakeAgtEvent())[0]
        self.assertEqual(event["decision"], "challenge")
        self.assertEqual(event["event_id"], "018f0f7d-7a13-7cc2-8000-000000000042")
        self.assertEqual(event["time_unix_nano"], "1787056496123456789")
        self.assertEqual(event["evaluation_duration_ns"], 1_250_000)
        self.assertEqual(event["reason_codes"], ["approval.required"])
        serialized = repr(event)
        self.assertNotIn("secret customer", serialized)
        self.assertNotIn("/customer/42", serialized)
        self.assertNotIn("must not copy", serialized)

    def test_policy_mapper_rejects_ambiguous_decision_and_reason_message(self):
        with self.assertRaisesRegex(ValueError, "unsupported AGT policy decision"):
            self.map(FakeAgtEvent(decision="warn"))
        with self.assertRaisesRegex(ValueError, "at most 32 identifiers"):
            self.map(
                FakeAgtEvent(
                    attributes={
                        "resource_type": "tool",
                        "reason_codes": ["customer 42 denied because secret"],
                    }
                )
            )

    def test_sink_prevalidates_whole_batch_before_emission(self):
        client = RecordingClient()
        sink = AgtGovernanceEventSink(
            client,
            self.map,
            success_result=Result.SUCCESS,
            failure_result=Result.FAILURE,
        )
        result = sink.emit([FakeAgtEvent(), FakeAgtEvent(decision="unknown")])
        self.assertEqual(result, Result.FAILURE)
        self.assertEqual(client.events, [])

    def test_sink_uses_source_result_sentinels_and_reports_projection_failure(self):
        successful = RecordingClient()
        sink = AgtGovernanceEventSink(
            successful,
            self.map,
            success_result=Result.SUCCESS,
            failure_result=Result.FAILURE,
        )
        self.assertEqual(sink.emit([FakeAgtEvent()]), Result.SUCCESS)
        self.assertEqual(len(successful.events), 1)

        failing = RecordingClient(errors=("log projection failed",))
        sink = AgtGovernanceEventSink(
            failing,
            self.map,
            success_result=Result.SUCCESS,
            failure_result=Result.FAILURE,
        )
        self.assertEqual(sink.emit([FakeAgtEvent()]), Result.FAILURE)


if __name__ == "__main__":
    unittest.main()
