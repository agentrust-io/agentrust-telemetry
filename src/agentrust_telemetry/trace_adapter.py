"""Optional mapping from sealed evidence to an official TRACE v0.2 record."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

import rfc8785

from .errors import TraceFinalizationError
from .evidence import CANONICALIZATION_PROFILE, EvidenceSnapshot, _entry_digest


OriginKind = Literal["self", "third-party-control-plane", "log-import"]


@dataclass(frozen=True)
class TraceConfiguration:
    subject: str
    model_provider: str
    model_id: str
    build_digest: str
    origin_kind: OriginKind
    origin_producer: str
    appraisal_verifier: str
    classification_taxonomy: str
    classification_order: tuple[str, ...]
    model_version: str | None = None
    build_slsa_level: int = 0
    build_builder: str | None = None
    build_provenance_uri: str | None = None
    transparency: str | None = None


def finalize_trace(
    snapshot: EvidenceSnapshot,
    config: TraceConfiguration,
    *,
    signing_key: Any,
) -> dict[str, Any]:
    """Build, sign, structurally validate, and self-verify a TRACE record."""
    trace = _trace_package()
    _require_finalizable(snapshot, config, signing_key)
    _verify_chain(snapshot)
    events = [entry.event for entry in snapshot.entries]

    try:
        bundle_hash, enforcement_mode = _policy_binding(events)
        data_class = _highest_data_class(events, config)
        tool_transcript = _tool_transcript(snapshot)
        appraisal_status = _appraisal(events)
        issued_at = max(int(event["time_unix_nano"]) for event in events) // 1_000_000_000
    except TraceFinalizationError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise TraceFinalizationError(
            f"evidence contains a malformed event: {type(exc).__name__}: {exc}"
        ) from exc
    record: dict[str, Any] = {
        "eat_profile": trace.TRACE_PROFILE_V0_2,
        "iat": issued_at,
        "subject": config.subject,
        "model": {
            "provider": config.model_provider,
            "model_id": config.model_id,
            **({"version": config.model_version} if config.model_version else {}),
        },
        "runtime": {
            "platform": "software-only",
            "measurement": f"sha256:{snapshot.chain_digest}",
        },
        "policy": {
            "bundle_hash": bundle_hash,
            "enforcement_mode": enforcement_mode,
        },
        "data_class": data_class,
        **({"tool_transcript": tool_transcript} if tool_transcript else {}),
        "origin": {
            "kind": config.origin_kind,
            "producer": config.origin_producer,
        },
        "build_provenance": {
            "slsa_level": config.build_slsa_level,
            "digest": config.build_digest,
            **({"builder": config.build_builder} if config.build_builder else {}),
            **(
                {"provenance_uri": config.build_provenance_uri}
                if config.build_provenance_uri
                else {}
            ),
        },
        "appraisal": {
            "status": appraisal_status,
            "verifier": config.appraisal_verifier,
            "timestamp": issued_at,
        },
        **({"transparency": config.transparency} if config.transparency else {}),
    }
    try:
        signed = trace.sign_record(record, signing_key)
        trace.TrustRecord.model_validate(signed)
        trace.verify_record(signed, signing_key.public_key(), max_age_seconds=None)
    except Exception as exc:
        raise TraceFinalizationError(
            f"official TRACE signing or validation failed: {type(exc).__name__}: {exc}"
        ) from exc
    return signed


def _require_finalizable(
    snapshot: EvidenceSnapshot, config: TraceConfiguration, signing_key: Any
) -> None:
    if not snapshot.sealed:
        raise TraceFinalizationError("evidence snapshot must be sealed")
    if snapshot.completeness != "complete":
        raise TraceFinalizationError("TRACE finalization requires completeness='complete'")
    if not snapshot.entries or not snapshot.chain_digest:
        raise TraceFinalizationError("TRACE finalization requires non-empty chained evidence")
    if (
        signing_key is None
        or not callable(getattr(signing_key, "sign", None))
        or not callable(getattr(signing_key, "public_key", None))
    ):
        raise TraceFinalizationError("a caller-supplied signing key is required")
    required = {
        "subject": config.subject,
        "model_provider": config.model_provider,
        "model_id": config.model_id,
        "build_digest": config.build_digest,
        "origin_producer": config.origin_producer,
        "appraisal_verifier": config.appraisal_verifier,
    }
    missing = sorted(name for name, value in required.items() if not value)
    if missing:
        raise TraceFinalizationError(f"trusted TRACE configuration is missing: {missing}")
    if len(set(config.classification_order)) != len(config.classification_order):
        raise TraceFinalizationError("classification_order contains duplicates")


def _verify_chain(snapshot: EvidenceSnapshot) -> None:
    """Recompute the evidence chain the measurement will commit to.

    The record's measurement is ``snapshot.chain_digest`` while its appraisal is
    derived from ``snapshot.entries``. Unless the entries still hash to that
    digest, the signed record could appraise events the measurement does not
    cover (an entry edited, dropped, or reordered after sealing).
    """
    if snapshot.canonicalization_profile != CANONICALIZATION_PROFILE:
        raise TraceFinalizationError(
            f"unsupported canonicalization profile: {snapshot.canonicalization_profile!r}"
        )
    previous: str | None = None
    for position, entry in enumerate(snapshot.entries):
        try:
            recomputed = _entry_digest(position, previous, entry.event)
            event_id = entry.event.get("event_id")
            run_id = entry.event.get("run_id")
        except (TypeError, ValueError, AttributeError, rfc8785.CanonicalizationError) as exc:
            raise TraceFinalizationError(
                f"evidence chain does not verify at sequence {position}: "
                f"{type(exc).__name__}"
            ) from exc
        if (
            entry.sequence != position
            or entry.previous_digest != previous
            or entry.digest != recomputed
            or entry.event_id != event_id
            or run_id != snapshot.run_id
        ):
            raise TraceFinalizationError(
                f"evidence chain does not verify at sequence {position}"
            )
        previous = recomputed
    if snapshot.chain_digest != previous:
        raise TraceFinalizationError("evidence chain does not verify: chain_digest mismatch")


def _policy_binding(events: list[dict[str, Any]]) -> tuple[str, str]:
    decisions = [event for event in events if event["event_type"] == "policy.decision"]
    if not decisions:
        raise TraceFinalizationError("no policy decision evidence is present")
    if any("bundle_digest" not in event["policy"] for event in decisions):
        raise TraceFinalizationError("every policy decision must carry bundle_digest")
    algorithms = {
        event["policy"]["bundle_digest"]["algorithm"] for event in decisions
    }
    unsupported = sorted(algorithms - {"sha256", "sha384"})
    if unsupported:
        raise TraceFinalizationError(
            f"TRACE does not support observed policy digest algorithms: {unsupported}"
        )
    bundles = {
        f"{event['policy']['bundle_digest']['algorithm']}:{event['policy']['bundle_digest']['value']}"
        for event in decisions
    }
    if len(bundles) != 1:
        raise TraceFinalizationError("conflicting policy bundle digests are present")
    modes = {event["enforcement_mode"] for event in decisions}
    if len(modes) != 1:
        raise TraceFinalizationError("conflicting policy enforcement modes are present")
    mapped = {"enforce": "enforce", "monitor": "advisory", "disabled": "declared"}
    return next(iter(bundles)), mapped[next(iter(modes))]


def _highest_data_class(
    events: list[dict[str, Any]], config: TraceConfiguration
) -> str:
    flows = [event for event in events if event["event_type"] == "data_flow.observed"]
    if not flows:
        raise TraceFinalizationError("no classified data-flow evidence is present")
    if any(
        event["classification"]["taxonomy"] != config.classification_taxonomy
        for event in flows
    ):
        raise TraceFinalizationError("data-flow taxonomy conflicts with TRACE configuration")
    rank = {value: index for index, value in enumerate(config.classification_order)}
    values = [event["classification"]["value"] for event in flows]
    unknown = sorted(set(values) - set(rank))
    if unknown:
        raise TraceFinalizationError(f"unranked data classifications are present: {unknown}")
    return max(values, key=rank.__getitem__)


def _appraisal(events: list[dict[str, Any]]) -> str:
    decisions = {
        event["event_id"]: event["decision"]
        for event in events
        if event["event_type"] == "policy.decision"
    }
    approvals = [event for event in events if event["event_type"].startswith("approval.")]
    approval_types = {event["event_type"] for event in approvals}
    if set(decisions.values()).intersection({"deny", "error"}) or approval_types.intersection(
        {"approval.rejected", "approval.expired", "approval.execution_failed"}
    ):
        return "contraindicated"
    approved_policy_events = _bound_approved_policy_events(approvals)
    unresolved_challenges = {
        event_id
        for event_id, decision in decisions.items()
        if decision == "challenge" and event_id not in approved_policy_events
    }
    if unresolved_challenges or "approval.cancelled" in approval_types:
        return "warning"
    if decisions or approval_types:
        return "affirming"
    return "none"


def _bound_approved_policy_events(approvals: list[dict[str, Any]]) -> set[str]:
    """Return challenges resolved by a complete, unexpired request/resolution pair."""
    requests = [
        event for event in approvals if event["event_type"] == "approval.requested"
    ]
    resolved: set[str] = set()
    binding_fields = (
        "approval_id",
        "policy_event_id",
        "action_digest",
        "chain_id",
        "chain_version",
        "requested_at_unix_nano",
        "expires_at_unix_nano",
    )
    for approval in approvals:
        if approval["event_type"] != "approval.approved":
            continue
        for request in requests:
            if any(
                field not in approval
                or field not in request
                or approval[field] != request[field]
                for field in binding_fields
            ):
                continue
            try:
                requested_at = int(request["requested_at_unix_nano"])
                approved_at = int(approval["time_unix_nano"])
                expires_at = int(request["expires_at_unix_nano"])
            except (TypeError, ValueError):
                continue
            if requested_at <= approved_at <= expires_at:
                resolved.add(str(approval["policy_event_id"]))
                break
    return resolved


def _tool_transcript(snapshot: EvidenceSnapshot) -> dict[str, Any] | None:
    actions = [
        {"sequence": entry.sequence, "event": entry.event}
        for entry in snapshot.entries
        if entry.event["event_type"] == "action.executed"
    ]
    if not actions:
        return None
    canonical = rfc8785.dumps(actions)
    return {
        "hash": "sha256:" + hashlib.sha256(canonical).hexdigest(),
        "call_count": len(actions),
    }


def _trace_package() -> Any:
    try:
        import agentrust_trace
    except ImportError as exc:
        raise TraceFinalizationError(
            "TRACE finalization requires the 'trace' optional dependency"
        ) from exc
    return agentrust_trace
