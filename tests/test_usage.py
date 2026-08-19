import sys
import unittest
import uuid
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    CostObservation, EventFactory, SchemaValidator, UsageAccumulator, usage_record,
)


class UsageTests(unittest.TestCase):
    def setUp(self):
        ids = iter(uuid.UUID(int=i) for i in range(1, 20))
        self.factory = EventFactory(
            SchemaValidator.bundled(), producer_name="usage-tests", producer_version="1",
            clock_ns=lambda: 1, event_id_factory=lambda: next(ids),
        )

    def leaf(self, **overrides):
        values = dict(
            run_id="run-1", agent_id="agent-1", workflow_id="workflow-1",
            scope="model_call", operation="chat", input_tokens=10, output_tokens=2,
        )
        values.update(overrides)
        return usage_record(self.factory, **values)

    def test_unknown_price_is_absent_not_zero(self):
        event = self.leaf()
        self.assertNotIn("cost", event)

    def test_cost_requires_finite_amount_and_explicit_provenance(self):
        with self.assertRaisesRegex(ValueError, "finite"):
            self.leaf(cost=CostObservation(float("nan"), "USD", "estimate"))
        event = self.leaf(cost=CostObservation(0, "USD", "provider", "invoice-v1"))
        self.assertEqual(event["cost"]["amount"], 0.0)
        self.assertEqual(event["cost"]["pricing_version"], "invoice-v1")
        with self.assertRaisesRegex(ValueError, "source"):
            CostObservation(1, "USD", "invented").as_event_value()  # type: ignore[arg-type]

    def test_bool_is_not_accepted_as_token_integer(self):
        with self.assertRaisesRegex(TypeError, "input_tokens"):
            self.leaf(input_tokens=True)

    def test_rollup_deduplicates_and_reports_partial_coverage(self):
        first = self.leaf(cost=CostObservation(0.10, "USD", "provider"))
        second = self.leaf(input_tokens=5, output_tokens=None)
        accumulator = UsageAccumulator()
        self.assertTrue(accumulator.add(first))
        self.assertFalse(accumulator.add(first))
        self.assertTrue(accumulator.add(second))
        rollup = accumulator.rollup(
            self.factory, scope="agent_run", run_id="run-1", agent_id="agent-1",
            workflow_id="workflow-1", operation="chat",
        )
        self.assertEqual(rollup["input_tokens"], 15)
        self.assertEqual(rollup["output_tokens"], 2)
        self.assertEqual(rollup["aggregation"]["event_count"], 2)
        self.assertEqual(rollup["aggregation"]["token_coverage"]["output_tokens"], 1)
        self.assertEqual(rollup["aggregation"]["cost_coverage"], 1)
        self.assertEqual(rollup["cost"]["source"], "aggregate")

    def test_rollup_rejects_non_leaf_and_mixed_currency(self):
        accumulator = UsageAccumulator()
        with self.assertRaisesRegex(ValueError, "model_call"):
            accumulator.add(self.leaf(scope="agent_run"))
        accumulator.add(self.leaf(cost=CostObservation(1, "USD", "caller")))
        accumulator.add(self.leaf(cost=CostObservation(1, "EUR", "caller")))
        with self.assertRaisesRegex(ValueError, "mixed currencies"):
            accumulator.rollup(
                self.factory, scope="workflow_run", run_id="run-1", agent_id="orchestrator",
                workflow_id="workflow-1", operation="build",
            )

    def test_reused_event_id_with_changed_data_is_rejected(self):
        event = self.leaf()
        accumulator = UsageAccumulator()
        accumulator.add(event)
        changed = dict(event, input_tokens=999)
        with self.assertRaisesRegex(ValueError, "reused"):
            accumulator.add(changed)

    def test_accumulator_rejects_non_finite_external_cost(self):
        event = self.leaf(cost=CostObservation(1, "USD", "caller"))
        event["cost"]["amount"] = float("nan")
        with self.assertRaisesRegex(ValueError, "finite"):
            UsageAccumulator().add(event)

    def test_schema_rejects_aggregate_cost_without_run_rollup(self):
        event = self.leaf()
        event["cost"] = {"amount": 1, "currency": "USD", "source": "aggregate"}
        with self.assertRaisesRegex(Exception, "aggregation"):
            SchemaValidator.bundled().validate(event)

    def test_rollups_match_shared_cross_language_vector(self):
        vector = json.loads(
            (ROOT / "compatibility" / "golden" / "usage-rollup.json").read_text()
        )
        accumulator = UsageAccumulator()
        for leaf in vector["leaves"]:
            event = self.leaf(
                run_id=vector["run_id"], workflow_id=vector["workflow_id"],
                agent_id=leaf["agent_id"], input_tokens=leaf["input_tokens"],
                output_tokens=leaf.get("output_tokens"),
                cost=(CostObservation(**leaf["cost"]) if "cost" in leaf else None),
            )
            event["event_id"] = leaf["event_id"]
            accumulator.add(event)
        for scope, agent_id in (("agent_run", "agent-a"), ("workflow_run", "orchestrator")):
            actual = accumulator.rollup(
                self.factory, scope=scope, run_id=vector["run_id"], agent_id=agent_id,
                workflow_id=vector["workflow_id"], operation="build",
            )
            for field, expected in vector["expected"][scope].items():
                self.assertEqual(actual[field], expected)


if __name__ == "__main__":
    unittest.main()
