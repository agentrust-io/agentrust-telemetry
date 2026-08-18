import importlib.util
import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "conformance_validate", ROOT / "conformance" / "runner" / "validate.py"
)
assert SPEC and SPEC.loader
validate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validate)


class ConformanceTests(unittest.TestCase):
    def test_all_schemas_are_valid_draft_2020_12(self):
        for path in sorted((ROOT / "spec" / "schema").glob("*.schema.json")):
            with self.subTest(schema=path.name):
                Draft202012Validator.check_schema(json.loads(path.read_text()))

    def test_committed_suite_has_expected_verdicts(self):
        self.assertEqual(validate.run_suite(), 0)

    def test_nested_prohibited_key_is_rejected_independently(self):
        record = json.loads(
            (ROOT / "conformance" / "fixtures" / "valid" / "policy-decision.json").read_text()
        )
        record["attributes"] = {"vendor.safe": True}
        record["policy"]["prompt"] = "must never leave process"
        errors = validate.validate_record(record)
        self.assertTrue(any("$.policy.prompt" in error and "privacy" in error for error in errors))

    def test_unknown_event_type_is_rejected(self):
        record = json.loads(
            (ROOT / "conformance" / "fixtures" / "valid" / "evidence.json").read_text()
        )
        record["event_type"] = "vendor.unknown"
        self.assertIn("unsupported event_type", validate.validate_record(record)[0])

    def test_uppercase_trace_id_is_rejected(self):
        record = json.loads(
            (ROOT / "conformance" / "fixtures" / "valid" / "policy-decision.json").read_text()
        )
        record["trace_id"] = record["trace_id"].upper()
        self.assertTrue(validate.validate_record(record))

    def test_action_payload_field_is_rejected_by_schema_and_privacy_gate(self):
        record = json.loads(
            (ROOT / "conformance" / "fixtures" / "valid" / "action.json").read_text()
        )
        record["tool_arguments"] = {"path": "sensitive.py"}
        errors = validate.validate_record(record)
        self.assertTrue(any("unevaluated" in error.lower() for error in errors))
        self.assertTrue(any("tool_arguments" in error and "privacy" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
