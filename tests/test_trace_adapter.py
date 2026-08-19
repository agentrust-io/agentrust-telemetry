import json
import sys
import unittest
from dataclasses import replace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    EvidenceAccumulator,
    SchemaValidator,
    TraceConfiguration,
    TraceFinalizationError,
    finalize_trace,
)


def fixture(name):
    return json.loads((ROOT / "conformance" / "fixtures" / "valid" / name).read_text())


class TraceAdapterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if sys.version_info < (3, 11):
            raise unittest.SkipTest("agentrust-trace requires Python 3.11+")
        from agentrust_trace import generate_key

        cls.key = generate_key()
        cls.validator = SchemaValidator(ROOT / "spec" / "schema")
        cls.config = TraceConfiguration(
            subject="spiffe://example.test/agent/workflow",
            model_provider="example",
            model_id="example-model",
            model_version="2026-08",
            build_digest="sha256:" + "b" * 64,
            build_slsa_level=1,
            origin_kind="self",
            origin_producer="example-runtime",
            appraisal_verifier="https://example.test/verifier",
            classification_taxonomy="example.enterprise.v1",
            classification_order=("public", "internal", "confidential", "restricted"),
        )

    def snapshot(self, *, completeness="complete", extra_events=()):
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        accumulator.append(fixture("policy-decision.json"))
        accumulator.append(fixture("data-flow.json"))
        for event in extra_events:
            accumulator.append(event)
        return accumulator.seal(completeness=completeness)

    def test_finalizes_signs_and_validates_official_trace_record(self):
        from agentrust_trace import TrustRecord, verify_record

        snapshot = self.snapshot()
        record = finalize_trace(snapshot, self.config, signing_key=self.key)
        TrustRecord.model_validate(record)
        verify_record(record, self.key.public_key(), max_age_seconds=None)
        self.assertEqual(record["runtime"]["measurement"], "sha256:" + snapshot.chain_digest)
        self.assertEqual(record["policy"]["bundle_hash"], "sha256:" + "a" * 64)
        self.assertEqual(record["policy"]["enforcement_mode"], "enforce")
        self.assertEqual(record["data_class"], "confidential")
        self.assertEqual(record["appraisal"]["status"], "contraindicated")
        self.assertNotIn("tool_transcript", record)

    def test_action_events_create_truthful_tool_transcript(self):
        action = fixture("action.json")
        snapshot = self.snapshot(extra_events=(action,))
        record = finalize_trace(snapshot, self.config, signing_key=self.key)
        self.assertEqual(record["tool_transcript"]["call_count"], 1)
        self.assertRegex(record["tool_transcript"]["hash"], r"^sha256:[0-9a-f]{64}$")

        changed = fixture("action.json")
        changed["outcome"] = "error"
        changed["error_type"] = "remote_error"
        changed_record = finalize_trace(
            self.snapshot(extra_events=(changed,)), self.config, signing_key=self.key
        )
        self.assertNotEqual(
            record["tool_transcript"]["hash"],
            changed_record["tool_transcript"]["hash"],
        )

    def test_linked_terminal_approval_resolves_policy_challenge(self):
        policy = fixture("policy-decision.json")
        policy["decision"] = "challenge"
        approval = fixture("approval.json")
        approval["event_type"] = "approval.approved"
        approval["policy_event_id"] = policy["event_id"]
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        accumulator.append(policy)
        accumulator.append(approval)
        accumulator.append(fixture("data-flow.json"))
        record = finalize_trace(
            accumulator.seal(completeness="complete"),
            self.config,
            signing_key=self.key,
        )
        self.assertEqual(record["appraisal"]["status"], "affirming")

        approval["policy_event_id"] = "018f0f7d-7a13-7cc2-8000-000000000099"
        approval["event_id"] = "018f0f7d-7a13-7cc2-8000-000000000098"
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        accumulator.append(policy)
        accumulator.append(approval)
        accumulator.append(fixture("data-flow.json"))
        record = finalize_trace(
            accumulator.seal(completeness="complete"),
            self.config,
            signing_key=self.key,
        )
        self.assertEqual(record["appraisal"]["status"], "warning")

    def test_refuses_unsealed_or_incomplete_evidence(self):
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        accumulator.append(fixture("policy-decision.json"))
        with self.assertRaisesRegex(TraceFinalizationError, "sealed"):
            finalize_trace(accumulator.snapshot(), self.config, signing_key=self.key)
        with self.assertRaisesRegex(TraceFinalizationError, "completeness"):
            finalize_trace(
                self.snapshot(completeness="incomplete"),
                self.config,
                signing_key=self.key,
            )

    def test_refuses_missing_signer(self):
        with self.assertRaisesRegex(TraceFinalizationError, "signing key"):
            finalize_trace(self.snapshot(), self.config, signing_key=None)

        class SignOnly:
            def sign(self, value):
                return value

        with self.assertRaisesRegex(TraceFinalizationError, "signing key"):
            finalize_trace(self.snapshot(), self.config, signing_key=SignOnly())

    def test_refuses_conflicting_policy_bundles(self):
        conflicting = fixture("policy-decision.json")
        conflicting["event_id"] = "018f0f7d-7a13-7cc2-8000-000000000099"
        conflicting["policy"]["bundle_digest"]["value"] = "f" * 64
        with self.assertRaisesRegex(TraceFinalizationError, "conflicting policy bundle"):
            finalize_trace(
                self.snapshot(extra_events=(conflicting,)),
                self.config,
                signing_key=self.key,
            )

    def test_refuses_unranked_classification(self):
        config = replace(self.config, classification_order=("public", "internal"))
        with self.assertRaisesRegex(TraceFinalizationError, "unranked"):
            finalize_trace(self.snapshot(), config, signing_key=self.key)

    def test_refuses_policy_digest_algorithm_trace_cannot_represent(self):
        unsupported = fixture("policy-decision.json")
        unsupported["policy"]["bundle_digest"] = {
            "algorithm": "sha512",
            "value": "f" * 128,
        }
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        accumulator.append(unsupported)
        accumulator.append(fixture("data-flow.json"))
        with self.assertRaisesRegex(TraceFinalizationError, "does not support"):
            finalize_trace(
                accumulator.seal(completeness="complete"),
                self.config,
                signing_key=self.key,
            )


if __name__ == "__main__":
    unittest.main()
