# Usage and cost attribution

`usage.recorded` reports measurements observed by an adapter. AgentTrust
Telemetry does not count tokens, resolve model prices, or infer a missing cost.

Use `usage_record()` for call-level facts and supply `CostObservation` only when
the provider, caller, or a named price resolver has produced a cost. An unknown
price is represented by the absence of `cost`, never by a synthetic zero.

`UsageAccumulator` accepts `model_call` leaves only, deduplicates them by
`event_id`, and can create `agent_run` or `workflow_run` rollups. Each rollup
contains the number of source events and per-field coverage counts. Consumers
can therefore distinguish a complete total from the sum of only the observations
that happened to include a field. Mixed-currency cost rollups are rejected.

Rollups are new telemetry facts. A metrics pipeline should select either leaf
events or rollup events for a given aggregation query; adding both double counts.
