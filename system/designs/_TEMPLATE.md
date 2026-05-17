# Design templates

Three templates — use the one matching the file you're writing.

- **`wip/`** designs are roadmap-aligned, numbered, temporal.
- **`active/`** subject-named files describing one logical component
  use the design template.
- **`active/`** subject-named *category rollup* files (the engineering
  counterparts of the product-spec category rollups —
  `pipeline-operations`, `tenancy-and-access`) use the index template.
  See [ADR 0025](../adrs/0025-type-index-for-category-rollup-artifacts.md).

See [`README.md`](./README.md) for the two-lifecycle model.

## Discipline (the bar, not a line cap)

Active designs target **one component each, current state only**.
Length follows content: every section earns its place; rollout /
history / decisions live in `## Evolution` (terse) or in ADRs. Smell
test at ~200 body lines (look hard for fused topics or padding); past
~300 is almost certainly two designs in one. A genuinely complex
component can sit in the 100–200 range and still be tight. See the
[architect role doc](../roles/software-architect/role.md)
§"What a good design looks like" for the full discipline.

Every leaf active design ends with a `## Where in code` section
citing 3–6 **symbols** (not line numbers) — `scripts/validate.py`
rejects `path.ext:N` patterns in that section.

---

## Template for `wip/` (numbered, roadmap-aligned)

Copy this when drafting a planned design. Filename: `00NN-kebab-title.md`.

```markdown
---
id: "00NN"
title: Short Title
type: design
status: wip
owner: ro
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_verified_at: YYYY-MM-DD
summary: ~               # ≤140-char one-liner used by system/INDEX.md once landed in active/
implements_specs: []     # spec ids (numeric for wip) or slugs (for active)
decided_by: []           # adr ids
related_designs: []      # other design ids/slugs
affects_services: []     # service ids touched
affects_repos: []        # repo ids touched
parent: ~                # category id (e.g. pipeline-operations); ~ until landed in active/
---

# {Title}

## Context
What problem are we solving? What's the world today?

## Goals / non-goals
- Goals
- Non-goals

## Design

```mermaid
flowchart TB
  A --> B
```

### Components
- Bullet each new or changed component.

### Data flow
Walk the happy path.

### Edge cases
- …

## Open questions
- …

## Rollout
How does this ship? Phases, flags, migration.

## Links
- Specs: …
- ADRs: …
- Services: …
```

---

## Template for `active/` (category rollup — `type: index`)

Copy this when a design file's job is grouping engineering components,
not describing one. Filename: `category-slug.md`. Required body
sections: `What this category covers`, `Components`,
`Cross-cutting concerns`, `Links`.

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
implements_specs: []          # the matching product-spec category id, if any
related_designs: []           # peer designs in or adjacent to this group
affects_services: []
affects_repos: []
parent: <category-id-or-~>    # parent design rollup or ~ for top-level
---

# {Category Name}

One-sentence framing: what this category groups and why.

## What this category covers

Short paragraph naming the boundary — what falls inside, what does not.

## Components

- [component-slug](./component-slug.md) — one-line role.

## Cross-cutting concerns

System-wide invariants this category leans on or enforces, with cross-links.

## Links

- Specs: …
- Repos: …
- Related categories: …
```

---

## Template for `active/` (subject-named component)

Copy this when creating a new active component file. Filename:
`component-slug.md`.

```markdown
---
id: component-slug        # matches filename, stable identifier
title: Component Name
type: design
status: active
owner: ro
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_verified_at: YYYY-MM-DD
summary: One-line description of what this component does (≤140 chars). Rendered into system/INDEX.md.
implements_specs: []      # active spec slugs this component realizes
decided_by: []            # adr ids
related_designs: []       # adjacent component slugs
affects_services: []      # service ids
affects_repos: []         # repo ids
parent: <category-id>     # required for active designs; pick from system/INDEX.md
---

# {Component Name}

## What it is
One paragraph — the role this component plays in the running system.

## Architecture

```mermaid
flowchart TB
  A --> B
```

### Parts
- Concrete pieces (modules, tables, endpoints, jobs) and their job.

### Data flow
How a request/event moves through this component today.

### Invariants
What must always hold. Edge cases the design handles.

## Interfaces
APIs, events, schemas, CLI surfaces this component exposes to others.

## Where in code
3–6 symbol anchors pointing into the source repos. **Cite by symbol,
not by line number** — lines shift on every refactor in `coder-core`;
designs live in `coder-system`, and no commit touches both atomically,
so a `path.ext:N` anchor silently rots on every unrelated PR. Symbol
names only change on rename — a much rarer event that's a natural
trigger to revisit the doc. Format: ``- `<path>` — `<symbol>` (note)``.
`scripts/validate.py` (per design 0095) rejects line-numbered anchors
in this section.

## Evolution
Short log of notable WIPs that shaped this component (commit/PR
references). Keep terse — git has the detail.

## Links
- Specs: …
- ADRs: …
- Services: …
```
