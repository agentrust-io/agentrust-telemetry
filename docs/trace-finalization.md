# TRACE finalization

Status: experimental; requires Python 3.11+ and `agentrust-telemetry[trace]`.

`finalize_trace` maps a sealed, explicitly complete evidence snapshot into the
official TRACE v0.2 model, signs it with a caller-supplied key, validates it, and
self-verifies the signature. The adapter never loads or generates a key.

The caller must provide trusted subject identity, model identity, build
provenance, evidence origin, appraisal verifier, and an ordered classification
taxonomy. The adapter derives the policy binding, enforcement mode, maximum data
class, appraisal, issuance time, and software evidence-chain measurement.

Finalization fails when evidence is open, incomplete, empty, inconsistently bound
to policy, missing classified data flows, or contains an unranked classification.
It emits `runtime.platform: software-only`; it cannot manufacture attestation.

No `tool_transcript` is emitted yet because the telemetry contract has no
dedicated tool-call event. Governance-event count is not tool-call count.

The signed record remains subject to TRACE's documented trust-anchor, freshness,
revocation, transparency, and software-only limitations.
