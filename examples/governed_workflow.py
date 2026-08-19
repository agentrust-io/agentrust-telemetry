"""Runnable AGT-to-OTel-to-evidence-to-TRACE reference workflow."""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agentrust_telemetry import (
    EventFactory,
    EvidenceAccumulator,
    OTelLogEmitter,
    OTelMetricEmitter,
    SchemaValidator,
    TelemetryClient,
    TraceConfiguration,
    agt_approval_request,
    agt_approval_resolution,
    agt_policy_decision_record,
    finalize_trace,
)


RUN_ID = "run-reference-001"
AGENT_ID = "spiffe://example.test/agent/builder"
DIGEST = "sha256:" + "a" * 64
BUNDLE = {"algorithm": "sha256", "value": "b" * 64}
START = datetime(2026, 8, 18, 12, 0, tzinfo=timezone.utc)


@dataclass
class PolicyDecisionRecord:
    action_digest: str = DIGEST
    policy_rule_id: str = "production-deploy-approval"
    policy_version: str = "7"
    approval_chain_id: str = "release-operators"
    approval_chain_version: str = "3"
    verdict: str = "require_approval"
    policy_decision_id: str = "pd_reference_001"
    decided_at: datetime = START


@dataclass
class ApprovalRequest:
    policy_decision_id: str = "pd_reference_001"
    action_digest: str = DIGEST
    agent_id: str = AGENT_ID
    operation: str = "deploy"
    policy_version: str = "7"
    approval_chain_id: str = "release-operators"
    approval_chain_version: str = "3"
    expires_at: datetime = START + timedelta(minutes=10)
    approval_request_id: str = "ar_reference_001"
    requested_at: datetime = START + timedelta(seconds=1)


@dataclass
class ApprovalResolution:
    approval_request_id: str = "ar_reference_001"
    outcome: str = "allow"
    action_digest: str = DIGEST
    policy_version: str = "7"
    approval_chain_version: str = "3"
    approval_resolution_id: str = "apr_reference_001"
    resolved_at: datetime = START + timedelta(seconds=5)
    final_entry_digest: str = "sha256:" + "c" * 64


class RecordingLogEmitter:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def emit(self, **record: Any) -> None:
        self.records.append(record)


class RecordingSpanExporter:
    def __init__(self) -> None:
        self.spans: list[Any] = []

    def export(self, spans: Any) -> Any:
        from opentelemetry.sdk.trace.export import SpanExportResult

        self.spans.extend(spans)
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        return True


