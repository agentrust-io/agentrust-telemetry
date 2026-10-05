# October 5 input-format validation

The CLI previously accepted unrelated native JSON and reported `processing: complete`
with zero spans and answers. Both `interpret` and `verify-receipts` now validate the
trace envelope before processing and return exit 1 with `processing: input_error` for
unsupported documents or malformed span collections. Errors name the failing location.

The gate accepts `{}`, empty arrays, and omitted/null repeated fields. A nonempty root
must contain `resourceSpans`; unknown fields alongside it remain ignored. This is an
offline format-selection policy, not a full OTLP receiver or schema validator. Nested
`resourceSpans`, `scopeSpans`, and `spans` arrays must contain objects. Span attributes,
IDs and unrelated OTLP fields are outside this structural check. Library callers can
use `parse_otlp`; low-level `flatten` assumes validated input.

[ProtoJSON's null rules](https://protobuf.dev/programming-guides/json/#null-values)
permit null repeated fields but exclude null array elements. Empty repeated fields may
be omitted. The gate preserves those behaviors. See also the
[OTLP JSON encoding rules](https://opentelemetry.io/docs/specs/otlp/#json-protobuf-encoding).

## Evidence

- [baseline-tests.txt](baseline-tests.txt): new CLI regression tests against unmodified
  reader `49727d4`. Unsupported JSON and malformed collections both failed as expected;
  empty-export and strict JSON controls passed.
- [cargo-test.txt](cargo-test.txt): all 24 tests pass after the fix, including the existing
  tenant and ordering checks. Four new tests exercise both CLI modes, wrong root types,
  native evidence shapes, wrong collection types, invalid entries after valid entries,
  empty/unset/null collections, duplicate keys and trailing JSON.
- [comparison.json](comparison.json): all 10 pinned kit cases still match (older 4/4,
  newer 6/6), including separate signature results.
- [cigar-probes.json](cigar-probes.json): all three complete Discord text captures now
  return input_error/exit 1 in both CLI modes. Hashes identify local UTF-8 text captures,
  not original downloaded attachment bytes. This establishes unsupported-format
  handling, not a defect in CIGAR or verification of its signatures.

From `interop/aaif-trace-model`, reproduce with:

```text
cargo +stable-x86_64-pc-windows-msvc test --locked
python check_pinned_kit.py --output results/2026-10-05-input-validation
```

Both commands exited 0. Cargo was launched through Python with `CREATE_NO_WINDOW`;
the CLI tests and kit harness also hide their Windows child processes. No other reader
or kit generator was run. The pre-fix failing tests establish the regression; the fix
does not add a native CIGAR adapter or complete Task 7's outstanding runtime coverage.
