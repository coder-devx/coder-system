---
id: "0066"
title: Navigation tree pattern for specs, designs, and ADRs
type: design
status: wip
owner: ro
created: 2026-05-02
updated: 2026-05-02
last_verified_at: 2026-05-02
implements_specs: []
decided_by: []
related_designs:
  - knowledge-repo-model
  - knowledge-write-api
  - pm-worker
  - architect-worker
affects_services:
  - coder-core
affects_repos:
  - coder-core
  - coder-system
parent: knowledge-repo-model
---

# 0062 — Navigation tree pattern

## Context

The product-specs and designs folders today are flat lists of artifacts
plus a registry that lists every entry side-by-side. Workers (PM,
Architect, Team Manager, Reviewer) and humans landing on the repo have
no curated entry point. To understand the system they either:

1. Read the registry and guess relevance from titles, or
2. Read every active spec, or
3. Walk the cross-link graph (`related_specs`, `served_by_designs`)
   spec-by-spec, hoping the author maintained the edges they need.

At 21 active product specs + 17 active designs, (1) works. Current PM
runs typically read 3-5 grounding files to draft a spec — the right
ones, picked from titles. At 100+ specs the title-only signal will
not be enough; the worker will either over-fetch (cost regression) or
miss relevant context (quality regression).

The seeds of a tree are already here:

- `designs/active/system-overview.md` is *de facto* an engineering
  root entry point.
- `designs/active/worker-roles.md` is *de facto* a category-level
  doc that points at architect-worker, pm-worker, etc.

But the role of "entry point" is implicit, the convention isn't
documented, and the product-specs side has no equivalent at all.

## Decision

**Adopt a hierarchical navigation pattern: root → category → leaf,
with leaves promoting to entry points when their content gets large
enough.** Same shape for product-specs, designs, and (optionally)
ADRs.

### The three levels

```
{type}/INDEX.md               root entry point
  └─ {type}/active/<category>.md     category entry point (a regular spec/design with children)
       └─ {type}/active/<leaf>.md    leaf (regular spec/design)
```

- **Root** (`INDEX.md`): one per artifact-type folder. Names every
  category, links to category entry-points, surfaces a one-paragraph
  description per category. ~200-400 lines for 5-7 categories.
- **Category** (`<category>.md`): a regular spec/design that happens
  to have many children. Same frontmatter shape as any other; its
  body opens with a `## Components` section listing children. Picked
  by the curator at category-creation time.
- **Leaf**: every other spec/design. Names its parent in frontmatter.

A leaf with internal sub-parts can graduate to an entry point by
acquiring children of its own — the schema is recursive.

### Schema additions

One new optional frontmatter field on specs and designs:

```yaml
parent: <category-id>     # the spec/design id of this artifact's parent.
                          # Omitted on root-level entries (categories that
                          # report directly to INDEX.md) and on the INDEX
                          # itself.
```

`parent` references an id that must exist in the same folder's
registry (per `_validate_cross_links` semantics). The validator will
warn — not fail — on missing `parent` until adoption is complete; a
future change can flip enforcement on.

The reverse relationship (`children:`) is *derived* at view time from
`parent:` rather than hand-maintained, to avoid the
double-bookkeeping that bites `related_specs` today.

### INDEX.md convention

