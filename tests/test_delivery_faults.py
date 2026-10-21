"""Operational delivery and evidence acceptance are different boundaries."""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    EvidenceAccumulator, EvidenceError, EvidencePersistenceError,
    SchemaValidator, TelemetryClient,
)


def fixture(name):
    return json.loads((ROOT / "conformance/fixtures/valid" / name).read_text())


class DeliveryFaultTests(unittest.TestCase):
    def test_shared_delivery_matrix_preserves_evidence_and_unknown_completeness(self):
        matrix = json.loads((ROOT / "compatibility/golden/delivery-faults.json").read_text())
        golden = json.loads((ROOT / "compatibility/golden/evidence-chain.json").read_text())
        for case in matrix["cases"]:
            with self.subTest(mode=case["mode"]):
                observed = []

                class Emitter:
                    def emit(self, record):
                        if case["mode"] == "raise":
                            raise RuntimeError("synthetic delivery failure")
                        if case["mode"] == "drop":
                            return
                        if case["mode"] == "reverse":
                            observed.insert(0, record)
                        else:
                            observed.append(record)
                            if case["mode"] == "duplicate":
                                observed.append(record)

                validator = SchemaValidator.bundled()
                evidence = EvidenceAccumulator(golden["run_id"], validator)
                client = TelemetryClient(validator, span_resolver=lambda: None,
                                         evidence_sink=evidence, log_emitter=Emitter())
                events = [fixture(name) for name in matrix["fixtures"]]
                for event in events:
                    result = client.emit(event)
                    self.assertTrue(result.accepted)
                    self.assertTrue(result.evidence_persisted)
                    self.assertEqual(result.log_emitted, case["log_emitted"])
                    self.assertEqual(len(result.projection_errors), case["error_count"])
                snapshot = evidence.snapshot()
                self.assertEqual([e.digest for e in snapshot.entries],
                                 [e["digest"] for e in golden["entries"]])
                self.assertEqual([r["body"]["event_id"] for r in observed],
                                 [events[i]["event_id"] for i in case["delivered_indices"]])
                self.assertEqual(snapshot.completeness, "unknown")
                self.assertFalse(snapshot.sealed)
                self.assertEqual(evidence.seal(completeness="unknown").completeness, "unknown")

    def test_committed_but_unacknowledged_event_retries_without_double_projection(self):
        for failure in ("false", "exception"):
            with self.subTest(failure=failure):
                # Test double for an idempotent adopter store, not durable storage.
                committed = {}
                attempts = []
                projections = []

                def append(entry):
                    attempts.append(entry)
                    old = committed.setdefault(entry.event_id, entry)
                    if old != entry:
                        raise ValueError("conflicting retry")
                    if len(attempts) == 1:
                        if failure == "exception":
                            raise TimeoutError("commit happened; acknowledgement lost")
                        return False
                    return True

                class Emitter:
                    def emit(self, record):
                        projections.append(record)

                validator = SchemaValidator.bundled()
                event = fixture("policy-decision.json")
                evidence = EvidenceAccumulator(event["run_id"], validator, durable_append=append)
                client = TelemetryClient(validator, span_resolver=lambda: None,
                                         evidence_sink=evidence, log_emitter=Emitter())
                with self.assertRaises(EvidencePersistenceError):
                    client.emit(event)
                self.assertEqual(len(committed), 1)
                self.assertEqual(evidence.snapshot().entries, ())
                self.assertEqual(projections, [])
                self.assertTrue(client.emit(event).evidence_persisted)
                self.assertEqual(attempts[0], attempts[1])
                self.assertEqual(len(committed), 1)
                self.assertEqual(len(evidence.snapshot().entries), 1)
                self.assertEqual(len(projections), 1)
                with self.assertRaises(EvidenceError):
                    client.emit(event)
                self.assertEqual(len(attempts), 2)
                self.assertEqual(len(projections), 1)

    def test_real_otel_sampling_and_export_failure_do_not_prove_delivery(self):
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExporter, SpanExportResult
        from opentelemetry.sdk.trace.sampling import ALWAYS_OFF, ALWAYS_ON

        for sampled in (False, True):
            with self.subTest(sampled=sampled):
                exported = []

                class FailingExporter(SpanExporter):
                    def export(self, spans):
                        exported.extend(spans)
                        return SpanExportResult.FAILURE

                provider = TracerProvider(sampler=ALWAYS_ON if sampled else ALWAYS_OFF)
                provider.add_span_processor(SimpleSpanProcessor(FailingExporter()))
                try:
                    validator = SchemaValidator.bundled()
                    event = fixture("usage.json")
                    event.pop("trace_id", None)
                    event.pop("span_id", None)
                    evidence = EvidenceAccumulator(event["run_id"], validator)
                    with provider.get_tracer("delivery-test").start_as_current_span("step"):
                        result = TelemetryClient(validator, evidence_sink=evidence).emit(event)
                    self.assertTrue(result.evidence_persisted)
                    self.assertEqual(len(evidence.snapshot().entries), 1)
                    self.assertEqual(evidence.snapshot().completeness, "unknown")
                    self.assertEqual(len(exported), int(sampled))
                    if sampled:
                        self.assertEqual(len(exported[0].events), 1)
                    # add_event returning is not collector acknowledgement.
                    self.assertTrue(result.span_event_emitted)
                    self.assertEqual(result.projection_errors, ())
                finally:
                    provider.shutdown()
