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

Adapters report source facts; they do not evaluate policy or prove source
authenticity. Callers remain responsible for trusted bundle digests and correct
action/resource classification.
