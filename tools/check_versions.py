"""Check contract and reference package version declarations for consistency."""

from pathlib import Path
import json
import re
import sys
try:
    import tomllib
except ImportError:  # Python 3.10 development tooling
    import tomli as tomllib


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    contract = (ROOT / "spec" / "VERSION").read_text(encoding="utf-8").strip()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = project["project"]["version"]
    init_text = (ROOT / "src" / "agentrust_telemetry" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', init_text, re.MULTILINE)
    init_version = match.group(1) if match else None
    expected_package = contract.replace("-dev", ".dev0")
    npm_package = json.loads(
        (ROOT / "packages" / "typescript" / "package.json").read_text(encoding="utf-8")
    )["version"]
    expected_npm = f"{contract}.0"
    if package == init_version == expected_package and npm_package == expected_npm:
        print(f"PASS contract={contract} python={package} npm={npm_package}")
        return 0
    print(
        f"FAIL version drift contract={contract} expected_package={expected_package} "
        f"pyproject={package} __init__={init_version} expected_npm={expected_npm} npm={npm_package}",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
