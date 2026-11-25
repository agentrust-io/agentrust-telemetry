"""Run the committed manual example against an isolated installed package."""

from pathlib import Path
import runpy
import sys

import agentrust_telemetry
from agentrust_telemetry import TelemetryClient


def main() -> None:
    package = Path(agentrust_telemetry.__file__).resolve()
    if not package.is_relative_to(Path(sys.prefix).resolve()):
        raise AssertionError(f"example imported outside installed environment: {package}")
    results = []
    original_emit = TelemetryClient.emit

    def capture_emit(self, *args, **kwargs):
        result = original_emit(self, *args, **kwargs)
        results.append(result)
        return result

    TelemetryClient.emit = capture_emit
    try:
        runpy.run_path(sys.argv[1], run_name="__main__")
    finally:
        TelemetryClient.emit = original_emit
    if len(results) != 1:
        raise AssertionError("manual example must emit exactly one event")
    result = results[0]
    if not result.accepted or not result.log_emitted or result.projection_errors:
        raise AssertionError("manual example must accept and log its event without errors")
    print("PASS installed manual governance example")


if __name__ == "__main__":
    main()
