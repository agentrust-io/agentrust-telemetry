# Privacy

## Default profile

`metadata_only` is the mandatory default. The SDK rejects known content-bearing fields and rejects extension attributes unless the application explicitly allowlists each key.

The default prohibits prompts, completions, source code, tool arguments/results, credentials, secrets, and authorization tokens. Content digests are identifiers and may still be sensitive; operators must treat them according to their threat model.

## Responsibilities

Instrumentation authors must supply pseudonymous identities, accurate classification labels, and minimal metadata. Operators remain responsible for collector transport security, access control, retention, deletion, residency, and compliance obligations.

The SDK records classification supplied by another component. It does not establish that the classification is correct.

## Opt-in extensions

Extension attributes require an explicit allowlist in `SchemaValidator`. Allowlisting a key is a deployment decision, not proof that every value under that key is safe. Broad wildcards are intentionally unsupported.
