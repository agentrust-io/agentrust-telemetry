"""Every refusal in `trace_adapter.py`, exercised.

`trace_adapter.py` has sixteen `raise TraceFinalizationError` sites. Five test
methods in `tests/test_trace_adapter.py` hold six of them up. Replacing any of
the other ten with `pass`, one at a time, leaves `python -m unittest discover
-s tests` at exit 0, so those ten are correct and unexercised. This file covers
those ten.

Eight of them are refused because of the events. Each is built with
`EvidenceAccumulator` and driven through `finalize_trace` rather than by
handing the adapter a dict, so a case that passes is also evidence the refusal
is reachable from a schema-valid event stream rather than defensive.

Two are different in kind, and the file says so where they sit. No event
stream can produce either. The missing optional dependency is reached by
blocking the import, which is the only way in, so that case does not go
through `finalize_trace` at all. The failure inside official signing does go
through `finalize_trace`, on an accumulator-built snapshot, with a signing key
that passes the shape check and then fails when used.
"""

import copy
import json
import sys
import unittest
from unittest import mock
from dataclasses import replace
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (  # noqa: E402
    EvidenceAccumulator,
    SchemaValidator,
    TraceConfiguration,
    TraceFinalizationError,
    finalize_trace,
)
from agentrust_telemetry import trace_adapter  # noqa: E402


def fixture(name):
    return json.loads((ROOT / "conformance" / "fixtures" / "valid" / name).read_text())


class TraceAdapterRefusalTests(unittest.TestCase):
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

    def snapshot(self, events, *, completeness="complete"):
        accumulator = EvidenceAccumulator("run-governed-sdlc-001", self.validator)
        for event in events:
            accumulator.append(event)
        return accumulator.seal(completeness=completeness)

    def finalize(self, events, *, config=None, completeness="complete"):
        return finalize_trace(
            self.snapshot(events, completeness=completeness),
            config or self.config,
            signing_key=self.key,
        )

    def assertRefuses(self, message, events, *, config=None, completeness="complete"):
        with self.assertRaises(TraceFinalizationError) as caught:
            self.finalize(events, config=config, completeness=completeness)
        self.assertIn(message, str(caught.exception))

    # -- the evidence itself -------------------------------------------------

    def test_an_empty_run_carries_no_chained_evidence(self):
        self.assertRefuses("non-empty chained evidence", [])

    # -- the trusted configuration -------------------------------------------

    def test_every_required_configuration_field_is_named_when_absent(self):
        for field in ("subject", "model_provider", "model_id", "build_digest",
                      "origin_producer", "appraisal_verifier"):
            with self.subTest(field=field):
                config = replace(self.config, **{field: ""})
                with self.assertRaises(TraceFinalizationError) as caught:
                    self.finalize([fixture("policy-decision.json"),
                                   fixture("data-flow.json")], config=config)
                message = str(caught.exception)
                self.assertIn("trusted TRACE configuration is missing", message)
                self.assertIn(field, message)

    def test_a_repeated_classification_cannot_rank_anything(self):
        order = ("public", "internal", "public")
        config = replace(self.config, classification_order=order)
        self.assertRefuses(
            "classification_order contains duplicates",
            [fixture("policy-decision.json"), fixture("data-flow.json")],
            config=config,
        )

    # -- the policy binding ---------------------------------------------------

    def test_a_run_with_no_policy_decision_has_no_policy_to_bind(self):
        self.assertRefuses(
            "no policy decision evidence is present", [fixture("data-flow.json")]
        )

    def test_a_policy_decision_without_a_bundle_digest_is_refused(self):
        event = copy.deepcopy(fixture("policy-decision.json"))
        del event["policy"]["bundle_digest"]
        self.validator.validate(event)  # the schema permits it; the adapter must not
        self.assertRefuses(
            "every policy decision must carry bundle_digest",
            [event, fixture("data-flow.json")],
        )

    def test_two_decisions_disagreeing_on_enforcement_cannot_produce_one_mode(self):
        first = fixture("policy-decision.json")
        second = copy.deepcopy(first)
        second["event_id"] = "018f0f7d-7a13-7cc2-8000-0000000000f1"
        second["enforcement_mode"] = "monitor"
        self.assertRefuses(
            "conflicting policy enforcement modes are present",
            [first, second, fixture("data-flow.json")],
        )

    # -- the data classification ----------------------------------------------

    def test_a_run_with_no_data_flow_has_nothing_to_classify(self):
        self.assertRefuses(
            "no classified data-flow evidence is present",
            [fixture("policy-decision.json")],
        )

    def test_a_taxonomy_the_configuration_does_not_name_is_refused(self):
        config = replace(self.config, classification_taxonomy="example.other.v1")
        self.assertRefuses(
            "data-flow taxonomy conflicts with TRACE configuration",
            [fixture("policy-decision.json"), fixture("data-flow.json")],
            config=config,
        )

    # -- the two that no event stream can produce ------------------------------

    def test_the_optional_dependency_is_named_when_it_is_absent(self):
        import builtins

        original = builtins.__import__

        def refuse(name, *args, **kwargs):
            if name == "agentrust_trace":
                raise ImportError("not installed")
            return original(name, *args, **kwargs)

        builtins.__import__ = refuse
        try:
            with self.assertRaises(TraceFinalizationError) as caught:
                trace_adapter._trace_package()
            self.assertIn("optional dependency", str(caught.exception))
        finally:
            builtins.__import__ = original

    def test_a_failure_inside_official_signing_is_reported_as_one(self):
        """A key that satisfies the type check and then fails when used.

        `object()` would not reach here, and neither does a duck type: since
        agentrust-trace 0.10.0 the signing path requires a real
        Ed25519PrivateKey rather than anything carrying a `sign` method, so a
        hand-rolled stand-in is refused for the wrong reason and this test
        would pass on a refusal it is not about.

        A mock specced to Ed25519PrivateKey satisfies that isinstance check and
        still fails when actually used, which is the case this covers: a real
        key whose hardware backing is unavailable at the moment of signing.
        """
        FailsWhenUsed = mock.MagicMock(spec=Ed25519PrivateKey)
        FailsWhenUsed.sign.side_effect = RuntimeError("hardware signer unavailable")
        FailsWhenUsed.public_key.return_value = self.key.public_key()

        snapshot = self.snapshot(
            [fixture("policy-decision.json"), fixture("data-flow.json")]
        )
        with self.assertRaises(TraceFinalizationError) as caught:
            finalize_trace(snapshot, self.config, signing_key=FailsWhenUsed)
        message = str(caught.exception)
        self.assertIn("official TRACE signing or validation failed", message)
        self.assertIn("hardware signer unavailable", message)


if __name__ == "__main__":
    unittest.main()
