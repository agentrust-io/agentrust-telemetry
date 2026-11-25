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

    def test_inject_rejects_control_characters_in_every_agentrust_value(self):
        fields = {"run_id": "run-1", "agent_id": "agent-a", "workflow_id": "workflow-1"}
        for field in fields:
            for bad in ("a\x00b", "a\x1fb", "a\x7fb", "a\tb", "a\x0bb"):
                with self.subTest(field=field, bad=bad), self.assertRaisesRegex(
                    PropagationError, f"{field} contains a prohibited"
                ):
                    inject_context({}, **{**fields, field: bad})

        # Valid twins sit on both sides of the rejected range: space and tilde.
        carrier = {}
        inject_context(carrier, run_id="run 1", agent_id="agent~a", workflow_id="~")
        self.assertEqual(carrier["x-agentrust-run-id"], "run 1")
        self.assertEqual(carrier["x-agentrust-agent-id"], "agent~a")
        self.assertEqual(carrier["x-agentrust-workflow-id"], "~")

    def test_extract_rejects_control_characters_in_every_agentrust_header(self):
        attributes = {
            "x-agentrust-run-id": "run_id",
            "x-agentrust-workflow-id": "workflow_id",
            "x-agentrust-agent-id": "upstream_agent_id",
        }
        for header, attribute in attributes.items():
            for bad in ("a\x00b", "a\x1fb", "a\x7fb", "a\tb"):
                with self.subTest(header=header, bad=bad), self.assertRaisesRegex(
                    PropagationError, "prohibited control character"
                ):
                    extract_context({header: bad})
            with self.subTest(header=header, valid="space and tilde"):
                self.assertEqual(getattr(extract_context({header: "a b~"}), attribute), "a b~")

    def test_extract_rejects_conflicting_case_insensitive_duplicate_headers(self):
        for header in ("x-agentrust-run-id", "x-agentrust-workflow-id", "x-agentrust-agent-id"):
            with self.subTest(header=header), self.assertRaisesRegex(
                PropagationError, "conflicting duplicate"
            ):
                extract_context({header.upper(): "first", header: "second"})

    def test_extract_rejects_empty_and_non_string_values_and_ignores_non_string_keys(self):
        for header in ("x-agentrust-run-id", "x-agentrust-workflow-id", "x-agentrust-agent-id"):
            with self.subTest(header=header):
                with self.assertRaisesRegex(PropagationError, "must not be empty"):
                    extract_context({header: ""})
                for bad in (7, None, ["a", "b"]):
                    with self.assertRaisesRegex(PropagationError, "must be a string"):
                        extract_context({header: bad})
        extracted = extract_context({1: "ignored", "X-AgenTrust-Run-Id": "run-1"})
        self.assertEqual(extracted.run_id, "run-1")

    def test_agentrust_values_are_limited_to_512_characters(self):
        carrier = {}
        inject_context(carrier, run_id="r" * 512, agent_id="a")
        self.assertEqual(len(carrier["x-agentrust-run-id"]), 512)
        with self.assertRaisesRegex(PropagationError, "run_id exceeds 512 characters"):
            inject_context({}, run_id="r" * 513, agent_id="a")
        for header in ("x-agentrust-run-id", "x-agentrust-workflow-id", "x-agentrust-agent-id"):
            with self.subTest(header=header):
                extract_context({header: "v" * 512})
                with self.assertRaisesRegex(PropagationError, "exceeds 512 characters"):
                    extract_context({header: "v" * 513})

    def test_extract_accepts_identical_case_insensitive_duplicate_headers(self):
        extracted = extract_context(
            {
                "X-AgenTrust-Run-Id": "run-1",
                "x-agentrust-run-id": "run-1",
                "X-AGENTRUST-WORKFLOW-ID": "workflow-1",
                "x-agentrust-workflow-id": "workflow-1",
                "X-Agentrust-Agent-Id": "agent-a",
                "x-agentrust-agent-id": "agent-a",
            }
        )
        self.assertEqual(
            (extracted.run_id, extracted.workflow_id, extracted.upstream_agent_id),
            ("run-1", "workflow-1", "agent-a"),
        )

    def test_extract_validates_every_duplicate_before_comparing_them(self):
        with self.assertRaisesRegex(PropagationError, "prohibited control character"):
            extract_context({"X-AgenTrust-Run-Id": "run-1\x00", "x-agentrust-run-id": "run-1\x00"})


if __name__ == "__main__":
    unittest.main()
