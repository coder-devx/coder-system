# Product spec templates

Three templates — use the one matching the file you're writing.

- **`wip/`** specs are roadmap-aligned, numbered, temporal.
- **`active/`** subject-named files describing one logical component
  use the spec template.
- **`active/`** subject-named *category rollup* files (the top-level
  groupings — `delivery-and-infra`, `pipeline-operations`, etc.) use
  the index template. See [ADR 0025](../adrs/0025-type-index-for-category-rollup-artifacts.md).

See [`README.md`](./README.md) for the two-lifecycle model.

---

## Template for `wip/` (numbered, roadmap-aligned)

Copy this when drafting a planned spec. Filename: `00NN-kebab-title.md`.

```markdown
---
id: "00NN"
title: Short Title
type: spec
status: wip
owner: ro
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_verified_at: YYYY-MM-DD
summary: ~               # ≤140-char one-liner used by system/INDEX.md once landed in active/
served_by_designs: []    # wip design ids (numeric) or active design slugs
related_specs: []        # other spec ids/slugs
parent: ~                # category id (e.g. pipeline-operations); ~ until landed in active/
---

# {Title}

## Problem
Whose problem, in their words.

## Users / personas
Who hits this.

## Goals
What changes for users when this ships.

## Non-goals
What this is not.

## Scope
Concretely, what's in.

## Acceptance criteria

Each AC is a single bullet of the shape `- **AC<N>.** <description>` —
the bold prefix is the stable identifier the reviewer attestation
echoes back when the spec ships. The ship validator parses both this
form and the older `- [ ]` checkbox shape; new specs **must** use
`- **ACn.**` so attestations have a stable handle.

- **AC1.** Observable, testable condition for "done".
- **AC2.** Another condition. Aim for 4–7 ACs total.

## Metrics
How we'll know it worked.

## Open questions
- …

## Links
- Designs: …
- Related specs: …
```

---

## Template for `active/` (category rollup — `type: index`)

Copy this when a file's job is grouping components, not describing
one. Filename: `category-slug.md`. Required sections:
`What this category covers`, `Components`, `Cross-cutting concerns`,
`Links`. See [ADR 0025](../adrs/0025-type-index-for-category-rollup-artifacts.md).

```markdown
---
id: category-slug             # matches filename, stable identifier
title: Category Name
type: index
status: active
owner: ro
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_verified_at: YYYY-MM-DD
summary: One-line description of what this category groups (≤140 chars). Rendered into system/INDEX.md.
served_by_designs: []         # design slugs, if any, framing this group
related_specs: []             # peer category-rollup ids, if any
parent: ~                     # category rollups sit at the root; ~ is correct
---

# {Category Name}

One-sentence framing: what this category groups and why.

## What this category covers

One short paragraph naming the boundary — what falls inside, what
does not.

## Components

- [component-slug](./component-slug.md) — one-line role.
- …

## Cross-cutting concerns

Bullet the system-wide invariants this category leans on or enforces
(audit, isolation, observability, …) with cross-links.

## Links

- Designs: …
- Repos: … (when relevant)
- Related categories: …
```

---

## Template for `active/` (subject-named component)

Copy this when creating a new active component file, or landing WIP
content into a genuinely new component. Filename: `component-slug.md`.

```markdown
---
id: component-slug        # matches filename, stable identifier
title: Component Name
type: spec
status: active
owner: ro
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_verified_at: YYYY-MM-DD
summary: One-line description of what this component does (≤140 chars). Rendered into system/INDEX.md.
served_by_designs: []     # design slugs describing this component
related_specs: []         # adjacent component slugs
parent: <category-id>     # required for active specs; pick from system/INDEX.md
---

# {Component Name}

## What it is
One paragraph — what this component does in the running system.

## Capabilities
- Observable, current behaviors (not a checklist of ACs).

## Interfaces
APIs, events, CLIs, UI surfaces this component exposes.

## Invariants  <!-- optional -->
Hard rules the running component maintains — properties that must hold
on every read/write/transition. Use when the component has explicit
contracts that aren't obvious from Capabilities (e.g. "every audit row
is rolled back with its mutation transaction"). Skip when there are no
non-obvious invariants.

## Configuration  <!-- optional -->
Live operator knobs — env vars, per-project columns, feature flags,
weights — that change runtime behaviour without code edits. Use when
the surface has more than 1-2 knobs worth naming. Skip otherwise;
single knobs belong inline in Capabilities or Interfaces.

## Dependencies
Other components, services, or external systems it relies on.

## Evolution
1-3 lines of notable shipping milestones (date — what changed,
spec ids). Keep terse — git and design docs have the detail. If
this section grows past ~10 lines it's a code changelog, not the
current-state description an active spec is supposed to be.

## Links
- Designs: …
- Related components: …
```
