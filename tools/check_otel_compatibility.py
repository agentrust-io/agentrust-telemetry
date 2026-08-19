"""Fail when shipped OTel projections drift from the compatibility matrix."""

from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "compatibility" / "otel-genai.json"
PROJECTION = ROOT / "src" / "agentrust_telemetry" / "projection.py"
OTEL = ROOT / "src" / "agentrust_telemetry" / "otel.py"


def _literal_assignment(path: Path, name: str):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            return ast.literal_eval(node.value)
    raise ValueError(f"{name} assignment not found in {path.name}")


def _instruments(path: Path) -> dict[str, str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        kind = {"create_counter": "counter", "create_histogram": "histogram"}.get(
            node.func.attr
        )
        if kind and node.args and isinstance(node.args[0], ast.Constant):
            found[str(node.args[0].value)] = kind
    return found


def validate_matrix(document: dict, attributes: set[str], instruments: dict[str, str]) -> list[str]:
    errors: list[str] = []
    upstream = document.get("upstream", {})
    if not re.fullmatch(r"[0-9a-f]{40}", str(upstream.get("commit", ""))):
        errors.append("upstream commit must be a full lowercase Git SHA")
    if upstream.get("status") != "development":
        errors.append("pinned OTel GenAI status must be development")
    if upstream.get("schema_url") is not None:
        errors.append("schema_url must remain null until upstream publishes one")

    allowed = set(document.get("relations", []))
    for section in ("span_attributes", "metrics", "event_families", "native_context", "deliberate_omissions"):
        for entry in document.get(section, []):
            if entry.get("relation") not in allowed:
                errors.append(f"{section} has unsupported relation: {entry.get('relation')!r}")

    matrix_attributes = [entry["agentrust"] for entry in document.get("span_attributes", [])]
    if len(matrix_attributes) != len(set(matrix_attributes)):
        errors.append("span_attributes contains duplicates")
    missing = sorted(attributes - set(matrix_attributes))
    extra = sorted(set(matrix_attributes) - attributes)
    if missing or extra:
        errors.append(f"span attribute drift missing={missing} extra={extra}")

    matrix_metrics = {
        entry["agentrust"]: entry["instrument"] for entry in document.get("metrics", [])
    }
    if matrix_metrics != instruments:
        errors.append(f"metric drift expected={instruments} matrix={matrix_metrics}")

    expected_families = {
        "action.executed", "policy.decision", "usage.recorded", "data_flow.observed",
        "approval.*", "evidence.*",
    }
    actual_families = {entry["agentrust"] for entry in document.get("event_families", [])}
    if actual_families != expected_families:
        errors.append(
            f"event family drift missing={sorted(expected_families - actual_families)} "
            f"extra={sorted(actual_families - expected_families)}"
        )
    return errors


def main() -> int:
    document = json.loads(MATRIX.read_text(encoding="utf-8"))
    attributes = set(_literal_assignment(PROJECTION, "DIRECT_ATTRIBUTES").values())
    instruments = _instruments(OTEL)
    errors = validate_matrix(document, attributes, instruments)
    if errors:
        for error in errors:
            print(f"FAIL {error}", file=sys.stderr)
        return 1
    print(
        f"PASS OTel GenAI matrix covers {len(attributes)} span attributes, "
        f"{len(instruments)} metrics, and {len(document['event_families'])} event families"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
