import importlib.util
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


@unittest.skipIf(sys.version_info < (3, 11), "TRACE dependency requires Python 3.11+")
class ReferenceScenarioTests(unittest.TestCase):
    def test_complete_governed_workflow(self):
        path = ROOT / "examples" / "governed_workflow.py"
        spec = importlib.util.spec_from_file_location("governed_workflow", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        summary = module.run_scenario()
        self.assertEqual(summary["events_accepted"], 5)
        self.assertEqual(summary["events_fully_projected"], 5)
        self.assertEqual(summary["evidence_entries"], 5)
        self.assertEqual(summary["span_events"], 5)
        self.assertEqual(summary["log_records"], 5)
        self.assertGreaterEqual(summary["metric_points"], 5)
        self.assertEqual(summary["trace_appraisal"], "affirming")
        self.assertEqual(summary["trace_data_class"], "confidential")
        self.assertEqual(summary["trace_tool_calls"], 1)


if __name__ == "__main__":
    unittest.main()
