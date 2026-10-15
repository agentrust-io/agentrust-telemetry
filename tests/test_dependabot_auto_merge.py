"""Exercise the real auto-merge shell without contacting GitHub."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

WORKFLOW = (
    Path(__file__).resolve().parents[1] / ".github/workflows/dependabot-auto-merge.yml"
)


class DependabotAutoMergeTests(unittest.TestCase):
    @unittest.skipUnless(
        sys.platform == "linux", "Matches the workflow's Ubuntu runner"
    )
    def test_metadata_eligibility(self):
        patch = {"updateType": "version-update:semver-patch"}
        minor = {"updateType": "version-update:semver-minor"}
        major = {"updateType": "version-update:semver-major"}
        cases = [
            ([patch], True),
            ([minor], True),
            ([major], False),
            ([minor, patch], True),
            ([patch, major], False),
            ([patch, {}], False),
            ([{"updateType": None}], False),
            ([{"updateType": "unknown"}], False),
            ([patch, "unknown"], False),
            ([], False),
            (patch, False),
            (None, False),
            ("not metadata", False),
        ]
        for metadata, allowed in cases:
            with self.subTest(metadata=metadata, allowed=allowed):
                self._run_gate(json.dumps(metadata), allowed)

    @unittest.skipUnless(
        sys.platform == "linux", "Matches the workflow's Ubuntu runner"
    )
    def test_malformed_metadata_never_queues(self):
        self._run_gate("{invalid", False)

    def _run_gate(self, metadata, allowed):
        # Keep this tooling dependency-free, as the existing workflow guards are.
        block = re.search(
            r"^        run: \|\n((?:          [^\n]*\n)+)",
            WORKFLOW.read_text(),
            re.MULTILINE,
        )
        self.assertIsNotNone(block, "auto-merge must retain its literal Bash block")
        script = textwrap.dedent(block[1])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "gh-args"
            gh = root / "gh"
            gh.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "$AUDIT_GH_ARGS"\n')
            gh.chmod(0o755)
            head = "a" * 40
            url = "https://github.com/example/repo/pull/1"
            env = {
                **os.environ,
                "PATH": str(root) + os.pathsep + os.environ["PATH"],
                "AUDIT_GH_ARGS": str(output),
                "UPDATED_DEPENDENCIES": metadata,
                "PR_HEAD_SHA": head,
                "PR_URL": url,
                "GH_TOKEN": "unused-local-test-token",
            }
            subprocess.run(
                ["bash", "--noprofile", "--norc", "-e", "-o", "pipefail", "-c", script],
                env=env,
                check=True,
                capture_output=True,
                text=True,
                timeout=10,
            )
            self.assertEqual(output.exists(), allowed)
            if allowed:
                self.assertEqual(
                    output.read_text().splitlines(),
                    [
                        "pr",
                        "merge",
                        "--auto",
                        "--squash",
                        "--match-head-commit",
                        head,
                        url,
                    ],
                )

    def test_workflow_keeps_event_and_permission_boundaries(self):
        source = WORKFLOW.read_text()
        self.assertRegex(
            source,
            r"(?m)^on:\n  pull_request:\n    types: \[opened, reopened, synchronize\]\n"
            r"    branches: \[main\]\n\npermissions:",
        )
        for required in (
            "user.login == 'dependabot[bot]'",
            "head.repo.full_name == github.repository",
            "permissions:\n  contents: read\n",
            "    permissions:\n      contents: write\n      pull-requests: write\n",
            "UPDATED_DEPENDENCIES: ${{ steps.metadata.outputs.updated-dependencies-json }}",
            "PR_HEAD_SHA: ${{ github.event.pull_request.head.sha }}",
            "PR_URL: ${{ github.event.pull_request.html_url }}",
            "GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}",
        ):
            with self.subTest(required=required):
                self.assertIn(required, source)
        self.assertRegex(source, r"uses: dependabot/fetch-metadata@[0-9a-f]{40} #")
        for forbidden in ("skip-verification", "skip-commit-verification", "checkout@"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
