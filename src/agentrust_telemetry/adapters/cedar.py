"""Cedar authorization-response adapter with explicit safe fields."""

from __future__ import annotations

import re
from typing import Any, Iterable

from .base import EventFactory


def cedar_policy_decision(
    factory: EventFactory,
    *,
    run_id: str,
    agent_id: str,
    decision: str,
    cedar_version: str,
    bundle_digest: dict[str, str],
    action_type: str,
    resource_type: str,
    evaluation_duration_ns: int,
    determining_policy_ids: Iterable[str] = (),
    error_codes: Iterable[str] = (),
    enforcement_mode: str = "enforce",
    input_digest: dict[str, str] | None = None,
    **envelope: Any,
) -> dict[str, Any]:
    normalized = decision.lower()
    if normalized not in {"allow", "deny"}:
        raise ValueError("Cedar decision must be Allow or Deny")
    policy_ids = _identifiers(determining_policy_ids, "determining_policy_ids")
    errors = _identifiers(error_codes, "error_codes")
    if any(re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", value) is None for value in errors):
        raise ValueError("Cedar error_codes must be identifiers, not error messages")
    reason_codes = [*(f"cedar.policy:{value}" for value in policy_ids), *(f"cedar.error:{value}" for value in errors)]
    if len(reason_codes) > 32:
        raise ValueError("Cedar reasons and errors exceed the 32-code contract limit")
    policy: dict[str, Any] = {
        "engine": "cedar",
        "engine_version": cedar_version,
        "bundle_digest": bundle_digest,
        **({"policy_id": policy_ids[0]} if len(policy_ids) == 1 else {}),
        **({"input_digest": input_digest} if input_digest else {}),
    }
    return factory.build(
        "policy.decision",
        run_id=run_id,
        agent_id=agent_id,
        decision=normalized,
        policy=policy,
        action_type=action_type,
        resource_type=resource_type,
        enforcement_mode=enforcement_mode,
        evaluation_duration_ns=evaluation_duration_ns,
        reason_codes=reason_codes,
        **envelope,
    )


def _identifiers(values: Iterable[str], field: str) -> list[str]:
    if isinstance(values, (str, bytes)):
        raise ValueError(f"Cedar {field} must be an iterable of strings, not a string")
    normalized = sorted(set(values))
    if any(not isinstance(value, str) or not value for value in normalized):
        raise ValueError(f"Cedar {field} must contain non-empty strings")
    return normalized
