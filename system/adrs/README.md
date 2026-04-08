# adrs/

Architectural Decision Records.

An ADR captures **one decision** with the context that led to it, the
options considered, the choice made, and the consequences. ADRs are
**append-only** — once merged, the decision and rationale do not change.
To revise a decision, write a new ADR and mark the old one
`status: superseded` with `superseded_by:`.

## Numbering

Zero-padded 4-digit IDs. Look at the highest number in `registry.yaml`
before assigning. IDs are never reused.

## Status values

- `proposed` — drafted, not yet accepted
- `accepted` — current, in force
- `superseded` — replaced by a later ADR (`superseded_by:` set)
- `rejected` — drafted but not adopted
- `deprecated` — no longer relevant but not replaced

See [`../../AGENTS.md`](../../AGENTS.md) rule 4.
