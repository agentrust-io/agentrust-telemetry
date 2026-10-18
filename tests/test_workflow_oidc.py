"""Paired source-permission controls; no workflow dispatch or live setting access."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/check_workflow_oidc.py"
spec = importlib.util.spec_from_file_location("check_workflow_oidc", TOOL)
assert spec and spec.loader
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class WorkflowOidcTests(unittest.TestCase):
    def copy_workflows(self, directory):
        root = Path(directory)
        for path in [*gate.WORKFLOWS.glob("*.yml"), *gate.WORKFLOWS.glob("*.yaml")]:
            shutil.copyfile(path, root / path.name)
        gate.check_oidc_permissions(root)
        return root

    def test_real_workflow_baseline(self):
        gate.check_oidc_permissions(gate.WORKFLOWS)

    def test_each_permission_drift_is_refused_from_a_passing_copy(self):
        scenarios = [
            "new-yml", "new-yaml", "extra-job", "inherited-default", "shadowed-default",
            "default-write-all", "shadowed-write-all", "job-write-all", "allowed-write-all",
            "remove-pypi", "remove-npm", "remove-assets", "remove-scorecard",
            "rename-job", "rename-file",
        ]
        for scenario in scenarios:
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as directory:
                root = self.copy_workflows(directory)
                path = root / "release.yml"
                workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
                if scenario.startswith("new-"):
                    path = root / ("unexpected." + scenario.removeprefix("new-"))
                    workflow = {"permissions": {}, "jobs": {"unexpected": {
                        "runs-on": "ubuntu-latest", "permissions": {"id-token": "write"},
                        "steps": [{"run": "echo test"}],
                    }}}
                elif scenario == "extra-job":
                    workflow["jobs"]["unexpected"] = {"permissions": {"id-token": "write"}}
                elif scenario in {"inherited-default", "shadowed-default"}:
                    workflow["permissions"] = {"id-token": "write"}
                    if scenario == "shadowed-default":
                        for job in workflow["jobs"].values():
                            job.setdefault("permissions", {})
                elif scenario in {"default-write-all", "shadowed-write-all"}:
                    workflow["permissions"] = "write-all"
                    if scenario == "shadowed-write-all":
                        for job in workflow["jobs"].values():
                            job.setdefault("permissions", {})
                elif scenario in {"job-write-all", "allowed-write-all"}:
                    job = "build" if scenario == "job-write-all" else "publish-pypi"
                    workflow["jobs"][job]["permissions"] = "write-all"
                elif scenario.startswith("remove-"):
                    filename, job = {
                        "remove-pypi": ("release.yml", "publish-pypi"),
                        "remove-npm": ("release.yml", "publish-npm"),
                        "remove-assets": ("release.yml", "release-assets"),
                        "remove-scorecard": ("scorecard.yml", "analysis"),
                    }[scenario]
                    path = root / filename
                    workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
                    workflow["jobs"][job]["permissions"].pop("id-token")
                elif scenario == "rename-job":
                    workflow["jobs"]["renamed"] = workflow["jobs"].pop("publish-pypi")
                elif scenario == "rename-file":
                    path.unlink()
                    path = root / "release.yaml"
                path.write_text(yaml.safe_dump(workflow), encoding="utf-8", newline="\n")
                with self.assertRaisesRegex(ValueError, "OIDC"):
                    gate.check_oidc_permissions(root)

    def test_read_only_inheritance_and_narrowing_are_valid(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_workflows(directory)
            (root / "read-only.yaml").write_text(
                "permissions: read-all\njobs:\n  inherited: {}\n"
                "  narrow:\n    permissions:\n      contents: read\n", encoding="utf-8",
            )
            gate.check_oidc_permissions(root)

    def test_malformed_permissions_refuse(self):
        for value in [None, [], 1, "unsupported", {"id-token": True}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                gate._oidc_write(value)

    def test_empty_and_malformed_workflow_inventories_refuse(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "no workflows"):
                gate.check_oidc_permissions(root)
            for text in ["null", "[]", "jobs: null", "jobs: {test: null}"]:
                with self.subTest(text=text):
                    (root / "bad.yml").write_text(text, encoding="utf-8")
                    with self.assertRaisesRegex(ValueError, "mapping"):
                        gate.check_oidc_permissions(root)

    def test_optimized_cli_has_a_positive_control_and_detects_permission_drift(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copy_workflows(directory)
            command = [sys.executable, "-O", str(TOOL), str(root)]
            positive = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(positive.returncode, 0, positive.stderr)
            (root / "new.yaml").write_text(
                "permissions: write-all\njobs: {}\n", encoding="utf-8",
            )
            refused = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(refused.returncode, 1)
            self.assertIn("workflow-wide OIDC grant", refused.stderr)

    def test_ci_runs_the_guard_without_an_optional_parser_skip(self):
        ci = yaml.safe_load((gate.WORKFLOWS / "ci.yml").read_text(encoding="utf-8"))
        commands = [step.get("run", "") for step in ci["jobs"]["test"]["steps"]]
        self.assertIn("python tools/check_workflow_oidc.py", commands)
        inputs = (ROOT / "requirements/test.in").read_text(encoding="utf-8")
        self.assertIn("PyYAML==6.0.3", inputs.splitlines())
        lock = (ROOT / "requirements/test.txt").read_text(encoding="utf-8")
        self.assertIn("pyyaml==6.0.3", lock)


if __name__ == "__main__":
    unittest.main()
