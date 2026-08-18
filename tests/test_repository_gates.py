import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_tool(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "tools" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_schemas = load_tool("check_schemas")
check_versions = load_tool("check_versions")


class RepositoryGateTests(unittest.TestCase):
    def test_schema_gate_detects_changed_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "source"
            bundled = temporary / "bundled"
            source.mkdir()
            bundled.mkdir()
            (source / "event.schema.json").write_text('{"type":"object"}')
            (bundled / "event.schema.json").write_text('{"type":"array"}')
            missing, extra, changed = check_schemas.compare_schema_directories(source, bundled)
            self.assertEqual((missing, extra, changed), ([], [], ["event.schema.json"]))

    def test_schema_gate_detects_missing_and_extra_files(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source = temporary / "source"
            bundled = temporary / "bundled"
            source.mkdir()
            bundled.mkdir()
            (source / "required.schema.json").write_text("{}")
            (bundled / "stale.schema.json").write_text("{}")
            missing, extra, changed = check_schemas.compare_schema_directories(source, bundled)
            self.assertEqual(missing, ["required.schema.json"])
            self.assertEqual(extra, ["stale.schema.json"])
            self.assertEqual(changed, [])

    def test_declared_versions_are_consistent(self):
        self.assertEqual(check_versions.main(), 0)

    def test_issue_templates_are_valid_yaml_when_parser_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for path in sorted((ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml")):
            with self.subTest(path=path.name):
                self.assertIsInstance(yaml.safe_load(path.read_text()), dict)

    def test_workflows_are_valid_yaml_when_parser_available(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("PyYAML not installed")
        for path in sorted((ROOT / ".github" / "workflows").glob("*.yml")):
            with self.subTest(path=path.name):
                document = yaml.load(path.read_text(), Loader=yaml.BaseLoader)
                self.assertIsInstance(document, dict)
                self.assertIn("on", document)
                self.assertIn("jobs", document)


if __name__ == "__main__":
    unittest.main()
