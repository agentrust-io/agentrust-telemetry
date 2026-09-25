"""Normative schema and privacy validation."""

from __future__ import annotations

import json
import math
from importlib.resources import as_file, files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource

from .errors import EventValidationError


EVENT_SCHEMAS = {
    "action.executed": "action.schema.json",
    "policy.decision": "policy-decision.schema.json",
    "usage.recorded": "usage.schema.json",
    "data_flow.observed": "data-flow.schema.json",
}
PROHIBITED_KEYS = frozenset({
    "prompt", "completion", "source_code", "tool_arguments", "tool_result",
    "authorization", "credential", "secret", "access_token", "refresh_token",
})


def _schema_name(event_type: str) -> str:
    if event_type in EVENT_SCHEMAS:
        return EVENT_SCHEMAS[event_type]
    if event_type.startswith("approval."):
        return "approval.schema.json"
    if event_type.startswith("evidence."):
        return "evidence.schema.json"
    raise EventValidationError(f"unsupported event_type: {event_type!r}")


# Normative events are at most a few levels deep. The bound keeps hostile or
# self-referencing input from exhausting the stack inside jsonschema or the
# privacy walk, where it would surface as RecursionError, not a validation error.
_MAX_DEPTH = 32


def _json_shape_error(value: Any) -> str | None:
    """Return why ``value`` is not a JSON value this validator can walk, if so."""
    stack: list[tuple[Any, str, int]] = [(value, "$", 0)]
    while stack:
        item, path, depth = stack.pop()
        if depth > _MAX_DEPTH:
            return f"{path} exceeds the maximum nesting depth of {_MAX_DEPTH}"
        if isinstance(item, dict):
            for key, child in item.items():
                if not isinstance(key, str):
                    return f"{path} has a non-string key of type {type(key).__name__}"
                stack.append((child, f"{path}.{key}", depth + 1))
        elif isinstance(item, list):
            for index, child in enumerate(item):
                stack.append((child, f"{path}[{index}]", depth + 1))
        elif isinstance(item, float) and not math.isfinite(item):
            return f"{path} is not a finite number"
    return None


def _prohibited_paths(value: Any, prefix: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if key.lower() in PROHIBITED_KEYS:
                found.append(path)
            found.extend(_prohibited_paths(child, path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(_prohibited_paths(child, f"{prefix}[{index}]"))
    return found


class SchemaValidator:
    @classmethod
    def bundled(cls) -> "SchemaValidator":
        resource = files("agentrust_telemetry").joinpath("schemas")
        with as_file(resource) as directory:
            return cls(directory)

    def __init__(
        self,
        schema_directory: Path | str,
        *,
        allowed_attribute_keys: frozenset[str] = frozenset(),
    ):
        self.schema_directory = Path(schema_directory).resolve()
        self.allowed_attribute_keys = allowed_attribute_keys
        schemas: dict[str, dict[str, Any]] = {}
        registry = Registry()
        for path in self.schema_directory.glob("*.schema.json"):
            contents = json.loads(path.read_text(encoding="utf-8"))
            Draft202012Validator.check_schema(contents)
            schemas[path.name] = contents
            resource = Resource.from_contents(contents)
            registry = registry.with_resource(contents["$id"], resource)
            registry = registry.with_resource(path.as_uri(), resource)
        if not schemas:
            raise EventValidationError(f"no schemas found in {self.schema_directory}")
        self._schemas = schemas
        self._registry = registry

    def validate(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict):
            raise EventValidationError("event must be an object")
        shape_error = _json_shape_error(event)
        if shape_error is not None:
            raise EventValidationError(shape_error)
        name = _schema_name(str(event.get("event_type", "")))
        schema = self._schemas.get(name)
        if schema is None:
            raise EventValidationError(f"required schema is missing: {name}")
        validator = Draft202012Validator(
            schema, registry=self._registry, format_checker=FormatChecker()
        )
        errors = sorted(validator.iter_errors(event), key=lambda item: list(item.absolute_path))
        privacy_paths = _prohibited_paths(event)
        messages = [error.message for error in errors]
        messages.extend(f"{path} is prohibited by metadata_only" for path in privacy_paths)
        attributes = event.get("attributes", {})
        if isinstance(attributes, dict):
            for key in sorted(set(attributes) - self.allowed_attribute_keys):
                messages.append(
                    f"$.attributes.{key} is not in the metadata_only attribute allowlist"
                )
        if messages:
            raise EventValidationError("; ".join(messages))
