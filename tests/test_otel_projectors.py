import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    OTelLogEmitter,
    OTelMetricEmitter,
    SchemaValidator,
    TelemetryClient,
)


def fixture(name):
    return json.loads((ROOT / "conformance" / "fixtures" / "valid" / name).read_text())


class OTelProjectorTests(unittest.TestCase):
    def test_real_otel_log_preserves_event_and_active_trace_context(self):
        from opentelemetry.sdk._logs import LoggerProvider
        from opentelemetry.sdk._logs.export import (
            InMemoryLogRecordExporter,
            SimpleLogRecordProcessor,
        )
        from opentelemetry.sdk.trace import TracerProvider

        exporter = InMemoryLogRecordExporter()
        logger_provider = LoggerProvider()
        logger_provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
        logger = logger_provider.get_logger("agentrust-test")
        tracer = TracerProvider().get_tracer("agentrust-test")
        event = fixture("usage.json")
        event.pop("trace_id", None)
        event.pop("span_id", None)
        with tracer.start_as_current_span("agent") as span:
            result = TelemetryClient(
                SchemaValidator.bundled(), log_emitter=OTelLogEmitter(logger)
            ).emit(event)

        records = exporter.get_finished_logs()
        self.assertTrue(result.log_emitted)
        self.assertEqual(len(records), 1)
        record = records[0].log_record
        self.assertEqual(record.event_name, "usage.recorded")
        self.assertEqual(record.body["run_id"], event["run_id"])
        self.assertEqual(record.trace_id, span.get_span_context().trace_id)
        self.assertEqual(record.attributes["agentrust.run.id"], event["run_id"])

    def test_real_metrics_record_usage_without_high_cardinality_ids(self):
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader

        reader = InMemoryMetricReader()
        meter = MeterProvider(metric_readers=[reader]).get_meter("agentrust-test")
        emitter = OTelMetricEmitter(meter)
        result = TelemetryClient(
            SchemaValidator.bundled(),
            span_resolver=lambda: None,
            metric_emitter=emitter,
        ).emit(fixture("usage.json"))
        self.assertTrue(result.metrics_emitted)

        metrics = reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
        by_name = {metric.name: metric for metric in metrics}
        self.assertEqual(
            sum(point.value for point in by_name["agentrust.usage.tokens"].data.data_points),
            5012,
        )
        cost_point = by_name["agentrust.usage.cost"].data.data_points[0]
        self.assertEqual(cost_point.value, 0.0124)
        forbidden = {
            "agentrust.run.id",
            "agentrust.workflow.id",
            "agentrust.event.id",
            "gen_ai.agent.id",
        }
        for metric in metrics:
            for point in metric.data.data_points:
                self.assertTrue(forbidden.isdisjoint(point.attributes))

    def test_classification_metric_is_allowlisted_or_collapsed(self):
        class Counter:
            def __init__(self):
                self.calls = []

            def add(self, value, attributes):
                self.calls.append((value, attributes))

        class Instrument:
            def add(self, value, attributes):
                pass

            def record(self, value, attributes):
                pass

        class Meter:
            def __init__(self):
                self.counters = []

            def create_counter(self, *args, **kwargs):
                counter = Counter() if args[0] == "agentrust.data_flow.events" else Instrument()
                self.counters.append((args[0], counter))
                return counter

            def create_histogram(self, *args, **kwargs):
                return Instrument()

        meter = Meter()
        emitter = OTelMetricEmitter(meter, classification_values=frozenset({"public"}))
        emitter.emit(fixture("data-flow.json"))
        counter = dict(meter.counters)["agentrust.data_flow.events"]
        self.assertEqual(
            counter.calls[0][1]["agentrust.data_flow.classification"], "_other"
        )

    def test_metric_failure_is_reported_independently(self):
        class FailingMetrics:
            def emit(self, event):
                raise RuntimeError("metrics unavailable")

        result = TelemetryClient(
            SchemaValidator.bundled(),
            span_resolver=lambda: None,
            metric_emitter=FailingMetrics(),
        ).emit(fixture("approval.json"))
        self.assertFalse(result.metrics_emitted)
        self.assertIn("metric projection failed", result.projection_errors[0])

    def test_classification_allowlist_is_bounded(self):
        class Meter:
            def create_counter(self, *args, **kwargs):
                return object()

            def create_histogram(self, *args, **kwargs):
                return object()

        with self.assertRaisesRegex(ValueError, "more than 64"):
            OTelMetricEmitter(
                Meter(), classification_values=frozenset(f"class-{i}" for i in range(65))
            )

    def test_action_metrics_exclude_action_and_agent_identifiers(self):
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import InMemoryMetricReader

        reader = InMemoryMetricReader()
        meter = MeterProvider(metric_readers=[reader]).get_meter("agentrust-action-test")
        emitter = OTelMetricEmitter(meter)
        self.assertTrue(emitter.emit(fixture("action.json")))
        metrics = reader.get_metrics_data().resource_metrics[0].scope_metrics[0].metrics
        for metric in metrics:
            for point in metric.data.data_points:
                self.assertEqual(
                    set(point.attributes),
                    {"agentrust.action.kind", "agentrust.action.outcome"},
                )


if __name__ == "__main__":
    unittest.main()
