# Event factories and policy adapters

`EventFactory` owns normalized envelope construction: specification version,
producer identity, event UUID, timestamp, correlation fields, schema validation,
and privacy validation. Its generic `build` method supports every event family,
so adopters can instrument approvals, usage, data flows, and actions without a
source-specific dependency.

The OPA adapter accepts one decision-log event. Boolean results map to allow or
deny and an absent result maps to not-applicable; structured results require an
explicit mapper because OPA intentionally permits any JSON value. OPA input and
result documents are never copied. The source decision ID deterministically
derives the normalized UUID, and the query-evaluation timer is used when present.
A trusted bundle digest remains required because a bundle revision is not a
content digest.

The Cedar adapter accepts the final Allow/Deny response plus determining policy
IDs and caller-normalized diagnostic codes. Cedar evaluation errors are recorded
without rewriting the final decision, matching Cedar's skip-on-error semantics.
Free-form error messages are rejected to prevent accidental content leakage.

The optional AGT bridge implements the batch sink shape used by Agent OS without
making AGT a core dependency. The generic constructor accepts a runtime's result
sentinels and is the durable integration boundary. `from_agent_os` is a legacy
compatibility convenience that binds the installed runtime's actual export-result
enum; upstream currently deprecates `agent-os-kernel` in favor of
`agent-governance-toolkit-core`. A caller-supplied mapper keeps run identity and
source classification explicit. The included policy mapper accepts only AGT
policy events and requires a trusted policy-engine version, bundle digest, and
resource type. It does not copy free-form reason, resource, or attribute values.

The bridge normalizes the whole batch before emitting its first event. This
prevents a malformed later source event from causing mapping-time partial
delivery. Destination failures can still occur after earlier events were
accepted, so durable evidence callbacks must remain idempotent by event ID.

Adapters report source facts; they do not evaluate policy or prove source
authenticity. Callers remain responsible for trusted bundle digests and correct
action/resource classification.
