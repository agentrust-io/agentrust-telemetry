"""Fail closed unless a release tag matches every declared package version."""

import argparse
from pathlib import Path
import sys

try:
    from check_versions import ROOT, ecosystem_versions
except ModuleNotFoundError:  # Imported as a repository test module.
    from tools.check_versions import ROOT, ecosystem_versions


def validate_tag(tag: str, root: Path = ROOT) -> list[str]:
    contract = (root / "spec" / "VERSION").read_text(encoding="utf-8").strip()
    expected = f"v{contract}"
    errors = []
    if tag != expected:
        errors.append(f"release tag {tag!r} must equal {expected!r}")
    try:
        ecosystem_versions(contract)
    except ValueError as error:
        errors.append(str(error))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", help="Git release tag, including the leading v")
    arguments = parser.parse_args()
    errors = validate_tag(arguments.tag)
    if errors:
        for error in errors:
            print(f"FAIL {error}", file=sys.stderr)
        return 1
    print(f"PASS release tag={arguments.tag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
