import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    ContextMismatchError,
    EventValidationError,
    SchemaValidator,
    TelemetryClient,
)


class FakeContext:
    is_valid = True
    trace_id = int("4bf92f3577b34da6a3ce929d0e0e4736", 16)
    span_id = int("00f067aa0ba902b7", 16)


class FakeSpan:
    def __init__(self, fail=False):
        self.events = []
        self.fail = fail

    def get_span_context(self):
        return FakeContext()

    def add_event(self, name, attributes, timestamp):
        if self.fail:
            raise RuntimeError("span unavailable")
        self.events.append((name, attributes, timestamp))


class FakeLogEmitter:
    def __init__(self, fail=False):
        self.records = []
        self.fail = fail

    def emit(self, record):
        if self.fail:
            raise RuntimeError("log unavailable")
        self.records.append(record)


def fixture(name):
    return json.loads((ROOT / "conformance" / "fixtures" / "valid" / name).read_text())


class SdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.validator = SchemaValidator(ROOT / "spec" / "schema")

    def test_emits_correlated_span_event_and_log(self):
        span = FakeSpan()
        logs = FakeLogEmitter()
        result = TelemetryClient(
            self.validator, span_resolver=lambda: span, log_emitter=logs
        ).emit(fixture("policy-decision.json"))
        self.assertTrue(result.span_event_emitted)
        self.assertTrue(result.log_emitted)
        self.assertEqual(result.context.trace_id, "4bf92f3577b34da6a3ce929d0e0e4736")
        self.assertEqual(span.events[0][0], "policy.decision")
        self.assertEqual(span.events[0][1]["gen_ai.agent.id"], "spiffe://example.test/agent/coder")
        self.assertNotIn("trace_id", span.events[0][1])
        self.assertEqual(logs.records[0]["trace_id"], result.context.trace_id)

    def test_no_span_still_emits_run_correlated_log(self):
        event = fixture("usage.json")
        logs = FakeLogEmitter()
        result = TelemetryClient(
            self.validator, span_resolver=lambda: None, log_emitter=logs
        ).emit(event)
        self.assertFalse(result.span_event_emitted)
        self.assertTrue(result.log_emitted)
        self.assertNotIn("trace_id", logs.records[0])
        self.assertEqual(logs.records[0]["body"]["run_id"], event["run_id"])

    def test_context_mismatch_rejects_before_projection(self):
        event = fixture("policy-decision.json")
        event["span_id"] = "1111111111111111"
        span = FakeSpan()
        logs = FakeLogEmitter()
        with self.assertRaises(ContextMismatchError):
            TelemetryClient(
                self.validator, span_resolver=lambda: span, log_emitter=logs
            ).emit(event)
        self.assertEqual(span.events, [])
        self.assertEqual(logs.records, [])

    def test_privacy_violation_rejects_before_projection(self):
        event = fixture("usage.json")
        event["attributes"] = {"vendor.safe": True}
        event["prompt"] = "sensitive"
        span = FakeSpan()
        with self.assertRaises(EventValidationError):
            TelemetryClient(self.validator, span_resolver=lambda: span).emit(event)
        self.assertEqual(span.events, [])

    def test_extension_attributes_are_deny_by_default(self):
        event = fixture("usage.json")
        event["attributes"] = {"vendor.note": "could contain raw content"}
        with self.assertRaisesRegex(EventValidationError, "attribute allowlist"):
            self.validator.validate(event)

    def test_explicit_attribute_allowlist_is_narrow(self):
        event = fixture("usage.json")
        event["attributes"] = {"vendor.reviewed": True}
        validator = SchemaValidator(
            ROOT / "spec" / "schema",
            allowed_attribute_keys=frozenset({"vendor.reviewed"}),
        )
        validator.validate(event)

    def test_projection_failures_are_reported_independently(self):
        result = TelemetryClient(
            self.validator,
            span_resolver=lambda: FakeSpan(fail=True),
            log_emitter=FakeLogEmitter(fail=True),
        ).emit(fixture("policy-decision.json"))
        self.assertTrue(result.accepted)
        self.assertFalse(result.span_event_emitted)
        self.assertFalse(result.log_emitted)
        self.assertEqual(len(result.projection_errors), 2)

    def test_log_body_is_a_deep_copy(self):
        event = fixture("usage.json")
        logs = FakeLogEmitter()
        TelemetryClient(
            self.validator, span_resolver=lambda: None, log_emitter=logs
        ).emit(event)
        event["run_id"] = "mutated"
        event["cost"]["amount"] = 999
        self.assertNotEqual(logs.records[0]["body"]["run_id"], "mutated")
        self.assertNotEqual(logs.records[0]["body"]["cost"]["amount"], 999)

    def test_bundled_schemas_match_normative_schemas(self):
        bundled = ROOT / "src" / "agentrust_telemetry" / "schemas"
        normative = ROOT / "spec" / "schema"
        self.assertEqual(
            {path.name for path in bundled.glob("*.schema.json")},
            {path.name for path in normative.glob("*.schema.json")},
        )
        for source in normative.glob("*.schema.json"):
            self.assertEqual(source.read_bytes(), (bundled / source.name).read_bytes())

    def test_real_otel_span_receives_event(self):
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import SimpleSpanProcessor
        from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

        exporter = InMemorySpanExporter()
        provider = TracerProvider()
        provider.add_span_processor(SimpleSpanProcessor(exporter))
        tracer = provider.get_tracer("agentrust-test")
        event = fixture("usage.json")
        event.pop("trace_id", None)
        event.pop("span_id", None)
        with tracer.start_as_current_span("invoke_agent coder"):
            result = TelemetryClient(SchemaValidator.bundled()).emit(event)
        spans = exporter.get_finished_spans()
        self.assertTrue(result.span_event_emitted)
        self.assertEqual(len(spans), 1)
        self.assertEqual(spans[0].events[0].name, "usage.recorded")
        self.assertEqual(spans[0].events[0].attributes["agentrust.run.id"], event["run_id"])


if __name__ == "__main__":
    unittest.main()
