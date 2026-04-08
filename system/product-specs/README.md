# product-specs/

Product features and roadmap items. The product side of the system —
the **what** and the **why for users**, separate from the technical
**how** that lives under [`../designs/`](../designs/).

A spec is owned by the **Product Manager** role. A design is owned by
the **Software Architect** role. They cross-link.

## Lifecycle

Mirrors `designs/`:

```
wip/  ──ship──▶  active/  ──remove──▶  deprecated/
```

| Folder | Meaning |
|---|---|
| [`active/`](./active/) | Live product features. |
| [`wip/`](./wip/) | Approved and in flight. |
| [`deprecated/`](./deprecated/) | Removed features, kept with `deprecated_at` and `reason`. |

## Numbering

Same as designs and ADRs: zero-padded 4-digit IDs, never reused.
