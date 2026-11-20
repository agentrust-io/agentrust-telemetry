# Data-flow classification

When an agent moves data, for example reading a customer record and passing it to
a tool, this event records what kind of data it was and where it went, without
copying the data. This page is for developers who plug in their own classifier
(the code that decides how sensitive a piece of data is). It explains what the
helper guards against and what it cannot guarantee.

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


## Derived flows and source-label inheritance

For a summary, aggregation, extraction, or memory compaction step, pass the
trusted classifications of every contributing source together with an explicit
`ClassificationOrder` for their shared taxonomy. The ordered `levels` are listed
from least to most restrictive. The SDK records the classifier's output label as
`observed_classification`, computes `classification` as the strictest of that
output and every source label, and emits `source_classifications` containing only
source endpoint references and classification metadata.

```python
order = ClassificationOrder(
    "example.enterprise.v1",
    ("public", "internal", "confidential", "restricted"),
)

classified_data_flow(
    factory,
    output_classifier,
    summary,
    run_id="run-1",
    agent_id="agent-1",
    direction="output",
    source=DataEndpoint("transform", "summarizer"),
    destination=DataEndpoint("memory", "summary-1"),
    purpose="memory-compaction",
    source_classifications=[
        SourceClassification(
            DataEndpoint("document", "staff-notes"),
            ClassificationResult(
                "example.enterprise.v1", "confidential", "trusted-label-store"
            ),
        ),
    ],
    classification_order=order,
)
```

This API accepts **already-computed source labels**. It does not authenticate
those labels, verify that the source list is complete, or prevent callers from
passing untrusted/model-authored labels. Obtain source labels from a trusted
classifier or policy/label store, and supply the complete lineage. Unknown labels,
mixed taxonomies, duplicate source references, missing lineage, or a missing
order are rejected. At most 1,024 sources may be attached to one event. The SDK
does not infer declassification or implement reclassification/revocation
propagation. Existing direct-flow calls retain the previous data-flow
payload shape when the two new arguments are omitted.

This is a 0.2 contract change, not merely an optional-field change. Every event
from a 0.2 SDK carries `spec_version: 0.2.0-alpha.1`; therefore consumers pinned
to pre-0.2 closed schemas reject all events from the new SDK, including ordinary
direct-flow events that omit both lineage fields. Update the schema copy and
validator to 0.2 before consuming any event produced by a 0.2 SDK.

Source identity is the `(kind, id)` pair. Because `id` is optional, two distinct
same-kind endpoints without IDs are treated as duplicate references; provide
stable, pseudonymized IDs when multiple same-kind sources must be distinguished.
The Python API accepts a bounded iterable of source classifications, while the
TypeScript API requires a readonly array. When several sources share the highest rank, the first source in supplied
order wins the deterministic tie-break; iterable/array order is therefore part
of the contract.
