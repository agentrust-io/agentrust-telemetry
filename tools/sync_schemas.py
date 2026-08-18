"""Mechanically copy normative schemas into the Python wheel."""

from pathlib import Path
import shutil


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "spec" / "schema"
DESTINATION = ROOT / "src" / "agentrust_telemetry" / "schemas"


def main() -> None:
    DESTINATION.mkdir(parents=True, exist_ok=True)
    expected = set()
    for source in SOURCE.glob("*.schema.json"):
        expected.add(source.name)
        shutil.copyfile(source, DESTINATION / source.name)
    for stale in DESTINATION.glob("*.schema.json"):
        if stale.name not in expected:
            stale.unlink()


if __name__ == "__main__":
    main()
