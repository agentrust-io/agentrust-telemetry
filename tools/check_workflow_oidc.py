"""Source-only OIDC grant baseline for the release-safeguard sweep (.github#54)."""

from __future__ import annotations

from pathlib import Path
import sys

import yaml


WORKFLOWS = Path(__file__).resolve().parents[1] / ".github/workflows"
# Proposed existing-source baseline, not approval of live environment settings.
OIDC_JOBS = {
    ("release.yml", "publish-pypi"),
    ("release.yml", "publish-npm"),
    ("release.yml", "release-assets"),
    ("scorecard.yml", "analysis"),
}


def _oidc_write(permissions):
    if isinstance(permissions, str):
        if permissions not in {"read-all", "write-all"}:
            raise ValueError("unsupported permission shorthand")
        return permissions == "write-all"
    if not isinstance(permissions, dict):
        raise ValueError("permissions must be a mapping or supported shorthand")
    if any(not isinstance(key, str) or value not in ("read", "write", "none")
           for key, value in permissions.items()):
        raise ValueError("permission entries must name read, write or none")
    return permissions.get("id-token") == "write"


def check_oidc_permissions(workflows):
    """Refuse source drift even when narrower jobs shadow a broad default.

    Explicit raises are intentional: a direct python -O invocation still refuses.
    actionlint separately validates workflow syntax, expressions and duplicates.
    """
    paths = sorted([*workflows.glob("*.yml"), *workflows.glob("*.yaml")])
    if not paths:
        raise ValueError("no workflows found")
    actual = set()
    for path in paths:
        workflow = yaml.safe_load(path.read_text(encoding="utf-8"))
        if not isinstance(workflow, dict) or not isinstance(workflow.get("jobs"), dict):
            raise ValueError(f"workflow and jobs must be mappings: {path.name}")
        defaults = workflow.get("permissions", {})
        if _oidc_write(defaults):
            raise ValueError(f"workflow-wide OIDC grant: {path.name}")
        for name, job in workflow["jobs"].items():
            if not isinstance(job, dict):
                raise ValueError(f"job must be a mapping: {path.name}/{name}")
            permissions = job.get("permissions", defaults)
            if permissions == "write-all":
                raise ValueError(f"OIDC write-all job grant: {path.name}/{name}")
            if _oidc_write(permissions):
                actual.add((path.name, name))
    if actual != OIDC_JOBS:
        raise ValueError(f"OIDC job allowance drift: {sorted(actual ^ OIDC_JOBS)}")



def main():
    workflows = Path(sys.argv[1]) if len(sys.argv) > 1 else WORKFLOWS
    try:
        check_oidc_permissions(workflows)
    except (ValueError, yaml.YAMLError) as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    print("PASS workflow OIDC grants match the proposed source baseline")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
