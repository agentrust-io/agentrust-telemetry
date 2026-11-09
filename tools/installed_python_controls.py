"""Behavioral controls executed by the installed interpreter outside the checkout."""
from __future__ import annotations

import json
import sys
from importlib.metadata import version
from pathlib import Path


EXPECTED_FIXTURES = {
    "valid": [
        "action.json",
        "approval.json",
        "data-flow.json",
        "evidence.json",
        "policy-decision.json",
        "usage.json"
    ],
    "invalid": [
        "action-without-digest.json",
        "aggregate-cost-without-rollup.json",
        "model-call-with-rollup.json",
        "numeric-timestamp.json",
        "raw-content.json",
        "usage-without-measurement.json",
        "zero-trace-id.json"
    ]
}


def check_controls(controls, validator, factory, validation_error):
    counts = {}
    for kind in ("valid", "invalid"):
        cases = controls["fixtures"][kind]
        if sorted(case["name"] for case in cases) != EXPECTED_FIXTURES[kind]:
            raise AssertionError(f"missing or unexpected {kind} controls")
        for case in cases:
            try:
                validator.validate(case["event"])
            except validation_error:
                if kind == "valid":
                    raise AssertionError(f"valid control refused: {case['name']}") from None
            else:
                if kind == "invalid":
                    raise AssertionError(f"invalid control admitted: {case['name']}")
        counts[kind] = len(cases)
    actual = factory.build(
        "usage.recorded", run_id="run-1", agent_id="agent-1", workflow_id="workflow-1",
        scope="model_call", operation="chat", input_tokens=7,
    )
    if actual != controls["golden"]:
        raise AssertionError("installed event construction differs from golden control")
    return counts


def main():
    import agentrust_telemetry as package
    from agentrust_telemetry import EventFactory, EventValidationError, SchemaValidator

    controls = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    origin = Path(package.__file__).resolve()
    if not origin.is_relative_to(Path(sys.prefix).resolve()):
        raise AssertionError(f"import escaped installed environment: {origin}")
    if version("agentrust-telemetry") != controls["version"]:
        raise AssertionError("installed version differs from source package metadata")
    validator = SchemaValidator.bundled()
    factory = EventFactory(
        validator, producer_name="parity-test", producer_version="1.0.0",
        clock_ns=lambda: 1787079000000000000,
        event_id_factory=lambda: "018f0f7d-7a13-7cc2-8000-000000000042",
    )
    print(json.dumps(check_controls(controls, validator, factory, EventValidationError)))


if __name__ == "__main__":
    main()
