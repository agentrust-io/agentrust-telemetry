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


def ecosystem_versions(contract: str) -> tuple[str, str]:
    """Map the contract SemVer spelling to Python and npm package versions."""
    match = re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-(dev|alpha|beta|rc)(?:\.(0|[1-9]\d*))?)?",
        contract,
    )
    if not match:
        raise ValueError(f"unsupported contract version: {contract}")
    major, minor, patch, phase, sequence = match.groups()
    release = f"{major}.{minor}.{patch}"
    if phase is None:
        return release, release
    sequence = sequence or "0"
    python_phase = {"dev": ".dev", "alpha": "a", "beta": "b", "rc": "rc"}[phase]
    return f"{release}{python_phase}{sequence}", f"{release}-{phase}.{sequence}"


def main() -> int:
    contract = (ROOT / "spec" / "VERSION").read_text(encoding="utf-8").strip()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    package = project["project"]["version"]
    init_text = (ROOT / "src" / "agentrust_telemetry" / "__init__.py").read_text(encoding="utf-8")
    match = re.search(r'^__version__ = "([^"]+)"$', init_text, re.MULTILINE)
    init_version = match.group(1) if match else None
    try:
        expected_package, expected_npm = ecosystem_versions(contract)
    except ValueError as error:
        print(f"FAIL {error}", file=sys.stderr)
        return 1
    npm_package = json.loads(
        (ROOT / "packages" / "typescript" / "package.json").read_text(encoding="utf-8")
    )["version"]
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
