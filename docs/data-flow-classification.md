# Data-flow classification

`classified_data_flow` is a closed metadata boundary around an adopter-owned
classifier. Raw content is passed to `classifier.classify` and is never inserted
into the event. The classifier must return `ClassificationResult`; dictionaries
and arbitrary metadata objects are rejected.

Source and destination are `DataEndpoint` identifiers, not URLs, paths, queries,
or display text. Purpose, taxonomy, classification value, producer, endpoint
kind, and endpoint ID use a conservative identifier profile without whitespace,
query strings, fragments, or key/value delimiters. This blocks common accidental
content and credential placement, but cannot prove that every opaque identifier
is nonsensitive. Instrumentation authors must still pseudonymize identifiers.

Digests, sizes, token counts, media types, and transformations are caller facts.
The helper does not read content to derive them, and a digest is not proof that
classification is correct.

The AGT `DataAccessDecision` adapter maps only its allow/deny result, agent ID,
evaluation time, and ordered `DataClassification` tier under taxonomy
`agt.data_classification.v1`. It deliberately omits free-form reason, categories,
owner, geography, and matched-policy fields.
