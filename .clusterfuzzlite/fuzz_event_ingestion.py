#!/usr/bin/python3
"""Fuzz event validation and every projection a validated event reaches.

SchemaValidator.validate is the gate in front of spans, logs, metrics and the
evidence chain. Its contract is that anything it refuses surfaces as
EventValidationError. Once it accepts an event, each projection must be able to
carry it: span attributes are scalar and drawn only from the documented
mapping, the log body is an exact copy, the metric projector does not raise,
and the evidence accumulator either chains it or refuses with EvidenceError.

The second half fuzzes the inbound W3C and AgentTrust propagation headers,
which arrive from whoever called this agent. extract_context must either
return or raise PropagationError, and whatever it returns must satisfy the same
length and line-break rules inject_context enforces on the way out.
"""
import logging
import sys

import atheris

with atheris.instrument_imports():
    from agentrust_telemetry import (
        EventValidationError,
        EvidenceAccumulator,
        EvidenceError,
        PropagationError,
        SchemaValidator,
        extract_context,
    )
    from agentrust_telemetry.otel import OTelMetricEmitter
    from agentrust_telemetry.projection import DIRECT_ATTRIBUTES, log_record, span_attributes
    from agentrust_telemetry.propagation import (
        RUN_ID_HEADER,
        UPSTREAM_AGENT_ID_HEADER,
        WORKFLOW_ID_HEADER,
    )

    import _fuzz_build

# OTel logs a warning for every malformed baggage entry; at fuzzing rates that
# is only noise and slows the run down.
logging.getLogger("opentelemetry").setLevel(logging.CRITICAL)

_VALIDATOR = SchemaValidator.bundled()
_PERMISSIVE = SchemaValidator(
    _VALIDATOR.schema_directory,
    allowed_attribute_keys=frozenset({"vendor.a", "vendor.b", "x"}),
)
_HEADERS = (
    "traceparent", "tracestate", "baggage",
    RUN_ID_HEADER, WORKFLOW_ID_HEADER, UPSTREAM_AGENT_ID_HEADER,
    RUN_ID_HEADER.upper(), "X-AgenTrust-Agent-Id",
)
_SCALARS = (str, int, float, bool)


class _Instrument:
    def add(self, amount, attributes=None):
        pass

    def record(self, amount, attributes=None):
        pass


class _Meter:
    def create_counter(self, *args, **kwargs):
        return _Instrument()

    def create_histogram(self, *args, **kwargs):
        return _Instrument()


_METRICS = OTelMetricEmitter(_Meter(), classification_values=frozenset({"confidential"}))


def _check_event(fdp: atheris.FuzzedDataProvider) -> None:
    event = _fuzz_build.event(fdp)
    if fdp.ConsumeBool():
        event["attributes"] = {
            _fuzz_build.key(fdp) if fdp.ConsumeBool() else "vendor.a": _fuzz_build.value(fdp)
        }
    validator = _PERMISSIVE if fdp.ConsumeBool() else _VALIDATOR
    try:
        validator.validate(event)
    except EventValidationError:
        return

    attributes = span_attributes(event)
    assert set(attributes) <= set(DIRECT_ATTRIBUTES.values()), attributes
    assert all(isinstance(item, _SCALARS) for item in attributes.values()), attributes
    record = log_record(event, None)
    assert record["body"] == event and record["body"] is not event
    _METRICS.emit(event)
    try:
        EvidenceAccumulator(event["run_id"], validator).append(event)
    except EvidenceError:
        pass


def _check_headers(fdp: atheris.FuzzedDataProvider) -> None:
    carrier = {}
    for _ in range(fdp.ConsumeIntInRange(0, 6)):
        name = (
            _HEADERS[fdp.ConsumeIntInRange(0, len(_HEADERS) - 1)]
            if fdp.ConsumeBool()
            else fdp.ConsumeUnicodeNoSurrogates(16)
        )
        carrier[name] = fdp.ConsumeUnicodeNoSurrogates(fdp.ConsumeIntInRange(0, 600))
    try:
        extracted = extract_context(carrier)
    except PropagationError:
        return
    for field in (extracted.run_id, extracted.workflow_id, extracted.upstream_agent_id):
        if field is not None:
            assert isinstance(field, str) and 0 < len(field) <= 512, field
            assert "\r" not in field and "\n" not in field, field


def TestOneInput(data: bytes) -> None:
    fdp = atheris.FuzzedDataProvider(data)
    if fdp.ConsumeIntInRange(0, 3):
        _check_event(fdp)
    else:
        _check_headers(fdp)


def main() -> None:
    atheris.Setup(sys.argv, TestOneInput)
    atheris.Fuzz()


if __name__ == "__main__":
    main()
