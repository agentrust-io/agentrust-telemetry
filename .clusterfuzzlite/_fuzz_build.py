"""Structured input construction shared by the fuzz targets.

Events are built by mutating a valid seed rather than by fuzzing JSON text, so
the fuzzer spends its budget on field values and shapes (wrong types, integer
and float boundaries, control characters, extra keys, nesting) instead of on
producing syntactically valid JSON.
"""

from __future__ import annotations

import copy
from typing import Any

from _fuzz_seeds import SEEDS

_SEED_NAMES = sorted(SEEDS)
_MAX_DEPTH = 4
_MAX_ITEMS = 5

# Keys the schemas and adapters actually read, so a mutation lands on a field
# that matters far more often than a random string would.
KEYS = sorted(
    {key for seed in SEEDS.values() for key in seed}
    | {
        "attributes", "reason_codes", "policy", "bundle_digest", "algorithm", "value",
        "classification", "taxonomy", "cost", "amount", "currency", "source",
        "aggregation", "expires_at_unix_nano", "policy_event_id", "chain_id",
        "chain_version", "prompt", "Authorization", "secret", "decision_id",
        "result", "labels", "version", "metrics", "timer_rego_query_eval_ns",
        "path", "ids", "timestamp", "kind", "latency_ms", "occurred_at",
        "policy_name", "resource_type",
    }
)
EVENT_TYPES = sorted({seed["event_type"] for seed in SEEDS.values()} | {
    "approval.requested", "approval.rejected", "approval.expired",
    "approval.cancelled", "approval.execution_failed", "evidence.sealed",
    "policy", "", "x.y",
})

# Closed-vocabulary values the schemas accept, so an enum field can move
# between legal states (allow to challenge, enforce to monitor) and reach the
# appraisal logic instead of only ever failing validation.
WORDS = EVENT_TYPES + [
    "allow", "deny", "challenge", "not_applicable", "error", "enforce", "monitor",
    "disabled", "success", "denied", "cancelled", "timeout", "human", "system",
    "policy", "read", "write", "public", "internal", "confidential", "restricted",
    "sha256", "sha384", "sha512", "model_call", "agent_run", "workflow_run",
]


def value(fdp: Any, depth: int = 0) -> Any:
    """An arbitrary JSON-shaped value, with Python-only shapes mixed in."""
    if depth >= _MAX_DEPTH or fdp.remaining_bytes() == 0:
        return fdp.ConsumeUnicodeNoSurrogates(16)
    kind = fdp.ConsumeIntInRange(0, 9)
    if kind == 0:
        return None
    if kind == 1:
        return fdp.ConsumeBool()
    if kind == 2:
        # Straddle both the RFC 8785 safe-integer bound and uint64.
        return fdp.ConsumeIntInRange(-(2**65), 2**65)
    if kind == 3:
        return fdp.ConsumeFloat()
    if kind == 4:
        return fdp.ConsumeUnicodeNoSurrogates(64)
    if kind == 5:
        return str(fdp.ConsumeIntInRange(0, 2**70))
    if kind == 6:
        return fdp.ConsumeUnicode(24)
    if kind == 7:
        return [value(fdp, depth + 1) for _ in range(fdp.ConsumeIntInRange(0, _MAX_ITEMS))]
    return {
        key(fdp): value(fdp, depth + 1)
        for _ in range(fdp.ConsumeIntInRange(0, _MAX_ITEMS))
    }


def key(fdp: Any) -> str:
    if fdp.ConsumeBool():
        return KEYS[fdp.ConsumeIntInRange(0, len(KEYS) - 1)]
    return fdp.ConsumeUnicodeNoSurrogates(24)


def mutate(fdp: Any, document: dict[str, Any]) -> None:
    """Apply a handful of in-place edits somewhere in ``document``."""
    for _ in range(fdp.ConsumeIntInRange(0, 4)):
        if fdp.remaining_bytes() == 0:
            return
        target = _pick_object(fdp, document)
        op = fdp.ConsumeIntInRange(0, 3)
        if op == 0 and target:
            names = sorted(target)
            del target[names[fdp.ConsumeIntInRange(0, len(names) - 1)]]
        elif op == 1:
            target["event_type" if target is document and fdp.ConsumeBool() else key(fdp)] = (
                WORDS[fdp.ConsumeIntInRange(0, len(WORDS) - 1)]
                if fdp.ConsumeBool()
                else value(fdp)
            )
        elif op == 2 and target:
            names = sorted(target)
            target[names[fdp.ConsumeIntInRange(0, len(names) - 1)]] = (
                WORDS[fdp.ConsumeIntInRange(0, len(WORDS) - 1)]
                if fdp.ConsumeBool()
                else value(fdp)
            )
        else:
            target[key(fdp)] = value(fdp)


def event(fdp: Any) -> dict[str, Any]:
    base = copy.deepcopy(SEEDS[_SEED_NAMES[fdp.ConsumeIntInRange(0, len(_SEED_NAMES) - 1)]])
    mutate(fdp, base)
    return base


def _pick_object(fdp: Any, document: dict[str, Any]) -> dict[str, Any]:
    current = document
    for _ in range(fdp.ConsumeIntInRange(0, 2)):
        children = [child for child in current.values() if isinstance(child, dict)]
        if not children:
            break
        current = children[fdp.ConsumeIntInRange(0, len(children) - 1)]
    return current
