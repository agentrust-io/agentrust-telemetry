# Action execution events

`action.executed` records one resolved action attempt. It covers tools, MCP,
A2A, file, HTTP, database, and explicitly identified other actions.

The event requires an `action_digest`: a digest of the canonical authorization
subject used by the producer. An approval event can bind to the same digest, and
the action may additionally name its `approval_id` and governing
`policy_event_id`. The telemetry contract validates these fields but does not
prove that a producer computed or linked them honestly.

`outcome` distinguishes success, error, denial, cancellation, and timeout.
Denied attempts are still resolved attempts and therefore count in a TRACE tool
transcript. The event intentionally carries no arguments, results, source code,
credentials, or authorization material; optional digests identify those objects
without capturing them.

This revision does not represent started/in-flight actions. A producer emits the
event once the attempt has a terminal outcome and records its total duration.
