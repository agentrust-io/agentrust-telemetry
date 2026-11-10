"""Timestamp trust boundaries, including self-consistent imported snapshots."""

import copy
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentrust_telemetry import (
    TraceConfiguration,
    TraceFinalizationError,
    finalize_trace,
)
from agentrust_telemetry.evidence import (
    CANONICALIZATION_PROFILE,
    EvidenceEntry,
    EvidenceSnapshot,
    _entry_digest,
)
from agentrust_telemetry.trace_adapter import _action_approval_binding, _bound_approvals

INVALID = (True, False, 1, 1.0, None, "", "01", "+1", "-1", " 1", "1 ",
           "1\n", "1.0", "1e0", "١", "１", "100000000000000000000")
FIELDS = ("time_unix_nano", "requested_at_unix_nano", "expires_at_unix_nano")


def events():
    return json.loads(
        (ROOT / "conformance/appraisal/approved-action-matches.json").read_text()
    )["events"]


def snapshot(rows):
    # Deliberately bypass schema ingestion and recompute every digest. These
    # tests exercise the public finalizer, not a stale-chain refusal.
    entries, previous = [], None
    for sequence, event in enumerate(rows):
        digest = _entry_digest(sequence, previous, event)
        entries.append(EvidenceEntry(sequence, event["event_id"], previous, digest, event))
        previous = digest
    return EvidenceSnapshot(
        run_id=rows[0]["run_id"], entries=tuple(entries), chain_digest=previous,
        canonicalization_profile=CANONICALIZATION_PROFILE,
        completeness="complete", sealed=True,
    )


class TimestampBindingTests(unittest.TestCase):
    def binding(self, rows):
        approvals = rows[1:3]
        return _action_approval_binding(
            rows, {rows[0]["event_id"]: "challenge"}, approvals,
            _bound_approvals(approvals),
        )

    def test_canonical_window_boundaries_and_expiration(self):
        for value in ("0", "1", "99999999999999999999"):
            rows = events()
            for row in rows:
                for field in FIELDS:
                    if field in row:
                        row[field] = value
            with self.subTest(value=value):
                self.assertEqual(len(_bound_approvals(rows[1:3])), 1)
                self.assertEqual(self.binding(rows), "bound")
        rows = events()
        rows[2]["time_unix_nano"] = rows[1]["expires_at_unix_nano"]
        rows[-1]["time_unix_nano"] = rows[2]["time_unix_nano"]
        self.assertEqual(self.binding(rows), "bound")
        rows[2]["time_unix_nano"] = str(int(rows[1]["expires_at_unix_nano"]) + 1)
        self.assertEqual(_bound_approvals(rows[1:3]), [])
        self.assertEqual(self.binding(rows), "contradicted")
        rows = events()
        rows[2]["time_unix_nano"] = str(int(rows[1]["requested_at_unix_nano"]) - 1)
        self.assertEqual(_bound_approvals(rows[1:3]), [])
        self.assertEqual(self.binding(rows), "unresolved")

    def test_noncanonical_triples_never_bind(self):
        for value in INVALID:
            rows = events()
            for row in rows:
                for field in FIELDS:
                    if field in row:
                        row[field] = value
            with self.subTest(value=value):
                self.assertEqual(_bound_approvals(rows[1:3]), [])
                self.assertEqual(self.binding(rows), "contradicted")

    def test_each_request_and_resolution_timestamp_is_checked(self):
        for index in (1, 2):
            for field in FIELDS:
                rows = events()
                # All canonical times are 1, so bool/int equality cannot hide
                # behind an unrelated mismatched binding field.
                for row in rows:
                    for name in FIELDS:
                        if name in row:
                            row[name] = "1"
                rows[index][field] = True
                with self.subTest(index=index, field=field):
                    self.assertEqual(_bound_approvals(rows[1:3]), [])

    def test_each_action_or_approval_time_is_checked(self):
        for index in (2, 4):
            for value in INVALID:
                rows = events()
                rows[index]["time_unix_nano"] = value
                with self.subTest(index=index, value=value):
                    self.assertEqual(self.binding(rows), "contradicted")


@unittest.skipIf(sys.version_info < (3, 11), "TRACE requires Python 3.11+")
class TimestampFinalizationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from agentrust_trace import generate_key
        cls.key = generate_key()
        cls.config = TraceConfiguration(
            subject="spiffe://example.test/agent/workflow", model_provider="example",
            model_id="example-model", build_digest="sha256:" + "b" * 64,
            origin_kind="self", origin_producer="example-runtime",
            appraisal_verifier="https://example.test/verifier",
            classification_taxonomy="example.enterprise.v1",
            classification_order=("public", "internal", "confidential", "restricted"),
        )

    def test_valid_snapshot_signs_with_expected_iat_and_appraisal(self):
        rows = events()
        record = finalize_trace(snapshot(rows), self.config, signing_key=self.key)
        self.assertEqual(record["iat"], 1787079650)
        self.assertEqual(record["appraisal"]["status"], "affirming")

    def test_rehashed_invalid_timestamps_refuse_before_signing(self):
        baseline = events()
        for index, row in enumerate(baseline):
            for field in FIELDS:
                if field not in row:
                    continue
                for value in INVALID:
                    rows = copy.deepcopy(baseline)
                    rows[index][field] = value
                    with self.subTest(index=index, field=field, value=value), mock.patch(
                        "agentrust_trace.sign_record"
                    ) as sign:
                        with self.assertRaisesRegex(TraceFinalizationError, "timestamp"):
                            finalize_trace(snapshot(rows), self.config, signing_key=self.key)
                        sign.assert_not_called()


    def test_missing_required_approval_timestamps_refuse_before_signing(self):
        for index in (1, 2):
            for field in ("time_unix_nano", "requested_at_unix_nano"):
                rows = events()
                del rows[index][field]
                with self.subTest(index=index, field=field), mock.patch(
                    "agentrust_trace.sign_record"
                ) as sign:
                    with self.assertRaises(TraceFinalizationError):
                        finalize_trace(snapshot(rows), self.config, signing_key=self.key)
                    sign.assert_not_called()

    def test_malformed_candidate_refuses_even_with_a_valid_pair(self):
        rows = events()
        malformed = dict(rows[2], event_id="01996390-9db3-7d30-a96b-d88876ae3ac5",
                         expires_at_unix_nano=True)
        rows.insert(2, malformed)
        with mock.patch("agentrust_trace.sign_record") as sign:
            with self.assertRaisesRegex(TraceFinalizationError, "timestamp"):
                finalize_trace(snapshot(rows), self.config, signing_key=self.key)
            sign.assert_not_called()


if __name__ == "__main__":
    unittest.main()
