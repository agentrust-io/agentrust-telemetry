# TRACE finalization

Status: experimental. Python requires 3.11+ and `agentrust-telemetry[trace]`.
TypeScript requires a caller-supplied official TRACE codec because no official
AgentTrust TRACE Node package is currently published.

`finalize_trace` maps a sealed, explicitly complete evidence snapshot into the
official TRACE v0.2 model, signs it with a caller-supplied key, validates it, and
self-verifies the signature. The adapter never loads or generates a key.

The caller must provide trusted subject identity, model identity, build
provenance, evidence origin, appraisal verifier, and an ordered classification
taxonomy. The adapter derives the policy binding, enforcement mode, maximum data
class, appraisal, issuance time, and software evidence-chain measurement.

Finalization fails when evidence is open, incomplete, empty, inconsistently bound
to policy, missing classified data flows, or contains an unranked classification.
It also recomputes the evidence chain and fails when the snapshot's entries no
longer hash to its chain digest (an entry edited, dropped, or reordered after
sealing), since the measurement would then not cover the events appraised. The
recheck proves consistency, not provenance: the chain carries no key.
It emits `runtime.platform: software-only`; it cannot manufacture attestation.

When `action.executed` events are present, `tool_transcript.hash` covers their
normalized bytes and evidence sequence in acceptance order, and `call_count`
equals the number of those action events. Other governance events are excluded.
When no action evidence is present, the optional transcript remains absent.

The signed record remains subject to TRACE's documented trust-anchor, freshness,
revocation, transparency, and software-only limitations.

The TypeScript codec boundary must provide the v0.2 profile identifier, signing,
structural validation, public-key derivation, and signature verification. The
finalizer invokes all four steps and fails closed. It does not substitute a local
shape check for official TRACE validation. Tool transcript bytes use RFC 8785 JCS
in both SDKs.

## Appraisal

The adapter derives `appraisal.status` from the sealed evidence, worst first:

- `contraindicated` when any policy decision is `deny` or `error`; when the run
  carries `approval.rejected`, `approval.expired`, or
  `approval.execution_failed`; or when an approval-gated action contradicts its
  approval: the approval for it carries a different `action_digest` or
  `policy_event_id`, or was resolved after the action completed. The evidence
  then shows that something other than the approved action ran, so the
  appraisal failed.
- `warning` when a `challenge` decision has no bound approval, when the run
  carries `approval.cancelled`, or when an approval-gated action has no bound
  approval at all.
- `affirming` when policy or approval evidence is present and none of the
  above applies.
- `none` when there is no policy or approval evidence.

An approval resolves a challenge only when an `approval.approved` event matches
an `approval.requested` event on `approval_id`, `policy_event_id`,
`action_digest`, `chain_id`, `chain_version`, `requested_at_unix_nano` and
`expires_at_unix_nano`, and its `time_unix_nano` falls inside the request's
window. The approval-gated action rules are in
[Action execution events](action-events.md#approval-binding).
