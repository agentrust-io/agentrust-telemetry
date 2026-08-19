# Evidence chain profile

Status: experimental `rfc8785-jcs-v1` for contract `0.1.0-dev`.

Each accepted event is validated and privacy-checked before entering the chain.
Sequence numbers start at zero and represent acceptance order, not event time.

For entry `n`, calculate:

```text
event_bytes = RFC 8785 JSON Canonicalization Scheme (JCS) bytes for event
previous = 32 zero bytes for entry 0, otherwise raw bytes of entry n-1 digest
material = previous || uint64_big_endian(n) || event_bytes
digest = lowercase_hex(SHA-256(material))
```

The profile name is explicit and versioned. RFC 8785 requires I-JSON input,
ECMAScript number serialization, UTF-16 property sorting, and rejection of
non-finite numbers and invalid Unicode. Integer identifiers that can exceed
IEEE-754's exact range, including nanosecond timestamps, remain decimal strings
on the wire.

Callback-mode writers must commit idempotently by `event_id` and return `True`
only after durable acknowledgement. A false return or exception leaves local
sequence and chain state unchanged. The callback receives an isolated copy.

Sealing prevents further appends. `completeness` is explicitly supplied by the
caller and must remain `unknown` unless the caller has an independent basis for
asserting `complete` or `incomplete`.
