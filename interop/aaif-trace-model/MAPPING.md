# Source mapping: aaif-trace-reader-rs

This is the reader's own mapping, authored from the #57 kit README and the record files. It is
not the example's mapping file, and it declares no link methods. Contract §4 gives that role to
the example.

| Native label in the kit | Contract term | Identity | Relationship expressed |
| --- | --- | --- | --- |
| span carrying `turn.id` | Turn | `turn.id` | R1 via `conversation.id` on the same span |
| span named `propose_action` | Proposed action | `action.id` | none exported (R3 absent; span ancestry is not used) |
| span named `execute_tool *` | Tool execution | none exported | R5 via `action.id` |
| span named `ticket.create.receipt`, or any `receipt.*` attribute | External effect receipt | `receipt.id`, scoped by `receipt.service` and resource `tenant.id` | R6 via `receipt.action_id` to the execution's `action.id` within the same tenant |

Scope. A receipt's issuing scope is `receipt.service`, and it must equal the receipt's resource
`service.name`; a mismatch leaves the receipt's scope unresolved. An effect's identity is
(`receipt.service`, resource `tenant.id`, `receipt.ticket_id`). Receipts deduplicate on
(`receipt.service`, resource `tenant.id`, `receipt.id`). The implementation first partitions
candidate receipts by the execution's exact tenant, then groups by service and ID.
`receipt.action_id` does not say which agent service issued the action ID, so the join is made
only when all executions for that tenant/action have one known agent service. Query filtering
does not remove competing executions from this ambiguity check. R5 proposal lookup also uses
the execution's service and tenant. Subjects retain both, including turns and proposals.

The illustrative resource `tenant.id` mapping follows kit `b658795`'s mapping.md. Absent tenant
matches only absent tenant; it is not a wildcard. A present empty, non-string, ambiguous AnyValue,
or duplicate resource scope attribute is diagnosed and cannot establish R5/R6 joins. Missing
agent service also prevents an R6 join. This is a fixture mapping, not an OTel convention or an
authenticated tenant assertion: the receipt signing input does not cover `tenant.id`.

Optional `--query-action`, `--query-service`, and `--query-tenant` select execution answers for
an action and exact tenant, and constrain R6 receipts to the named service. Action and service
are required together. An omitted query tenant selects the absent-tenant scope. No match
produces no execution answer, not a successful result; multiple matching executions stay
visible. The comparator rejects zero or multiple selected answers. Non-execution answers remain
in the report. Queries come from `basis.json` evaluation context via the caller; the reader
never reads expected answers or `basis.json` itself.

Not used. `evidence.externally_verified` is the producer's claim about its own evidence. The reader
reports it under `not_used` and draws nothing from it.

Not mapped in this input: model calls (R2) and approval decisions (R4). Their questions answer
`unknown` with a named gap, never zero.