class JsonlEvidenceStore:
    """Small fsync-backed example store, idempotent by event ID."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.event_ids: set[str] = set()

    def append(self, entry: Any) -> bool:
        if entry.event_id in self.event_ids:
            return True
        payload = {
            "sequence": entry.sequence,
            "event_id": entry.event_id,
            "previous_digest": entry.previous_digest,
            "digest": entry.digest,
            "event": entry.event,
        }
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        self.event_ids.add(entry.event_id)
        return True


def run_scenario() -> dict[str, Any]:
    from agentrust_trace import generate_key
    from opentelemetry import trace
    from opentelemetry.sdk.metrics import MeterProvider
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    validator = SchemaValidator.bundled()
    factory = EventFactory(
        validator,
        producer_name="governed-workflow-example",
        producer_version="0.1.0",
    )
    span_exporter = RecordingSpanExporter()
    tracer_provider = TracerProvider()
    tracer_provider.add_span_processor(SimpleSpanProcessor(span_exporter))
    tracer = tracer_provider.get_tracer("agentrust.reference")
    metric_reader = InMemoryMetricReader()
    meter_provider = MeterProvider(metric_readers=[metric_reader])
    log_target = RecordingLogEmitter()

    with tempfile.TemporaryDirectory(prefix="agentrust-reference-") as directory:
        store = JsonlEvidenceStore(Path(directory) / "evidence.jsonl")
        accumulator = EvidenceAccumulator(
            RUN_ID,
            validator,
            durable_append=store.append,
        )
        client = TelemetryClient(
            validator,
            span_resolver=trace.get_current_span,
            log_emitter=OTelLogEmitter(log_target),
            evidence_sink=accumulator,
            metric_emitter=OTelMetricEmitter(
                meter_provider.get_meter("agentrust.reference"),
                classification_values=frozenset({"public", "confidential"}),
            ),
        )
        policy_source = PolicyDecisionRecord()
        request_source = ApprovalRequest()
        resolution_source = ApprovalResolution()
        results = []
        with tracer.start_as_current_span("governed.deploy") as span:
            context = span.get_span_context()
            trace_id = f"{context.trace_id:032x}"
            span_id = f"{context.span_id:016x}"
            policy = agt_policy_decision_record(
                factory,
                policy_source,
                run_id=RUN_ID,
                agent_id=AGENT_ID,
                action_type="environment.deploy",
                resource_type="environment",
                policy_engine_version="5.0.0",
                bundle_digest=BUNDLE,
                evaluation_duration_ns=250_000,
                trace_id=trace_id,
                span_id=span_id,
            )
            request = agt_approval_request(
                factory,
                request_source,
                policy_source,
                run_id=RUN_ID,
                trace_id=trace_id,
                span_id=span_id,
            )
            approval = agt_approval_resolution(
                factory,
                resolution_source,
                request_source,
                run_id=RUN_ID,
                trace_id=trace_id,
                span_id=span_id,
            )
            data_flow = factory.build(
                "data_flow.observed",
                run_id=RUN_ID,
                agent_id=AGENT_ID,
                trace_id=trace_id,
                span_id=span_id,
                direction="read",
                source={"kind": "repository", "id": "application-source"},
                destination={"kind": "agent", "id": AGENT_ID},
                classification={
                    "taxonomy": "example.enterprise.v1",
                    "value": "confidential",
                    "producer": "example-classifier",
                },
                purpose="deployment-generation",
                policy_decision="allow",
                content_digest={"algorithm": "sha256", "value": "d" * 64},
                transformation="metadata_only",
            )
            action = factory.build(
                "action.executed",
                run_id=RUN_ID,
                agent_id=AGENT_ID,
                trace_id=trace_id,
                span_id=span_id,
                action_id="deploy-reference-001",
                action_kind="tool",
                action_name="deploy_application",
                operation="deploy",
                outcome="success",
                duration_ns=50_000_000,
                action_digest={"algorithm": "sha256", "value": "a" * 64},
                policy_event_id=policy["event_id"],
                approval_id=request["approval_id"],
                target={"kind": "environment", "id": "staging"},
            )
            for event in (policy, request, approval, data_flow, action):
                results.append(client.emit(event))

        snapshot = accumulator.seal(completeness="complete")
        record = finalize_trace(
            snapshot,
            TraceConfiguration(
                subject=AGENT_ID,
                model_provider="example",
                model_id="architecture-agent",
                model_version="2026-08",
                build_digest="sha256:" + "e" * 64,
                build_slsa_level=1,
                origin_kind="self",
                origin_producer="governed-workflow-example",
                appraisal_verifier="https://example.test/verifier",
                classification_taxonomy="example.enterprise.v1",
                classification_order=("public", "confidential"),
            ),
            signing_key=generate_key(),
        )
        evidence_lines = store.path.read_text(encoding="utf-8").splitlines()

    metric_data = metric_reader.get_metrics_data()
    metric_points = sum(
        len(metric.data.data_points)
        for resource in metric_data.resource_metrics
        for scope in resource.scope_metrics
        for metric in scope.metrics
    )
    span_events = sum(len(span.events) for span in span_exporter.spans)
    return {
        "events_accepted": sum(result.accepted for result in results),
        "events_fully_projected": sum(
            result.evidence_persisted
            and result.span_event_emitted
            and result.log_emitted
            and result.metrics_emitted
            and not result.projection_errors
            for result in results
        ),
        "evidence_entries": len(evidence_lines),
        "span_events": span_events,
        "log_records": len(log_target.records),
        "metric_points": metric_points,
        "trace_appraisal": record["appraisal"]["status"],
        "trace_data_class": record["data_class"],
        "trace_tool_calls": record["tool_transcript"]["call_count"],
    }


if __name__ == "__main__":
    print(json.dumps(run_scenario(), indent=2, sort_keys=True))
