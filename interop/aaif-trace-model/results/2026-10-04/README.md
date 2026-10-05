# October 4 independent reader rerun

Reader: `590d6182f6b8ae0938a0546439ed854b92745d64`, unchanged Rust implementation.
Contract: v0.7-draft at `e82abf1e58b066c586c25767edfba862c4ebd027`.
Kit revisions: `4a028675ef9b5727e614762df305f5f037b04b98` and
`b6587950986eb4ec501e080cc9730fd21dcb69fa`.

The input files, hashes and reader output were committed locally at `6fb9c5d`
before fetching either revision's expected files for this rerun. Expected outcomes
were already described in the kit README. Earlier published results were known.
This was expected-file-blind, not answer-blind. Neither kit reader nor generator
was read or run. No reader implementation change was made.

## Results

| Kit revision | Cases matching every expected field | Signature checks |
| --- | --- | --- |
| 4a02867 | 4 of 4 | valid pair verifies; invalid pair fails |
| b658795 | 5 of 6 | valid pair verifies; invalid pair fails |

At both revisions, action, effect and confirmed ticket IDs match in the duplicate
receipt, missing receipt and both signature cases. Correlation confirms the effect
even in the invalid-signature case. The signature result is a separate check run
only where `basis.json` requests it. The new changed-ticket case returns `T-2088`.

The tenant-reuse case fails. `flatten()` retains the resource service but drops
`tenant.id`. `effects_for()` then groups both tenants' `R-9` receipts by service
and receipt ID, reports `receipt_deliveries_disagree`, and emits two indistinguishable
execution subjects. It cannot select the `tenant-a` query in `basis.json`.
It does not return the other tenant's ticket as confirmed. This is an implementation
gap in the Rust reader, not a contradiction in the declared kit mapping.

The comparison query comes from `basis.json` before opening expected answers.
For the older revision, which has no evaluation context, the single action `P1`
and test service come from its README and declared single-service mapping.
The old Rust `trace-compare` was not used: it selects an action from `expected.json`
and still compares the superseded `externally_verified` field.

`comparison.json` scores each requested field separately. Original and current
input hashes are in each revision's `inputs.sha256.json`. Full Task 7 remains
unestablished: continuity, calls/retries, approvals and runtime exports were not
tested by this effects-only kit.

## Execution

Windows x86_64 MSVC toolchain, dependencies locked:

```text
cargo +stable-x86_64-pc-windows-msvc test --locked
cargo +stable-x86_64-pc-windows-msvc build --locked --bins
```

Both commands exited 0. The eight existing tests passed, including exhaustive
permutations of the original four cases. The new scope case was not added to
that permutation suite and no new scope regression test is claimed.

For each pinned record file:

```text
trace-reader interpret --input RECORDS --method-default R1=attribute-reference --method-default R5=attribute-reference --method-default R6=external-correlation-key --defaults-declared-by "kit mapping.md @ SHA"
trace-reader verify-receipts --input RECORDS --key test-ticket-service.pub.pem
```

The signature command runs only for the two evidence-grade cases. All interpreter
and signature commands exited 0. Native children were launched with
`subprocess.CREATE_NO_WINDOW`.
