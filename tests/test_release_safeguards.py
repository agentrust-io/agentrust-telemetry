"""Exercise the release dependency graph and packed-artifact handoff."""
import ast
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def jobs(source):
    return dict(re.findall(r"^  ([\w-]+):\n(.*?)(?=^  [\w-]+:\n|\Z)", source, re.M | re.S))


def field(block, name):
    match = re.search(rf"^    {name}: (.+)$", block, re.M)
    return match[1] if match else None


def scheduled(source, validation, target):
    results = {"validate": validation}
    for name, block in jobs(source).items():
        if name == "validate":
            continue
        needs = field(block, "needs") or ""
        dependencies = [item.strip() for item in needs.strip("[]").split(",") if item.strip()]
        assert all(dependency in results for dependency in dependencies)
        eligible = all(results[dependency] == "success" for dependency in dependencies)
        if condition := field(block, "if"):
            tree = ast.parse(condition, mode="eval").body
            # Fail on a new status-function guard; it must not silently inherit
            # this model's default success() behavior.
            assert isinstance(tree, ast.Compare)
            assert ast.unparse(tree.left) == "github.event.release.target_commitish"
            assert len(tree.ops) == 1 and isinstance(tree.ops[0], ast.Eq)
            assert len(tree.comparators) == 1
            eligible = eligible and target == ast.literal_eval(tree.comparators[0])
        results[name] = "success" if eligible else "skipped"
    return results


class ReleaseSafeguardsTests(unittest.TestCase):
    def test_validation_failure_and_target_controls_reach_both_publishers(self):
        source = (ROOT / ".github/workflows/release.yml").read_text()
        for validation in ("success", "failure", "cancelled", "skipped"):
            for target in ("main", "other"):
                with self.subTest(validation=validation, target=target):
                    result = scheduled(source, validation, target)
                    expected = "success" if validation == "success" and target == "main" else "skipped"
                    for job in ("build", "publish-pypi", "publish-npm", "release-assets"):
                        self.assertEqual(result[job], expected)

    def test_validation_reuses_ci_with_the_python_matrix_and_typescript(self):
        release = jobs((ROOT / ".github/workflows/release.yml").read_text())
        self.assertEqual(field(release["validate"], "uses"), "./.github/workflows/ci.yml")
        ci = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertRegex(ci, r"(?m)^  workflow_call:")
        self.assertIn('python-version: ["3.10", "3.11", "3.12", "3.13"]', ci)
        self.assertIn("npm run check", jobs(ci)["typescript"])

    def test_packed_tarball_is_checked_before_the_immutable_upload(self):
        release = jobs((ROOT / ".github/workflows/release.yml").read_text())
        build = release["build"]
        pack = build.index("npm pack --pack-destination ../../npm-dist")
        smoke = build.index("node tools/smoke_npm.mjs npm-dist/*.tgz")
        upload = build.index("name: npm-distribution")
        self.assertLess(pack, smoke)
        self.assertLess(smoke, upload)
        self.assertIn("path: npm-dist/*.tgz", build)
        publisher = release["publish-npm"]
        self.assertIn("name: npm-distribution", publisher)
        self.assertIn("npm publish ./npm-dist/*.tgz", publisher)
        self.assertNotIn("npm pack", publisher)
        self.assertNotRegex(build, r"(?m)^    environment:")
        self.assertNotIn("id-token: write", build)


if __name__ == "__main__":
    unittest.main()
