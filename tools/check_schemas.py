"""Fail when bundled Python schemas drift from the normative contract."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "schema"
BUNDLED = ROOT / "src" / "agentrust_telemetry" / "schemas"


def compare_schema_directories(source_dir: Path, bundled_dir: Path) -> tuple[list[str], list[str], list[str]]:
    source = {path.name: path.read_bytes() for path in source_dir.glob("*.schema.json")}
    bundled = {path.name: path.read_bytes() for path in bundled_dir.glob("*.schema.json")}
    missing = sorted(set(source) - set(bundled))
    extra = sorted(set(bundled) - set(source))
    changed = sorted(name for name in set(source) & set(bundled) if source[name] != bundled[name])
    return missing, extra, changed


def main() -> int:
    missing, extra, changed = compare_schema_directories(SOURCE, BUNDLED)
    if not (missing or extra or changed):
        print(f"PASS {len(list(SOURCE.glob('*.schema.json')))} bundled schemas match normative bytes")
        return 0
    print(f"FAIL schema drift missing={missing} extra={extra} changed={changed}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
