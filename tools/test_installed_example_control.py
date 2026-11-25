"""Exercise the installed-example checker and prove its refusal guards matter."""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import agentrust_telemetry


DRIVER = '''
import importlib.util
import sys
from dataclasses import replace
control, example, case, outside = sys.argv[1:]
if case == "outside-package":
    sys.path.insert(0, outside)
from agentrust_telemetry import TelemetryClient
if case in {"not-accepted", "not-logged", "projection-error"}:
    original = TelemetryClient.emit
    changes = {"not-accepted": {"accepted": False},
               "not-logged": {"log_emitted": False},
               "projection-error": {"projection_errors": ("synthetic",)}}[case]
    def changed(self, *args, **kwargs):
        return replace(original(self, *args, **kwargs), **changes)
    TelemetryClient.emit = changed
spec = importlib.util.spec_from_file_location("example_control", control)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
sys.argv = [control, example]
module.main()
'''


def replace_once(source, old, new):
    if source.count(old) != 1:
        raise AssertionError(f"control site must occur exactly once: {old!r}")
    return source.replace(old, new)


def run_case(control, example, case, outside):
    return subprocess.run(
        [sys.executable, "-I", "-c", DRIVER, str(control), str(example), case, str(outside)],
        cwd=control.parent, capture_output=True, text=True,
    )


def check_controls(control, example):
    source = example.read_text(encoding="utf-8")
    control_source = control.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="example-controls-") as directory:
        root = Path(directory)
        outside = root / "outside"
        shutil.copytree(Path(agentrust_telemetry.__file__).resolve().parent,
                        outside / "agentrust_telemetry")
        unchanged = run_case(control, example, "valid", outside)
        if unchanged.returncode or "PASS installed manual governance example" not in unchanged.stdout:
            raise AssertionError(f"valid installed example failed:\n{unchanged.stderr}")
        # Read the event to change its version without pinning a second contract
        # version in this control, which must also work after version upgrades.
        import re
        match = re.search(r'"spec_version": "([^"]+)"', source)
        if match is None:
            raise AssertionError("manual example must declare spec_version")
        variants = {
            "stale-version": replace_once(source, match.group(0), '"spec_version": "unsupported"'),
            "no-event": replace_once(source, "print(client.emit(event))", "pass"),
            "two-events": replace_once(source, "print(client.emit(event))",
                                       "print(client.emit(event))\nprint(client.emit(event))"),
        }
        expected = {
            "stale-version": "EventValidationError",
            "no-event": "must emit exactly one event",
            "two-events": "must emit exactly one event",
            "not-accepted": "must accept and log its event without errors",
            "not-logged": "must accept and log its event without errors",
            "projection-error": "must accept and log its event without errors",
            "outside-package": "imported outside installed environment",
        }
        examples = {}
        for case in expected:
            path = root / f"{case}.py"
            path.write_text(variants.get(case, source), encoding="utf-8")
            examples[case] = path
            result = run_case(control, path, case, outside)
            if result.returncode == 0 or expected[case] not in result.stderr:
                raise AssertionError(f"negative control {case} was not caught as intended:\n{result.stderr}")
        # These mutations retain all names and executable paths. Each matching
        # negative control must become a false success when its guard is removed.
        mutants = {
            "two-events": ("if len(results) != 1:", "if False:"),
            "not-accepted": ("not result.accepted or ", ""),
            "not-logged": ("not result.log_emitted or ", ""),
            "projection-error": (" or result.projection_errors", ""),
            "outside-package": (
                "if not package.is_relative_to(Path(sys.prefix).resolve()):", "if False:"),
        }
        for case, (old, new) in mutants.items():
            mutated = replace_once(control_source, old, new)
            mutant = root / f"mutant-{case}.py"
            mutant.write_text(mutated, encoding="utf-8")
            result = run_case(mutant, examples[case], case, outside)
            if result.returncode != 0:
                raise AssertionError(f"disabled guard did not expose {case}:\n{result.stderr}")
        print(json.dumps({"positive": 1, "negative": len(expected), "guard_mutations": len(mutants)}))


if __name__ == "__main__":
    check_controls(Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve())
