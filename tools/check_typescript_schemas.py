"""Fail when TypeScript package schemas drift from the normative contract."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def compare_schema_directories(source_dir: Path, bundled_dir: Path) -> tuple[list[str], list[str], list[str]]:
    source = {path.name: path.read_bytes() for path in source_dir.glob("*.schema.json")}
    bundled = {path.name: path.read_bytes() for path in bundled_dir.glob("*.schema.json")}
    return (
        sorted(set(source) - set(bundled)),
        sorted(set(bundled) - set(source)),
        sorted(name for name in set(source) & set(bundled) if source[name] != bundled[name]),
    )


def main() -> int:
    missing, extra, changed = compare_schema_directories(
        ROOT / "spec" / "schema", ROOT / "packages" / "typescript" / "schemas"
    )
    if missing or extra or changed:
        print(f"FAIL TypeScript schema drift missing={missing} extra={extra} changed={changed}", file=sys.stderr)
        return 1
    print("PASS TypeScript schemas match normative bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
