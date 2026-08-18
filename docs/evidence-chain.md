# Evidence chain profile

Status: experimental `agentrust-json-v1` for contract `0.1.0-dev`.

Each accepted event is validated and privacy-checked before entering the chain.
Sequence numbers start at zero and represent acceptance order, not event time.

For entry `n`, calculate:

```text
event_bytes = UTF-8(JSON(event, keys sorted, no insignificant whitespace,
                        non-ASCII preserved, NaN and infinity rejected))
previous = 32 zero bytes for entry 0, otherwise raw bytes of entry n-1 digest
material = previous || uint64_big_endian(n) || event_bytes
digest = lowercase_hex(SHA-256(material))
```

The profile name is explicit because this pre-alpha JSON serialization is not a
claim of RFC 8785 conformance. A future contract may adopt a standard canonical
form through a versioned profile; existing chains retain their original profile.

Callback-mode writers must commit idempotently by `event_id` and return `True`
only after durable acknowledgement. A false return or exception leaves local
sequence and chain state unchanged. The callback receives an isolated copy.

Sealing prevents further appends. `completeness` is explicitly supplied by the
caller and must remain `unknown` unless the caller has an independent basis for
asserting `complete` or `incomplete`.
