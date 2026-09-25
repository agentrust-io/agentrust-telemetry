#!/usr/bin/python3
"""Fuzz the mapping from sealed evidence to a signed TRACE record.

finalize_trace derives the policy binding, data class, tool transcript and
appraisal from a run's events and signs the result. Its contract is that it
either returns a record that verifies or raises TraceFinalizationError; it
must never overstate what the evidence shows. Three properties are asserted:

1. Nothing outside TraceFinalizationError escapes, for any run the evidence
   accumulator accepted.
2. A record that is produced verifies, commits to the snapshot's chain digest,
   and is "contraindicated" whenever the run holds a deny or error decision.
3. The same snapshot with any one entry edited after sealing is refused, since
   the measurement would no longer cover the events that were appraised.
"""
import sys

import atheris

with atheris.instrument_imports():
    from agentrust_telemetry import (
        EventValidationError,
        EvidenceAccumulator,
        EvidenceError,
        SchemaValidator,
        TraceConfiguration,
        TraceFinalizationError,
        finalize_trace,
    )

    import _fuzz_build
    from _fuzz_seeds import RUN_ID

from agentrust_trace import generate_key, verify_record

_KEY = generate_key()
_VALIDATOR = SchemaValidator.bundled()
_CONFIG = TraceConfiguration(
    subject="spiffe://example.test/agent/workflow",
    model_provider="example",
    model_id="example-model",
    build_digest="sha256:" + "b" * 64,
    build_slsa_level=1,
    origin_kind="self",
    origin_producer="example-runtime",
    appraisal_verifier="https://example.test/verifier",
    classification_taxonomy="example.enterprise.v1",
    classification_order=("public", "internal", "confidential", "restricted"),
)


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    accumulator = EvidenceAccumulator(RUN_ID, _VALIDATOR)
    accepted = []
    for index in range(fdp.ConsumeIntInRange(1, 6)):
        event = _fuzz_build.event(fdp)
        event["run_id"] = RUN_ID
        # Distinct ids so duplicates are a mutation outcome, not the default.
        if isinstance(event.get("event_id"), str) and fdp.ConsumeBool():
            event["event_id"] = f"018f0f7d-7a13-7cc2-8000-{index:012x}"
        try:
            accumulator.append(event)
        except (EventValidationError, EvidenceError):
            continue
        accepted.append(event)
    snapshot = accumulator.seal(completeness="complete")

    try:
        record = finalize_trace(snapshot, _CONFIG, signing_key=_KEY)
    except TraceFinalizationError:
        return

    verify_record(record, _KEY.public_key(), max_age_seconds=None)
    assert record["runtime"]["measurement"] == f"sha256:{snapshot.chain_digest}"
    if any(
        event["event_type"] == "policy.decision" and event["decision"] in ("deny", "error")
        for event in accepted
    ):
        assert record["appraisal"]["status"] == "contraindicated", record["appraisal"]

    victim = snapshot.entries[fdp.ConsumeIntInRange(0, len(snapshot.entries) - 1)]
    victim.event["producer"]["version"] = victim.event["producer"]["version"] + "-edited"
    try:
        finalize_trace(snapshot, _CONFIG, signing_key=_KEY)
    except TraceFinalizationError:
        return
    raise AssertionError("an entry edited after sealing was signed")


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
