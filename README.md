# aaif-trace-reader-rs

The second independent reader for [AAIF Observability & Traceability Task 7 (#45)](https://github.com/aaif/wg-observability-and-traceability/issues/45).
Rust, offline, batch. The design it implements was posted on #45 on
[16 September](https://github.com/aaif/wg-observability-and-traceability/issues/45#issuecomment-5691732097).

## Inputs, and what was not read

- Contract: [#51 v0.7-draft at `e82abf1`](https://github.com/aaif/wg-observability-and-traceability/blob/e82abf1e58b066c586c25767edfba862c4ebd027/working-documents/AGENT-BEHAVIOR-TRACE-MODEL-CONTRACT.md), copied to `inputs/contract/`.
- Kit: [#57 at `8fa732e`](https://github.com/aaif/wg-observability-and-traceability/pull/57/commits/8fa732e3ec597e04a8b667c3669d3ac537e3e98a):
  README, TEMPLATE, the trust key, and each case's `records.otlp.json` and `basis.json`, copied to `inputs/kit/`.
- Not read before the first results commit: any `expected.json`, `run.py`, `generate.py`, and the
  Python reader at `Rul1an/aaif-trace-reader`. His comments on #45 and #57 were read, since they are
  public discussion.

Written with an AI coding assistant (Claude Opus 5.5), directed and reviewed by Imran Siddique.
Dependencies: `serde`, `serde_json`, `sha2`, `base64`, `ed25519-dalek`.

## Build and run

```sh
cargo test                     # set semantics: every permutation of every case, plus degraded cases
cargo run --release --bin trace-reader -- interpret --input inputs/kit/cases/<case>/records.otlp.json
cargo run --release --bin trace-reader -- verify-receipts --input <records> --key inputs/kit/trust/test-ticket-service.pub.pem
```

`interpret` has no argument for expected answers. `basis.json` is not read by the reader either:
which document a case follows is the comparator's business, not an input to interpretation.

On Windows on ARM without the ARM64 MSVC libraries, build with `cargo +stable-x86_64-pc-windows-msvc`.

## Interpretation choices

1. **No method, no relationship.** Contract §4 (revision 3) requires a link method on each
   relationship record, or a default in the example's mapping file. No record in the kit carries a
   method and the kit ships no mapping file, so under v0.7-draft none of R1, R5 or R6 is established.
   The reader reports `relationship_method_absent` as a mapping loss and answers `unknown`.
2. **Declared defaults are recorded as declared.** `--method-default` stands in for the example's
   mapping file. It requires `--defaults-declared-by`, and the report carries who declared it.
   An unrecognized method is a loss, with no fallback (§4 boundary case 1).
3. **Scope before join.** Receipts deduplicate on (`receipt.service`, `receipt.id`); effects are
   (`receipt.service`, `receipt.ticket_id`). Deliveries that disagree are a conflict, not a merge.
4. **Producer claims are not evidence.** `evidence.externally_verified` is listed under `not_used`.
5. **Signatures are separate.** v0.7-draft treats a receipt as correlation evidence, so the contract
   reader never looks at `receipt.signature`. `verify-receipts` implements the README's signing input.
6. **Missing is unknown.** No model-call and no decision records are mapped in this kit, so calls
   and approvals answer `unknown` with a named gap.

## Results

`results/8fa732e/` holds three runs per case: `strict` (no defaults), `declared-defaults`
(R1 and R5 `attribute-reference`, R6 `external-correlation-key`), and `receipt-signatures`.

## Limits

This reader interprets telemetry. It does not show that an export is complete or authentic, and
four cases exercise the effects question only. Continuity, calls and approvals await cases and the
#43/#44 exports.

## Comparison against the kit's expected answers

Run after `cf1fad8` froze the reader and its results. `trace-compare` is a separate program; it
reads `expected/` (copied from the kit at `8fa732e`) and scores each field on its own.

| Case | v0.7 scope | strict | declared defaults |
| --- | --- | --- | --- |
| effects-receipt-delivered-twice | yes | effect, tickets, externally_verified miss | all four match |
| effects-receipt-missing | yes | all four match | all four match |
| evidence-grade-pair-verifies | no (#32 §3.3) | effect, tickets, externally_verified miss | all four match |
| evidence-grade-pair-fails | no (#32 §3.3) | all four match | effect and tickets miss; externally_verified matches |

A strict match on a negative case is not evidence: a reader that answers unknown everywhere gets
the same result there. `externally_verified` comes from `verify-receipts` in every row, because
v0.7-draft has no rule for it, including in the two cases whose basis is the #42 example.
