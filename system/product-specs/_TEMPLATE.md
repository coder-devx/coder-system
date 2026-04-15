# Product spec templates

Two templates — use the one matching the folder you're writing into.
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
served_by_designs: []    # wip design ids (numeric) or active design slugs
related_specs: []        # other spec ids/slugs
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
served_by_designs: []     # design slugs describing this component
related_specs: []         # adjacent component slugs
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
