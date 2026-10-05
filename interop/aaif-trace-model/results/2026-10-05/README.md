# October 5 tenant-scope fix

The reader now preserves resource `tenant.id`, joins receipts only within the execution's
tenant, and accepts an explicit action/service/tenant query. Query context comes from the
kit's `basis.json` through CLI flags; expected answers never enter the reader.

## Before and after

The unchanged reader from parent `25f4bf1` (reader implementation `590d618`) was run first
against the pinned tenant-reuse input with the declared R6 default. It exited 0 but returned
two indistinguishable execution subjects, each with `receipt_deliveries_disagree` and no
correlated effect. See [baseline-tenant.json](baseline-tenant.json).

The fixed reader answers `tenant-a` with `T-1042` and `tenant-b` with `T-2088`, keeping the
same action `P1` and receipt `R-9` separate. The CLI selects `tenant-a` without reading an
expected answer. An omitted query tenant means the absent-tenant scope, not all tenants.

| Pinned kit | Cases matching every expected field |
| --- | --- |
| `4a028675ef9b5727e614762df305f5f037b04b98` | 4 of 4 |
| `b6587950986eb4ec501e080cc9730fd21dcb69fa` | 6 of 6 |

Both signature cases retain their prior behavior: the valid signature verifies and the invalid
signature fails, while both receipts still correlate. Signature bytes and verification code
were not changed. [comparison.json](comparison.json) records each field, query, command and
exit code. Each case directory holds the reader output and upstream expected answers.
[sha256.json](sha256.json) pins inputs, expectations and the relevant source files.

## Reproduce

From `interop/aaif-trace-model`:

```text
cargo +stable-x86_64-pc-windows-msvc test --locked
python check_pinned_kit.py
```

Both commands exited 0. On other platforms, use the installed Rust toolchain. The comparison
script uses only committed files and the built binary; it needs no network. On Windows its
reader children use `CREATE_NO_WINDOW`, as does the CLI integration test. This run launched
Cargo through a Python wrapper with that flag too.

The comparison queries the reader before loading expected answers. The four-case kit lacks
evaluation context, so the harness explicitly uses the action and service in its documented
single-service mapping. The newer six-case kit supplies each query in `basis.json`. Every
case must produce exactly one selected execution answer; the harness cannot silently select
the first of several. The historical `trace-compare` binary is not used here.

## Regression evidence

[cargo-test.txt](cargo-test.txt): 20 tests passed (8 existing, 12 added). New tests cover:

- both tenant queries and distinguishable subjects without query filtering;
- all 24 resource orders and all 6 x 6 agent-span orders, totaling 864 combinations;
- absent tenant versus named tenant, missing receipts, and another tenant's receipt;
- duplicate, empty, non-string and ambiguous resource scope attributes;
- receipt resource/service mismatch and a different queried service;
- same receipt/ticket IDs across tenants, duplicate deliveries, and conflicts within a tenant;
- multiple agent services for the same tenant/action remaining unresolved;
- proposal lookup and orphan receipts retaining tenant scope;
- missing R6 method remaining unknown and unknown action yielding no selected answer;
- the actual CLI selecting tenant-a and returning only its ticket.

For a causal check, removing just `r.resource_tenant == e.resource_tenant` from the receipt
candidate filter made `reused_action_and_receipt_ids_stay_in_their_tenant` fail with `conflict`
instead of `established`. [mutation-test.txt](mutation-test.txt) records the command, exit 101,
and assertion. Source bytes were restored before the final passing suite and kit comparison.

## Limits

This fixes a reader implementation gap under the kit's declared mapping. It does not change
the contract or claim adoption of `tenant.id` as an OTel field. The signature does not cover
tenant metadata; correlation is not authenticated tenant identity.

This follow-up was developed with the fixture, its declared outcome, and the earlier expected
results already known. It is not a blind validation. No kit generator or other reader was read
or run. The local comparison harness and new tests were written alongside the fix; the pinned
upstream expectations provide the external oracle for the ten comparisons.

The tests exercise effects and specific scope handling. Full Task 7 remains unestablished:
continuity, calls/retries, approvals and runtime exports still need their own cases. The reader
is a fixture-specific interpreter, not a general OTLP validator or a proof of export completeness.
