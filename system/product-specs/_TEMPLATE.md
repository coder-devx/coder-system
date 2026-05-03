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
- [ ] Observable, testable conditions for "done".

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
served_by_designs: []     # design slugs describing this component
related_specs: []         # adjacent component slugs
parent: <category-id>     # required for active specs; pick from product-specs/INDEX.md
---

# {Component Name}

## What it is
One paragraph — what this component does in the running system.

## Capabilities
- Observable, current behaviors (not a checklist of ACs).

## Interfaces
APIs, events, CLIs, UI surfaces this component exposes.

## Dependencies
Other components, services, or external systems it relies on.

## Evolution
Short log of notable WIPs that shaped this component (commit/PR
references). Keep terse — git has the detail.

## Links
- Designs: …
- Related components: …
```
