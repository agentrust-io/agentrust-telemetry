import sys
import unittest
from datetime import datetime, timezone
from enum import IntEnum
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    ClassificationResult,
    DataEndpoint,
    EventFactory,
    SchemaValidator,
    agt_data_access_flow,
    classified_data_flow,
)


class RecordingClassifier:
    def __init__(self, result):
        self.result = result
        self.seen = None

    def classify(self, value):
        self.seen = value
        return self.result


class Level(IntEnum):
    CONFIDENTIAL = 2


class DataFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.factory = EventFactory(
            SchemaValidator(ROOT / "spec" / "schema"),
            producer_name="data-flow-tests",
            producer_version="1.0.0",
        )

    def test_classifier_sees_content_but_event_contains_only_closed_metadata(self):
        secret = {
            "prompt": "customer@example.test token=secret",
            "source_code": "print('private')",
        }
        classifier = RecordingClassifier(
            ClassificationResult("example.enterprise.v1", "confidential", "dlp.v2")
        )
        event = classified_data_flow(
            self.factory,
            classifier,
            secret,
            run_id="run-1",
            agent_id="agent-1",
            direction="read",
            source=DataEndpoint("repository", "application-source"),
            destination=DataEndpoint("agent", "builder"),
            purpose="architecture-generation",
            content_digest={"algorithm": "sha256", "value": "a" * 64},
            transformation="metadata_only",
        )
        self.assertIs(classifier.seen, secret)
        serialized = repr(event)
        for prohibited in ("customer@example", "token=secret", "source_code", "private"):
            self.assertNotIn(prohibited, serialized)

    def test_classifier_cannot_return_arbitrary_metadata(self):
        classifier = RecordingClassifier(
            {"taxonomy": "x", "value": "confidential", "prompt": "leak"}
        )
        with self.assertRaisesRegex(TypeError, "ClassificationResult"):
            classified_data_flow(
                self.factory,
                classifier,
                "secret",
                run_id="run-1",
                agent_id="agent-1",
                direction="read",
                source=DataEndpoint("repository"),
                destination=DataEndpoint("agent"),
                purpose="review",
            )

    def test_metadata_identifiers_reject_prose_paths_and_query_values(self):
        for value in (
            "customer secret text", "/customers/42.txt", "https://example.test/secret",
            "token=secret", "x?key=y",
        ):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "metadata identifier"):
                DataEndpoint("source", value)
        with self.assertRaisesRegex(ValueError, "metadata identifier"):
            ClassificationResult("example", "customer secret", "classifier")
        classifier = RecordingClassifier(
            ClassificationResult("example", "internal", "classifier")
        )
        with self.assertRaisesRegex(ValueError, "media_type"):
            classified_data_flow(
                self.factory,
                classifier,
                "secret",
                run_id="run-1",
                agent_id="agent-1",
                direction="read",
                source=DataEndpoint("repository"),
                destination=DataEndpoint("agent"),
                purpose="review",
                media_type="text/plain; token=secret",
            )

    def test_agt_decision_maps_tier_and_omits_categories_owner_geography_reason(self):
        label = SimpleNamespace(
            classification=Level.CONFIDENTIAL,
            categories=["PII", "customer@example.test"],
            owner="alice@example.test",
            geography="EU",
        )
        decision = SimpleNamespace(
            allowed=False,
            reason="SSN 123-45-6789 denied",
            agent_id="agent-1",
            data_label=label,
            matched_policy="agent-1",
            evaluated_at=datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc),
        )
        event = agt_data_access_flow(
            self.factory,
            decision,
            run_id="run-1",
            direction="read",
            source=DataEndpoint("database", "customer-records"),
            destination=DataEndpoint("agent", "builder"),
            purpose="requirements-analysis",
        )
        self.assertEqual(event["classification"]["value"], "confidential")
        self.assertEqual(event["policy_decision"], "deny")
        serialized = repr(event)
        for prohibited in ("PII", "customer@example", "alice@example", "123-45-6789", "geography"):
            self.assertNotIn(prohibited, serialized)

    def test_structured_agt_classification_is_a_value_error(self):
        from agentrust_telemetry import agt_data_classification

        for bad in ([], {}, [2]):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, "unsupported AGT data classification"):
                    agt_data_classification(SimpleNamespace(classification=bad))

    def test_data_flow_validates_endpoints_and_safe_integer_size_and_token_bounds(self):
        classifier = RecordingClassifier(
            ClassificationResult("example", "internal", "classifier")
        )
        # Valid boundary twins (0 and 2**53 - 1) succeed
        for valid_amount in (0, 2**53 - 1):
            ev = classified_data_flow(
                self.factory,
                classifier,
                "secret",
                run_id="run-1",
                agent_id="agent-1",
                direction="read",
                source=DataEndpoint("repository"),
                destination=DataEndpoint("agent"),
                purpose="review",
                size_bytes=valid_amount,
                token_count=valid_amount,
            )
            self.assertEqual(ev["size_bytes"], valid_amount)
            self.assertEqual(ev["token_count"], valid_amount)

        with self.assertRaisesRegex(TypeError, "source must be a DataEndpoint"):
            classified_data_flow(
                self.factory,
                classifier,
                "secret",
                run_id="run-1",
                agent_id="agent-1",
                direction="read",
                source={"kind": "repository"},  # type: ignore[arg-type]
                destination=DataEndpoint("agent"),
                purpose="review",
            )
        with self.assertRaisesRegex(TypeError, "destination must be a DataEndpoint"):
            classified_data_flow(
                self.factory,
                classifier,
                "secret",
                run_id="run-1",
                agent_id="agent-1",
                direction="read",
                source=DataEndpoint("repository"),
                destination={"kind": "agent"},  # type: ignore[arg-type]
                purpose="review",
            )

        for field_name in ("size_bytes", "token_count"):
            for bad_amount in (True, False, -1, 2**53, "10", 1.5):
                with self.subTest(field_name=field_name, bad_amount=bad_amount):
                    with self.assertRaisesRegex(ValueError, field_name):
                        classified_data_flow(
                            self.factory,
                            classifier,
                            "secret",
                            run_id="run-1",
                            agent_id="agent-1",
                            direction="read",
                            source=DataEndpoint("repository"),
                            destination=DataEndpoint("agent"),
                            purpose="review",
                            **{field_name: bad_amount},
                        )

    def test_propagation_rejects_control_characters(self):
        from agentrust_telemetry import PropagationError
        from agentrust_telemetry.propagation import _safe_value

        self.assertEqual(_safe_value("x-agentrust-run-id", "run-123_ok", required=True), "run-123_ok")
        for bad_val in ("run\x00bad", "run\x1fbad", "run\x7fbad", "run\tbad"):
            with self.subTest(bad_val=bad_val):
                with self.assertRaises(PropagationError):
                    _safe_value("x-agentrust-run-id", bad_val, required=True)

    def test_propagation_rejects_conflicting_duplicate_headers_and_accepts_identical_duplicates(self):
        from agentrust_telemetry import PropagationError
        from agentrust_telemetry.propagation import _header

        # Identical case-insensitive duplicate headers are accepted
        self.assertEqual(
            _header({"X-Agentrust-Run-Id": "run-1", "x-agentrust-run-id": "run-1"}, "x-agentrust-run-id"),
            "run-1",
        )
        # Conflicting case-insensitive duplicate headers are rejected
        with self.assertRaises(PropagationError):
            _header({"X-Agentrust-Run-Id": "run-1", "x-agentrust-run-id": "run-2"}, "x-agentrust-run-id")


if __name__ == "__main__":
    unittest.main()
