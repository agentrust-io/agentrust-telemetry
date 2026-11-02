"""Shared Python/TypeScript normalization and projection cases, not schema acceptance."""
import json
import math
import unittest
from pathlib import Path

from agentrust_telemetry.adapters.base import _unix_nano
from agentrust_telemetry.projection import span_attributes

CORPUS = json.loads(
    (Path(__file__).resolve().parents[1] / "conformance/parity/projection-boundaries.json")
    .read_text(encoding="utf-8")
)


class TestProjectionParityCorpus(unittest.TestCase):
    def test_timestamp_normalization(self):
        for case in CORPUS["timestamps"]:
            with self.subTest(value=case["input"]):
                normalized = _unix_nano(case["input"])
                self.assertEqual(normalized, case["input"])
                self.assertEqual(list(divmod(int(normalized), 1_000_000_000)), case["tuple"])

    def test_noncanonical_timestamps(self):
        for value in CORPUS["invalid_timestamps"]:
            with self.subTest(value=value), self.assertRaises((ValueError, TypeError)):
                _unix_nano(value)

    def test_scalar_projection(self):
        special = {"nan": math.nan, "positive_infinity": math.inf, "negative_infinity": -math.inf}
        for case in CORPUS["projections"]:
            with self.subTest(case=case["id"]):
                event = dict(case["event"])
                event.update({key: special[value] for key, value in case.get("special", {}).items()})
                self.assertEqual(span_attributes(event), case["expected"])
