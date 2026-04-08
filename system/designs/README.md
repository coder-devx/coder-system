# designs/

Design docs for the Coder system. Each design is a logical unit (a feature, a
subsystem, an interaction model) with diagrams and the rationale that links
back to ADRs and product specs.

## Lifecycle

```
wip/  ──ship──▶  active/  ──remove──▶  deprecated/
```

| Folder | Meaning |
|---|---|
| [`active/`](./active/) | Describes how the system **currently** works. The big picture. |
| [`wip/`](./wip/)       | In flight. Implementation in progress. Will land in `active/` (as a new file or by editing an existing one) when done. |
| [`deprecated/`](./deprecated/) | Removed from the system, kept with a `deprecated_at` date and `reason` so the history is recoverable. |

## Promotion rules

- A WIP design that ships is **either** moved into `active/` as-is **or** its
  content is merged into existing active design files. Both are valid; pick
  whichever keeps `active/` coherent.
- An active design that is removed is moved to `deprecated/`. Set
  `status: deprecated`, `deprecated_at:`, and a `reason:` field. Do not delete.

See [`../../AGENTS.md`](../../AGENTS.md) rule 5 for the canonical rule.

## Numbering

Zero-padded 4-digit IDs. Look at the highest existing ID across **all three**
subfolders and `registry.yaml` before assigning a new one. IDs are never
reused.
