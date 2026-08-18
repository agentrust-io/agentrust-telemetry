import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    EvidenceAccumulator,
    EvidenceError,
    EvidencePersistenceError,
    SchemaValidator,
    TelemetryClient,
)


def fixture(name):
    return json.loads((ROOT / "conformance" / "fixtures" / "valid" / name).read_text())


class RecordingSpan:
    def __init__(self):
        self.events = []

    def get_span_context(self):
        return type("Context", (), {"is_valid": False})()

    def add_event(self, name, attributes, timestamp):
        self.events.append(name)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.validator = SchemaValidator(ROOT / "spec" / "schema")

    def test_chain_is_ordered_and_has_stable_golden_digest(self):
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        first = accumulator.append(fixture("policy-decision.json"))
        second = accumulator.append(fixture("usage.json"))

        self.assertEqual(first.sequence, 0)
        self.assertIsNone(first.previous_digest)
        self.assertEqual(second.sequence, 1)
        self.assertEqual(second.previous_digest, first.digest)
        self.assertEqual(
            second.digest,
            "e6a03fca3d030c9c0295251fe5feaa467f32df5b3a8ec6b070dd179f3156fc10",
        )

    def test_durable_callback_acknowledges_before_local_acceptance(self):
        durable = []

        def append(entry):
            durable.append(entry)
            return True

        accumulator = EvidenceAccumulator(
            "run-governed-sdlc-001", self.validator, durable_append=append
        )
        accepted = accumulator.append(fixture("policy-decision.json"))
        self.assertEqual(accumulator.mode, "callback")
        self.assertEqual(durable, [accepted])
        self.assertEqual(accumulator.snapshot().entries, (accepted,))

    def test_failed_durable_ack_is_fail_closed_and_retryable(self):
        acknowledgements = iter([False, True])
        accumulator = EvidenceAccumulator(
            "run-governed-sdlc-001",
            self.validator,
            durable_append=lambda entry: next(acknowledgements),
        )
        event = fixture("policy-decision.json")
        with self.assertRaises(EvidencePersistenceError):
            accumulator.append(event)
        self.assertEqual(accumulator.snapshot().entries, ())
        self.assertEqual(accumulator.append(event).sequence, 0)

    def test_client_does_not_project_when_evidence_fails(self):
        accumulator = EvidenceAccumulator(
            "run-governed-sdlc-001",
            self.validator,
            durable_append=lambda entry: False,
        )
        span = RecordingSpan()
        with self.assertRaises(EvidencePersistenceError):
            TelemetryClient(
                self.validator,
                span_resolver=lambda: span,
                evidence_sink=accumulator,
            ).emit(fixture("policy-decision.json"))
        self.assertEqual(span.events, [])

    def test_client_reports_evidence_persistence(self):
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        result = TelemetryClient(
            self.validator, span_resolver=lambda: None, evidence_sink=accumulator
        ).emit(fixture("policy-decision.json"))
        self.assertTrue(result.evidence_persisted)
        self.assertEqual(len(accumulator.snapshot().entries), 1)

    def test_client_isolates_operational_event_from_evidence_sink(self):
        class MutatingSink:
            def append(self, event):
                event["run_id"] = "mutated-by-sink"

        event = fixture("usage.json")
        TelemetryClient(
            self.validator, span_resolver=lambda: None, evidence_sink=MutatingSink()
        ).emit(event)
        self.assertEqual(event["run_id"], "run-governed-sdlc-001")

    def test_non_finite_number_cannot_enter_digest_chain(self):
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        event = fixture("usage.json")
        event["cost"]["amount"] = float("nan")
        with self.assertRaisesRegex(EvidenceError, "cannot be canonicalized"):
            accumulator.append(event)
        self.assertEqual(accumulator.snapshot().entries, ())

    def test_rejects_cross_run_duplicate_overflow_and_append_after_seal(self):
        accumulator = EvidenceAccumulator(
            "run-governed-sdlc-001", self.validator, max_events=1
        )
        event = fixture("policy-decision.json")
        wrong_run = fixture("usage.json")
        wrong_run["run_id"] = "another-run"
        with self.assertRaisesRegex(EvidenceError, "does not match"):
            accumulator.append(wrong_run)
        accumulator.append(event)
        with self.assertRaisesRegex(EvidenceError, "duplicate"):
            accumulator.append(event)

        full = fixture("usage.json")
        with self.assertRaisesRegex(EvidenceError, "max_events"):
            accumulator.append(full)
        snapshot = accumulator.seal(completeness="incomplete")
        self.assertTrue(snapshot.sealed)
        self.assertEqual(snapshot.completeness, "incomplete")
        with self.assertRaisesRegex(EvidenceError, "sealed"):
            accumulator.append(full)

    def test_snapshot_is_defensive_and_unsealed_never_claims_complete(self):
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        accumulator.append(fixture("usage.json"))
        snapshot = accumulator.snapshot()
        snapshot.entries[0].event["run_id"] = "mutated"
        fresh = accumulator.snapshot()
        self.assertEqual(fresh.completeness, "unknown")
        self.assertEqual(fresh.entries[0].event["run_id"], "run-governed-sdlc-001")

    def test_callback_and_returned_entry_cannot_mutate_retained_evidence(self):
        callback_entries = []

        def append(entry):
            callback_entries.append(entry)
            entry.event["run_id"] = "callback-mutated"
            return True

        accumulator = EvidenceAccumulator(
            "run-governed-sdlc-001", self.validator, durable_append=append
        )
        returned = accumulator.append(fixture("usage.json"))
        returned.event["run_id"] = "caller-mutated"
        retained = accumulator.snapshot().entries[0]
        self.assertEqual(retained.event["run_id"], "run-governed-sdlc-001")
        self.assertNotEqual(callback_entries[0].event["run_id"], retained.event["run_id"])


if __name__ == "__main__":
    unittest.main()
