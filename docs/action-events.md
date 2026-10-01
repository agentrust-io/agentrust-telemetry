# Action execution events

`action.executed` records one resolved action attempt. It covers tools, MCP,
A2A, file, HTTP, database, and explicitly identified other actions.

The event requires an `action_digest`: a digest of the canonical authorization
subject used by the producer. An approval event can bind to the same digest, and
the action may additionally name its `approval_id` and governing
`policy_event_id`. The telemetry contract validates these fields but does not
prove that a producer computed or linked them honestly.

## Approval binding

An `action.executed` event is approval-gated when it names an `approval_id`,
or names a `policy_event_id` whose `policy.decision` is `challenge`. A gated
action with an outcome other than `denied` must run under an `approval.approved`
event that:

- carries the same `approval_id` (or, when the action names none, the same
  `policy_event_id`);
- carries an `action_digest` with the same `algorithm` and `value` as the
  action's `action_digest`;
- names the same `policy_event_id` as the action, when the action names one;
- is bound to its `approval.requested` event and resolved inside that request's
  window, as described in [TRACE finalization](trace-finalization.md); and
- has a `time_unix_nano` no later than the action's `time_unix_nano`.

A `denied` attempt did not run, so it is exempt. These rules are checked across
the run's evidence; a single event cannot show a violation, so the per-event
schemas do not change. The run-level cases in `conformance/appraisal/` cover a
matching action and each way a gated action can fail to match.

Binding relies on the producer naming `approval_id` or `policy_event_id` on the
action. An action that names neither is not gated by this check.

`outcome` distinguishes success, error, denial, cancellation, and timeout.
Denied attempts are still resolved attempts and therefore count in a TRACE tool
transcript. The event intentionally carries no arguments, results, source code,
credentials, or authorization material; optional digests identify those objects
without capturing them.

This revision does not represent started/in-flight actions. A producer emits the
event once the attempt has a terminal outcome and records its total duration.
