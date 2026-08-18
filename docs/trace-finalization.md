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

When `action.executed` events are present, `tool_transcript.hash` covers their
normalized bytes and evidence sequence in acceptance order, and `call_count`
equals the number of those action events. Other governance events are excluded.
When no action evidence is present, the optional transcript remains absent.

The signed record remains subject to TRACE's documented trust-anchor, freshness,
revocation, transparency, and software-only limitations.
