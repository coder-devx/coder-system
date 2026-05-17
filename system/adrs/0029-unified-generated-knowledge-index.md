---
id: "0029"
title: One generated knowledge index for the whole system
type: adr
status: accepted
date: 2026-05-07
deciders: [ro]
supersedes:
superseded_by:
relates_to_designs: [navigation-tree-pattern]
---

# ADR 0029 — One generated knowledge index for the whole system

## Context

Design [navigation-tree-pattern](../designs/active/knowledge/navigation-tree-pattern.md)
introduced a curated `INDEX.md` per artifact-type folder
(`product-specs/INDEX.md` and `designs/INDEX.md`) and a `parent:`
field on every spec and design. Workers (PM, Architect, Reviewer)
read the relevant per-folder INDEX as the first grounding fetch
before drafting, designing, or reviewing.

The pattern is sound — a curated tree beats a flat registry at scale
— but the current shape has friction:

- **Two indexes that mostly mirror each other.** The five top-level
  categories (`pipeline-operations`, `worker-roles`,
  `tenancy-and-access`, `knowledge-and-admin`, `delivery-and-infra`)
  appear on both surfaces. Each INDEX.md hand-restates the same
  taxonomy with slightly different one-liners.
- **Hand-curated → drift.** The per-category one-liners live in two
  files, separately from the artifacts they describe. They go stale
  whenever an artifact's scope changes and the INDEX isn't updated
  in lockstep. INDEX.md was already pointing at non-existent
  `wip/0066-…md` paths within days of the underlying file moving to
  `active/`.
- **Per-role index variants.** Six worker task contracts inject
  `product-specs/INDEX.md` *or* `designs/INDEX.md` depending on
  role. PM reads only the product index, Architect reads both,
  Reviewer reads only the engineering index. Cross-cutting decisions
  (a Reviewer noticing a missing spec while gating a design) require
  a second fetch.
- **The taxonomy already exists in frontmatter.** Every active spec
  and design carries `parent:` per design 0062. The tree is data;
  the indexes are a stale rendering of that data.

## Options considered

1. **Status quo — two hand-curated INDEX.md files.** Lowest churn.
   Keeps the drift, keeps the per-role variants, keeps the
   double-bookkeeping for category descriptions.
2. **Two generated INDEX.md files (one per folder).** Resolves drift
   but keeps the two-files / two-fetches / hand-mirrored-taxonomy
   shape that mostly served the old folder-isolation model.
3. **One generated `system/INDEX.md` covering the whole system
   (this ADR).** Source of truth: the `parent:` chains already
   present plus a new `summary:` field on each artifact. A
   `scripts/render_index.py` walks both registries and emits the
   tree. Workers fetch one file. Categories are rendered with their
   own artifact's `summary:`, not a hand-curated description in the
   index file.

## Decision

Adopt option 3. **One generated `system/INDEX.md`** is the single
navigation entry point for product specs and designs together. The
two per-folder `INDEX.md` files are deleted in the same change that
introduces the generator and the new `summary:` field.

Schema additions:

- `summary:` (optional, string, ≤ ~140 chars) on `spec` and `design`
  artifact types. The renderer pulls it into the INDEX. Where the
  field is absent, the renderer falls back to `title`.

Renderer contract (`scripts/render_index.py`):

- Walks `system/product-specs/registry.yaml` and
  `system/designs/registry.yaml`.
- Builds a tree from `parent:` references, with both spec and design
  children listed under each category in a single flat list, tagged
  `(spec)` / `(design)`.
- Emits `system/INDEX.md`. The file has the same lifecycle as
  `REGISTRY.md`: generated, drift-checked by `scripts/validate.py`,
  hand-edits lost on the next render.

Worker contract change (knowledge side):

- The 6 task contracts that today inject `product-specs/INDEX.md` or
  `designs/INDEX.md` instead inject `system/INDEX.md`. Same name for
  every role.
- `_common.md` references the unified INDEX as the canonical
  knowledge entry point.
- `AGENTS.md` discovery order surfaces `system/INDEX.md` as step 4.

Lifecycle scope:

- The INDEX renders **active** artifacts only. WIPs are listed in
  `registry.yaml` and tracked in `ROADMAP.md`; including them in the
  navigation tree would conflate roadmap detail with current-state
  grounding.
- Deprecated artifacts are excluded.

## Rationale

- **Single source of truth.** One artifact, one place to look for
  category shape and per-leaf summary. Drift collapses.
- **One fetch.** Workers preload `system/INDEX.md` regardless of
  role. Cross-cutting work (Reviewer needing both views) costs zero
  extra round trips.
- **Builds on existing schema.** `parent:` is already populated on
  47 designs + 32 specs. The new `summary:` field is a one-line
  backfill, not a schema redesign.
- **Generated views match the rest of the repo.** REGISTRY.md is
  already generated from registry.yaml. INDEX.md joining that
  pattern keeps the contributor mental model uniform.
- **Cross-folder taxonomy reflects the system.** A category like
  "pipeline operations" is one logical area with both a product
  view (the spec) and an engineering view (the design). A unified
  index makes that explicit; two parallel indexes make it
  accidental.

## Consequences

- **Positive:**
  - One file to read for grounding, one file to keep current,
    one schema for the navigation tree.
  - Per-category descriptions stop drifting from the artifact
    they describe.
  - `validate.py` drift detection covers INDEX the same way it
    covers REGISTRY.md.
  - Adding a category requires no INDEX edit — just creating the
    category artifact with `parent:` null and `summary:` set.
- **Negative:**
  - One-time backfill: add `summary:` to ~40 active spec/design
    artifacts. Most one-liners can be lifted verbatim from the
    existing INDEX.md files (this lands in the same change).
  - Six worker task contracts updated to reference
    `system/INDEX.md`. Mechanical edits.
  - `coder-core` workers that today fetch
    `product-specs/INDEX.md` and `designs/INDEX.md` via the GitHub
    API need to switch to `system/INDEX.md`. Tracked separately in
    coder-core; the knowledge-side change can land first because
    the old paths stop existing simultaneously and the worker
    prompts already treat the index path as a fetch parameter.
- **Follow-ups:**
  - Edit design `navigation-tree-pattern` in place to record the
    evolution from per-folder hand-curated to unified generated.
    Active designs are edited in place per AGENTS.md rule 5.
  - The renderer initially produces the flat tagged-list format
    decided here (option 1 in the design proposal). A future
    grouped-by-kind variant is a renderer-only change if a need
    emerges.
