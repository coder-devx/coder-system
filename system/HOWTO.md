# How-to

> One-page entry point for common tasks in this knowledge repo. If you
> can't find your question here, check [AGENTS.md](../AGENTS.md) for
> the contract or [INDEX.md](./INDEX.md) for the navigation tree.

This file lists "how do I X?" questions and points at the right place
to do X. It is not the answer itself — the linked file is.

## Authoring

**How do I propose a new product spec?**
PM role only. Drop a numbered file under
[`product-specs/wip/`](./product-specs/wip/), copy from
[`product-specs/_TEMPLATE.md`](./product-specs/_TEMPLATE.md) (the
WIP template), fill the frontmatter (use `Next free spec ID` from
the dispatcher's run-context block — never invent one, ADR
[0028](./adrs/0028-reaffirm-shared-id-pool-with-allocation-guard.md)),
and register the entry in
[`product-specs/registry.yaml`](./product-specs/registry.yaml).

**How do I propose a new design?**
Architect role. Same shape as a spec: numbered file under
[`designs/wip/`](./designs/wip/), copy from
[`designs/_TEMPLATE.md`](./designs/_TEMPLATE.md), use the spec's id
on the design (shared numeric pool, ADR
[0026](./adrs/0026-shared-numeric-id-pool-for-wip-specs-and-designs.md)),
register in [`designs/registry.yaml`](./designs/registry.yaml).

**How do I add a `summary:` to a new artifact?**
≤140-char one-liner that the index renderer pulls into
[`INDEX.md`](./INDEX.md). Set it on the WIP frontmatter so it's
ready when the WIP folds into `active/`. Omit it and the renderer
falls back to `title`.

**How do I write an ADR?**
Append-only (AGENTS.md rule 4). Copy from
[`adrs/_TEMPLATE.md`](./adrs/_TEMPLATE.md), pick the next free
4-digit ID, register in
[`adrs/registry.yaml`](./adrs/registry.yaml), add a row to the
"Current decisions" table in
[`adrs/REGISTRY.md`](./adrs/REGISTRY.md).

**How do I add a new role?**
Folder shape only (ADR
[0027](./adrs/0027-uniform-role-folder-shape.md)): create
`roles/<role-id>/role.md` from
[`roles/_TEMPLATE.md`](./roles/_TEMPLATE.md), register in
[`roles/registry.yaml`](./roles/registry.yaml). Worker roles also
populate `tasks:` and create per-mode contracts under
`roles/<role-id>/tasks/<mode>.md`.

**How do I add a new mode to an existing worker role?**
Drop a new `roles/<role>/tasks/<mode>.md`, list the mode under
`tasks:` in `roles/registry.yaml`, and wire mode detection into
`coder_core.workers.dispatcher._parse_mode_for_role` in coder-core.

**How do I deprecate an active component?**
Move the file to `<folder>/deprecated/`, set `status: deprecated`,
add `deprecated_at:` and `reason:`, update the registry. Don't
delete — `deprecated/` is the audit trail.

## Shipping a WIP

**How do I ship a WIP product spec?**
PM `ship` mode. Read the smart-fold rules in
[`roles/product-manager/tasks/ship.md`](./roles/product-manager/tasks/ship.md)
— extend an existing active spec when the WIP refines a known
component, create a new active component file only when the WIP
introduces a genuinely new logical unit. Delete the numbered WIP
file in the same change.

**How do I ship a WIP design?**
Architect `ship` mode — same smart-fold contract as PM ship, applied
to designs. See
[`roles/software-architect/tasks/ship.md`](./roles/software-architect/tasks/ship.md).

**Soaking before fold?**
If a behaviour-changing flag is live in production, the WIP stays in
`wip/` for the soak window (≥30 days for behaviour flags, longer for
auth / audit / billing). The roadmap entry annotates `shipped,
soaking through <date>`. See AGENTS.md rule 5.

## Navigating

**How do I find the right category for a new spec or design?**
Read [INDEX.md](./INDEX.md). It's the unified category tree across
specs and designs (ADR 0029); pick the category your component
belongs to and set `parent: <category-id>` on the new artifact.

