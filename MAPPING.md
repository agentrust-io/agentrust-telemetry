# Source mapping: aaif-trace-reader-rs

This is the reader's own mapping, authored from the #57 kit README and the record files. It is
not the example's mapping file, and it declares no link methods. Contract §4 gives that role to
the example.

| Native label in the kit | Contract term | Identity | Relationship expressed |
| --- | --- | --- | --- |
| span carrying `turn.id` | Turn | `turn.id` | R1 via `conversation.id` on the same span |
| span named `propose_action` | Proposed action | `action.id` | none exported (R3 absent; span ancestry is not used) |
| span named `execute_tool *` | Tool execution | none exported | R5 via `action.id` |
| span named `ticket.create.receipt`, or any `receipt.*` attribute | External effect receipt | `receipt.id`, scoped by `receipt.service` | R6 via `receipt.action_id` to the execution's `action.id` |

Scope. A receipt's issuing scope is `receipt.service`, and it must equal the receipt's resource
`service.name`; a mismatch leaves the receipt's scope unresolved. An effect's identity is
(`receipt.service`, `receipt.ticket_id`). `receipt.action_id` does not say which scope issued the
action id, so the join to an execution is made only when the input holds exactly one agent scope.

Not used. `evidence.externally_verified` is the producer's claim about its own evidence. The reader
reports it under `not_used` and draws nothing from it.

Not mapped in this input: model calls (R2) and approval decisions (R4). Their questions answer
`unknown` with a named gap, never zero.