`INDEX.md` is added to the SKIP_FILENAMES exclusion in
`scripts/validate.py` (no frontmatter required, not a knowledge
artifact in its own right — it's a curated narrative view).

Its body shape:

```markdown
# Product specs — index

One-paragraph description of the product surface area.

## <Category 1 — short name>

One-paragraph description of what this category covers and why
it groups together.

- [<spec-id>](./active/<spec-id>.md) — one-line summary
- [<spec-id>](./active/<spec-id>.md) — one-line summary

## <Category 2>
...
```

### Worker prompt impact

PM and Architect task contracts updated to read `INDEX.md` first.
The curated tree gives them the right grounding picks in a single
fetch instead of (registry → guess by title → fetch many).
`Next free spec ID` (added in design 0057's run-context block) keeps
working as before.

## Categories — initial cuts

### product-specs (21 active specs)

| Category file (new) | Children |
|---|---|
| `pipeline-operations.md` | escalations, self-healing, branch-cleanup, task-orchestration, observability |
| `worker-roles.md` (new spec; design with same slug exists) | architect-worker, pm-worker, developer-worker, reviewer-worker, team-manager-worker |
| `tenancy-and-access.md` | multi-tenancy, impersonation, service-accounts, audit-log |
| `knowledge-and-admin.md` | knowledge-api, knowledge-freshness, admin-panel, onboarding |
| `delivery-and-infra.md` | continuous-deployment, tenant-isolation, coder-core-modular-monolith |

### designs (17 active designs)

| Category file | Children |
|---|---|
| `system-overview.md` (existing root) | (links to all category designs) |
| `worker-roles.md` (existing) | architect-worker, pm-worker, team-manager-worker |
| `pipeline-operations.md` (new) | escalations, self-healing, branch-cleanup, observability-and-cost-tracking, worker-communication |
| `tenancy-and-access.md` (new) | impersonation, audit-log, tenant-isolation |
| `knowledge-stack.md` (new) | knowledge-repo-model, knowledge-freshness, knowledge-write-api |
| `coder-core-architecture.md` (new) | coder-core-modular-monolith, system-overview cross-cutting |

## Out of scope

- **ADRs** stay flat. They're append-only chronological decision records;
  thematic grouping is a future view-only concern. INDEX.md not added.
- **Bidirectional `children:` field**. Derived from `parent:` at view
  time only. Prevents the maintenance drift we already see with
  `related_specs`.
- **Multi-parent (DAG) navigation**. A leaf has *one* parent. Cross-links
  via `related_specs` cover the secondary-relationship case.
- **Deep trees**. Two levels is enough for the current scale. The
  schema doesn't forbid deeper trees, but we won't author them yet.
- **`type: category` artifact type**. Category nodes are regular
  specs/designs with children — no new type, no schema split.

## Migration

Phased and additive — no existing tasks break:

1. **Schema**: add optional `parent:` to `_TEMPLATE.md`, validator
   warns (doesn't fail) if missing.
2. **Categories**: author 5 new product-spec category files + 4 new
   design category files. Each is a real spec/design with frontmatter.
3. **Backfill**: every existing active spec/design gets `parent:`
   pointing at its category. WIP entries keep `parent: ~` (null)
   for now — they're roadmap-aligned, not yet in the active tree.
4. **INDEX.md**: write `product-specs/INDEX.md` and
   `designs/INDEX.md` (the latter as a slim companion to
   `system-overview.md`, or absorb into it).
5. **Worker prompts**: PM and Architect contracts read INDEX.md first.
6. **Future**: flip validator from warn to fail on missing `parent`
   for active artifacts after every project's repo is migrated.

Other Coder-managed projects' knowledge repos run unchanged until
they author their own INDEX.md and category nodes — same hard-cutover
posture as design 0057.

## Risks

1. **Authoring overhead**: ~9 new category files + parent fields on
   ~38 active artifacts. One-time cost, but real.
2. **Category drift**: clusters that look right today may not in 6
   months. Mitigated by: categories are regular specs/designs,
   re-parenting a leaf is a 1-line frontmatter change + registry
   update.
3. **Worker prompt cost regression**: prepending INDEX.md content
   could add a few KB to every assembled prompt. With prompt
   caching that cost is paid once, then cache-hot.

## Implementation order

This change lands in a single PR pair (coder-system + coder-core)
because the worker-prompt updates assume the new files exist:

1. Write this design + register in `designs/registry.yaml`.
2. Write 5 product-spec categories + `product-specs/INDEX.md`.
3. Write 4 design categories + `designs/INDEX.md`.
4. Backfill `parent:` on all active specs/designs (frontmatter + registry).
5. Update `_TEMPLATE.md` for specs and designs.
6. Update `scripts/validate.py`: skip INDEX.md, validate `parent:`
   references when present.
7. Update PM draft + accept and Architect design + ship contracts in
   `roles/<role>/tasks/<mode>.md` to read INDEX.md as the first
   grounding fetch.
8. Validator green; ship.

No coder-core code changes — workers fetch from the knowledge repo
via existing GitHub-API plumbing.

## Links

- Specs: none (no paired spec — internal architecture change)
- Related designs: `knowledge-repo-model`, `knowledge-write-api`,
  `pm-worker`, `architect-worker`
- Predecessor: design 0057 (per-role/per-mode prompt layout) — the
  worker-prompt half of this lives in the layout 0057 established.
