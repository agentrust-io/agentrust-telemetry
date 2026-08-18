"""Validate AgentTrust telemetry fixtures against the normative contract."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource


ROOT = Path(__file__).resolve().parents[2]
SCHEMA_DIR = ROOT / "spec" / "schema"
FIXTURE_DIR = ROOT / "conformance" / "fixtures"

EVENT_SCHEMAS = {
    "action.executed": "action.schema.json",
    "policy.decision": "policy-decision.schema.json",
    "usage.recorded": "usage.schema.json",
    "data_flow.observed": "data-flow.schema.json",
}
APPROVAL_PREFIX = "approval."
EVIDENCE_PREFIX = "evidence."

# Keys are checked recursively. Closed schemas are the first defense; this
# independent check protects the privacy invariant if a future schema grows.
PROHIBITED_METADATA_KEYS = {
    "prompt",
    "completion",
    "source_code",
    "tool_arguments",
    "tool_result",
    "authorization",
    "credential",
    "secret",
    "access_token",
    "refresh_token",
}


def schema_name(event_type: str) -> str:
    if event_type in EVENT_SCHEMAS:
        return EVENT_SCHEMAS[event_type]
    if event_type.startswith(APPROVAL_PREFIX):
        return "approval.schema.json"
    if event_type.startswith(EVIDENCE_PREFIX):
        return "evidence.schema.json"
    raise ValueError(f"unsupported event_type: {event_type!r}")


def prohibited_paths(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if key.lower() in PROHIBITED_METADATA_KEYS:
                found.append(path)
            found.extend(prohibited_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(prohibited_paths(child, f"{prefix}[{index}]"))
    return found


def schema_registry() -> Registry:
    registry = Registry()
    for path in SCHEMA_DIR.glob("*.schema.json"):
        contents = json.loads(path.read_text(encoding="utf-8"))
        resource = Resource.from_contents(contents)
        registry = registry.with_resource(contents["$id"], resource)
        registry = registry.with_resource(path.as_uri(), resource)
    return registry


def load_validator(name: str) -> Draft202012Validator:
    schema_path = SCHEMA_DIR / name
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    return Draft202012Validator(
        schema, registry=schema_registry(), format_checker=FormatChecker()
    )


def validate_record(record: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    try:
        validator = load_validator(schema_name(str(record.get("event_type", ""))))
    except ValueError as exc:
        return [str(exc)]
    for error in sorted(validator.iter_errors(record), key=lambda item: list(item.absolute_path)):
        location = "$" + "".join(f"[{part!r}]" for part in error.absolute_path)
        errors.append(f"{location}: {error.message}")
    for path in prohibited_paths(record):
        errors.append(f"{path}: prohibited by metadata_only privacy profile")
    return errors


def validate_fixture(path: Path) -> list[str]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"invalid JSON: {exc}"]
    if not isinstance(record, dict):
        return ["top-level value must be an object"]
    return validate_record(record)


def run_suite(fixtures: Path = FIXTURE_DIR) -> int:
    failures = 0
    for expected_valid, directory in ((True, fixtures / "valid"), (False, fixtures / "invalid")):
        for path in sorted(directory.glob("*.json")):
            errors = validate_fixture(path)
            passed = not errors if expected_valid else bool(errors)
            print(f"{'PASS' if passed else 'FAIL'} {path.relative_to(ROOT)}")
            if not passed:
                failures += 1
                for error in errors or ["invalid fixture unexpectedly passed"]:
                    print(f"  {error}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", type=Path)
    args = parser.parse_args()
    if not args.paths:
        return 1 if run_suite() else 0
    failures = 0
    for path in args.paths:
        errors = validate_fixture(path)
        if errors:
            failures += 1
            print(f"FAIL {path}")
            for error in errors:
                print(f"  {error}")
        else:
            print(f"PASS {path}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
