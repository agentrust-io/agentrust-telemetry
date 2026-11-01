import importlib.util
import json
import unittest
from pathlib import Path
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installed_python_controls", ROOT / "tools/installed_python_controls.py")
controls_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(controls_module)


class InstalledControlsTests(unittest.TestCase):
    def setUp(self):
        from agentrust_telemetry import (
            EventFactory,
            EventValidationError,
            SchemaValidator,
        )
        self.error = EventValidationError
        self.validator = SchemaValidator.bundled()
        self.controls = {
            "fixtures": {kind: [{"name": path.name, "event": json.loads(path.read_text())}
                                for path in sorted((ROOT / "conformance/fixtures" / kind).glob("*.json"))]
                         for kind in ("valid", "invalid")},
            "golden": json.loads((ROOT / "compatibility/golden/event-factory.json").read_text()),
        }
        self.factory = EventFactory(self.validator, producer_name="parity-test", producer_version="1.0.0",
                                   clock_ns=lambda: 1787079000000000000,
                                   event_id_factory=lambda: "018f0f7d-7a13-7cc2-8000-000000000042")

    def test_real_controls(self):
        counts = controls_module.check_controls(self.controls, self.validator, self.factory, self.error)
        self.assertEqual(counts, {"valid": 6, "invalid": 7})

    def test_accept_all_is_caught(self):
        with self.assertRaisesRegex(AssertionError, "invalid control admitted"):
            controls_module.check_controls(self.controls, Mock(), self.factory, self.error)

    def test_reject_all_is_caught(self):
        validator = Mock()
        validator.validate.side_effect = self.error("synthetic rejection")
        with self.assertRaisesRegex(AssertionError, "valid control refused"):
            controls_module.check_controls(self.controls, validator, self.factory, self.error)

    def test_changed_factory_is_caught(self):
        factory = Mock()
        factory.build.return_value = {**self.controls["golden"], "input_tokens": 8}
        with self.assertRaisesRegex(AssertionError, "golden"):
            controls_module.check_controls(self.controls, self.validator, factory, self.error)

    def test_empty_controls_are_caught(self):
        for kind in ("valid", "invalid"):
            with self.subTest(kind=kind):
                controls = {**self.controls, "fixtures": {**self.controls["fixtures"], kind: []}}
                with self.assertRaisesRegex(AssertionError, "missing"):
                    controls_module.check_controls(controls, self.validator, self.factory, self.error)

    def test_partial_and_renamed_controls_are_caught(self):
        for kind in ("valid", "invalid"):
            cases = self.controls["fixtures"][kind]
            for changed in (cases[1:], [{**cases[0], "name": "renamed.json"}, *cases[1:]],
                            [cases[0], *cases]):
                with self.subTest(kind=kind, names=[c["name"] for c in changed]):
                    controls = {**self.controls, "fixtures": {**self.controls["fixtures"], kind: changed}}
                    with self.assertRaisesRegex(AssertionError, "missing or unexpected"):
                        controls_module.check_controls(controls, self.validator, self.factory, self.error)
