import copy
import json
import sys
import unittest
from collections.abc import Sequence
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
    EventValidationError,
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


    def test_derived_flow_inherits_strictest_source_classification(self):
        from agentrust_telemetry import ClassificationOrder, SourceClassification

        taxonomy = "example.enterprise.v1"
        order = ClassificationOrder(
            taxonomy, ("public", "internal", "confidential", "restricted")
        )
        observed = ClassificationResult(taxonomy, "public", "output-dlp")
        classifier = RecordingClassifier(observed)
        event = classified_data_flow(
            self.factory, classifier, "summary text",
            run_id="run-1", agent_id="agent-1", direction="output",
            source=DataEndpoint("transform", "summarizer"),
            destination=DataEndpoint("memory", "summary-1"),
            purpose="memory-compaction", transformation="aggregated",
            source_classifications=[
                SourceClassification(DataEndpoint("document", "public-faq"),
                    ClassificationResult(taxonomy, "public", "source-dlp")),
                SourceClassification(DataEndpoint("document", "staff-notes"),
                    ClassificationResult(taxonomy, "confidential", "trusted-label-store")),
            ],
            classification_order=order,
        )
        self.assertEqual(event["classification"]["value"], "confidential")
        self.assertEqual(event["observed_classification"]["value"], "public")
        self.assertEqual(len(event["source_classifications"]), 2)
        self.assertNotIn("summary text", repr(event))

    def test_derived_flow_requires_complete_unique_same_taxonomy_lineage(self):
        from agentrust_telemetry import ClassificationOrder, SourceClassification

        taxonomy = "example.enterprise.v1"
        order = ClassificationOrder(taxonomy, ("public", "confidential"))
        common = dict(
            run_id="run-1", agent_id="agent-1", direction="output",
            source=DataEndpoint("transform"), destination=DataEndpoint("memory"),
            purpose="memory-compaction",
        )
        classifier = RecordingClassifier(ClassificationResult(taxonomy, "public", "dlp"))
        with self.assertRaisesRegex(ValueError, "supplied together"):
            classified_data_flow(self.factory, classifier, "summary", **common,
                source_classifications=[],)
        with self.assertRaisesRegex(ValueError, "at least one source"):
            classified_data_flow(self.factory, classifier, "summary", **common,
                source_classifications=[], classification_order=order)
        duplicate = SourceClassification(DataEndpoint("document", "same"),
            ClassificationResult(taxonomy, "confidential", "dlp"))
        with self.assertRaisesRegex(ValueError, "duplicate source"):
            classified_data_flow(self.factory, classifier, "summary", **common,
                source_classifications=[duplicate, duplicate], classification_order=order)
        wrong_taxonomy = SourceClassification(DataEndpoint("document", "other"),
            ClassificationResult("example.other.v1", "confidential", "dlp"))
        with self.assertRaisesRegex(ValueError, "taxonomy mismatch"):
            classified_data_flow(self.factory, classifier, "summary", **common,
                source_classifications=[wrong_taxonomy], classification_order=order)

        unknown = SourceClassification(DataEndpoint("document", "unknown"),
            ClassificationResult(taxonomy, "top_secret", "dlp"))
        with self.assertRaisesRegex(ValueError, "unknown classification value"):
            classified_data_flow(self.factory, classifier, "summary", **common,
                source_classifications=[unknown], classification_order=order)

        too_many = (SourceClassification(DataEndpoint("document", f"source-{i}"),
            ClassificationResult(taxonomy, "public", "dlp")) for i in range(1025))
        with self.assertRaisesRegex(ValueError, "at most 1024"):
            classified_data_flow(self.factory, classifier, "summary", **common,
                source_classifications=too_many, classification_order=order)

        exactly_limit = [
            SourceClassification(
                DataEndpoint("document", f"source-{i}"),
                ClassificationResult(taxonomy, "public", "dlp"),
            )
            for i in range(1024)
        ]
        at_limit = classified_data_flow(
            self.factory, classifier, "summary", **common,
            source_classifications=exactly_limit, classification_order=order,
        )
        self.assertEqual(len(at_limit["source_classifications"]), 1024)


    def test_output_classification_is_not_downgraded_and_wins_ties(self):
        from agentrust_telemetry import ClassificationOrder, SourceClassification

        taxonomy = "example.enterprise.v1"
        order = ClassificationOrder(taxonomy, ("public", "confidential", "restricted"))
        source = SourceClassification(
            DataEndpoint("document", "staff-notes"),
            ClassificationResult(taxonomy, "confidential", "trusted-label-store"),
        )
        common = dict(
            run_id="run-1", agent_id="agent-1", direction="output",
            source=DataEndpoint("transform", "summarizer"),
            destination=DataEndpoint("memory", "summary-1"),
            purpose="memory-compaction",
            source_classifications=[source],
            classification_order=order,
        )

        stricter_output = ClassificationResult(taxonomy, "restricted", "output-dlp")
        event = classified_data_flow(
            self.factory, RecordingClassifier(stricter_output), "summary", **common
        )
        self.assertEqual(event["classification"]["value"], "restricted")
        self.assertEqual(event["classification"]["producer"], "output-dlp")

        tied_output = ClassificationResult(taxonomy, "confidential", "output-dlp")
        tied_event = classified_data_flow(
            self.factory, RecordingClassifier(tied_output), "summary", **common
        )
        self.assertEqual(tied_event["classification"]["value"], "confidential")
        self.assertEqual(tied_event["classification"]["producer"], "output-dlp")


    def test_classification_order_accepts_general_string_sequences(self):
        class Levels(Sequence):
            def __getitem__(self, index):
                return ("public", "confidential")[index]

            def __len__(self):
                return 2

        from agentrust_telemetry import ClassificationOrder

        order = ClassificationOrder("example.enterprise.v1", Levels())
        self.assertEqual(
            order.rank(ClassificationResult("example.enterprise.v1", "confidential", "dlp")),
            1,
        )

    def test_cheap_lineage_and_size_checks_precede_classifier(self):
        from agentrust_telemetry import ClassificationOrder, SourceClassification

        taxonomy = "example.enterprise.v1"
        classifier = RecordingClassifier(ClassificationResult(taxonomy, "public", "dlp"))
        duplicate = SourceClassification(
            DataEndpoint("document", "same"),
            ClassificationResult(taxonomy, "confidential", "trusted-store"),
        )
        common = dict(
            run_id="run-1", agent_id="agent-1", direction="output",
            source=DataEndpoint("transform"), destination=DataEndpoint("memory"),
            purpose="memory-compaction",
        )
        order = ClassificationOrder(taxonomy, ("public", "confidential"))
        with self.assertRaisesRegex(ValueError, "duplicate source"):
            classified_data_flow(
                self.factory, classifier, "summary", **common,
                source_classifications=(duplicate for _ in range(2)),
                classification_order=order,
            )
        self.assertIsNone(classifier.seen)

        with self.assertRaisesRegex(ValueError, "safe integer"):
            classified_data_flow(
                self.factory, classifier, "summary", **common,
                size_bytes=9007199254740992,
            )
        self.assertIsNone(classifier.seen)

    def test_schema_validator_enforces_lineage_identifier_and_safe_integer_rules(self):
        validator = SchemaValidator(ROOT / "spec" / "schema")
        fixture_path = ROOT / "conformance" / "fixtures" / "valid" / "derived-data-flow.json"
        event = json.loads(fixture_path.read_text(encoding="utf-8"))

        duplicate = copy.deepcopy(event)
        duplicate["source_classifications"][1]["source"] = copy.deepcopy(
            duplicate["source_classifications"][0]["source"]
        )
        with self.assertRaisesRegex(EventValidationError, "duplicates a prior"):
            validator.validate(duplicate)

        mixed = copy.deepcopy(event)
        mixed["source_classifications"][0]["classification"]["taxonomy"] = "other.taxonomy"
        with self.assertRaisesRegex(EventValidationError, "same taxonomy"):
            validator.validate(mixed)

        invalid_identifier = copy.deepcopy(event)
        invalid_identifier["source_classifications"][0]["source"]["kind"] = "customer data"
        with self.assertRaisesRegex(EventValidationError, "metadata identifier profile"):
            validator.validate(invalid_identifier)

        unsafe_integer = copy.deepcopy(event)
        unsafe_integer["size_bytes"] = 9007199254740992
        with self.assertRaises(EventValidationError):
            validator.validate(unsafe_integer)



    def test_derived_flow_matches_shared_cross_language_golden(self):
        from agentrust_telemetry import ClassificationOrder, SourceClassification

        expected = json.loads(
            (ROOT / "compatibility" / "golden" / "derived-data-flow.json").read_text(
                encoding="utf-8"
            )
        )
        factory = EventFactory(
            SchemaValidator(ROOT / "spec" / "schema"),
            producer_name="derived-flow-golden",
            producer_version="1.0.0",
            clock_ns=lambda: 1,
            event_id_factory=lambda: "018f0f7d-7a13-7cc2-8000-000000000042",
        )
        taxonomy = "example.enterprise.v1"
        event = classified_data_flow(
            factory,
            RecordingClassifier(ClassificationResult(taxonomy, "public", "output-dlp")),
            "summary",
            run_id="run-golden-derived-flow",
            agent_id="agent-1",
            direction="output",
            source=DataEndpoint("transform", "summarizer"),
            destination=DataEndpoint("memory", "summary-1"),
            purpose="memory-compaction",
            policy_decision="allow",
            transformation="aggregated",
            source_classifications=[
                SourceClassification(
                    DataEndpoint("knowledge_graph", "public-faq"),
                    ClassificationResult(taxonomy, "public", "source-dlp"),
                ),
                SourceClassification(
                    DataEndpoint("document", "staff-notes"),
                    ClassificationResult(taxonomy, "confidential", "trusted-label-store"),
                ),
            ],
            classification_order=ClassificationOrder(
                taxonomy, ("public", "internal", "confidential", "restricted")
            ),
            event_id="018f0f7d-7a13-7cc2-8000-000000000042",
            time_unix_nano="1787079400000000000",
        )
        self.assertEqual(event, expected)



if __name__ == "__main__":
    unittest.main()
