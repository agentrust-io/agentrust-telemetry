import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    PropagationError,
    extract_context,
    inject_context,
)


class PropagationTests(unittest.TestCase):
    def setUp(self):
        from opentelemetry.sdk.trace import TracerProvider

        self.provider = TracerProvider()
        self.tracer = self.provider.get_tracer("agentrust-propagation-test")

    def test_sync_handoff_preserves_trace_and_agent_parent(self):
        from opentelemetry import trace

        carrier = {}
        with self.tracer.start_as_current_span("agent-a") as upstream:
            inject_context(
                carrier,
                run_id="run-123",
                workflow_id="workflow-456",
                agent_id="agent-a",
            )
            upstream_trace_id = upstream.get_span_context().trace_id

        extracted = extract_context(carrier)
        with self.tracer.start_as_current_span(
            "agent-b", context=extracted.otel_context
        ) as downstream:
            self.assertEqual(downstream.get_span_context().trace_id, upstream_trace_id)
            self.assertEqual(
                trace.get_current_span().get_span_context().trace_id, upstream_trace_id
            )

        self.assertEqual(
            extracted.event_fields(agent_id="agent-b"),
            {
                "run_id": "run-123",
                "workflow_id": "workflow-456",
                "agent_id": "agent-b",
                "parent_agent_id": "agent-a",
            },
        )

    def test_async_handoff_creates_link_without_forcing_parentage(self):
        carrier = {}
        with self.tracer.start_as_current_span("producer") as upstream:
            inject_context(carrier, run_id="run-async", agent_id="agent-a")
            upstream_context = upstream.get_span_context()

        extracted = extract_context(carrier)
        link = extracted.link(attributes={"agentrust.handoff.type": "queue"})
        with self.tracer.start_as_current_span("consumer", links=[link]) as consumer:
            self.assertNotEqual(consumer.get_span_context().trace_id, upstream_context.trace_id)
            self.assertFalse(consumer.parent)
        self.assertEqual(link.context.trace_id, upstream_context.trace_id)
        self.assertEqual(link.attributes["agentrust.handoff.type"], "queue")

    def test_header_lookup_is_case_insensitive(self):
        extracted = extract_context(
            {"X-AgenTrust-Run-Id": "run-1", "X-AgenTrust-Agent-Id": "agent-a"}
        )
        self.assertEqual(extracted.run_id, "run-1")
        self.assertEqual(extracted.upstream_agent_id, "agent-a")

    def test_injection_rejects_header_injection(self):
        with self.assertRaisesRegex(PropagationError, "line break"):
            inject_context({}, run_id="run-1\r\nmalicious: value", agent_id="agent-a")

    def test_link_requires_valid_w3c_context(self):
        with self.assertRaisesRegex(PropagationError, "no valid remote span"):
            extract_context({"x-agentrust-run-id": "run-1"}).link()


if __name__ == "__main__":
    unittest.main()