**How do I see how artifacts relate to each other?**
[GRAPH.md](./GRAPH.md) renders per-category Mermaid graphs of
`served_by_designs` / `implements_specs` / `related_*` edges and an
ADR fan-out table.

**How do I find what's currently in flight?**
[ROADMAP.md](./product-specs/ROADMAP.md) → "In flight" section.
Per-WIP detail lives in
[product-specs/PHASES.md](./product-specs/PHASES.md).

**How do I find which service or repo owns a piece of code?**
[`services/REGISTRY.md`](./services/REGISTRY.md) and
[`repos/REGISTRY.md`](./repos/REGISTRY.md).

**How do I find the relevant ADRs for a topic?**
[`adrs/REGISTRY.md`](./adrs/REGISTRY.md) "Current decisions" table.
For ADRs cited by specific artifacts, see the "ADR fan-out" table in
[GRAPH.md](./GRAPH.md).

**How do I find the runbook for an operational task?**
[`runbooks/`](./runbooks/) — one file per procedure (incident
response, secret rotation, onboarding, …).

## Validating + regenerating

**How do I check the repo is valid before pushing?**
```
python3 scripts/validate.py
```
Checks frontmatter, cross-links, registry orphans, naming rules,
shared-id parent matches, and drift on the four generated views
(REGISTRY ×2, INDEX, GRAPH).

**How do I regenerate the human views?**
```
python3 scripts/render_registry.py    # designs + product-specs REGISTRY.md
python3 scripts/render_index.py       # system/INDEX.md
python3 scripts/render_graph.py       # system/GRAPH.md
```
All three are idempotent and drift-checked by `validate.py`.

**How do I see what knowledge has gone stale?**
```
python3 scripts/freshness.py --top 20            # 20 stalest
python3 scripts/freshness.py --over 90           # over 90 days
python3 scripts/freshness.py --type spec --top 10
```
When you re-verify a file, bump its `last_verified_at` to today.

## When something looks wrong

**A frontmatter cross-link doesn't resolve.**
Run `python3 scripts/validate.py`; the error names the file and the
unknown id. Fix the id or add the missing artifact + registry entry.

**REGISTRY.md / INDEX.md / GRAPH.md is out of sync with reality.**
Run the matching renderer (see "How do I regenerate the human
views?"). Hand edits are lost on the next render.

**A WIP id collides with an existing one.**
Numeric IDs are never reused (AGENTS.md rule 6). The dispatcher
allocates the next free id from the shared spec+design pool —
agents must refuse rather than guess (ADR 0028). If you're authoring
manually, look at the highest existing ID across `wip/` and
`deprecated/` in both folders.

**An active spec and design with the same id have different `parent:`.**
Validator catches this (ADR 0029). Pick the canonical parent (the
spec side usually wins) and align the design.

**An ADR's decision needs to be reversed.**
Don't edit the merged ADR. Write a new ADR with `supersedes:` set,
and flip the old ADR's `status` to `superseded` with `superseded_by:`
pointing at the new id. Move the old row from "Current decisions" to
"Superseded" in [`adrs/REGISTRY.md`](./adrs/REGISTRY.md).

## Knowing where something belongs

**A typed artifact** (spec, design, ADR, role, service, repo,
integration, runbook): goes in its named folder.

**A category-rollup file** (groups child specs/designs under a
common name): same folder as its children, `type: index` per ADR
[0025](./adrs/0025-type-index-for-category-rollup-artifacts.md).

**A time-bound analysis or audit report**: drop it under
[`reports/`](./reports/). No frontmatter, no registry, no validator
— archive only.

**An operational manifest** (read by `coder-core` at runtime):
[`repos.yaml`](./repos.yaml), [`managed-workflows.yaml`](./managed-workflows.yaml).
These live at `system/` root; not artifacts.

**A blueprint shape** (every project copies this): goes in
[`../template/`](../template/), not in `system/`. Update template
only when the *shape* of the knowledge model changes (new artifact
type, new frontmatter field) — write an ADR.
