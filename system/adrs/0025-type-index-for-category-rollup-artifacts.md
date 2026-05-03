---
id: "0025"
title: "`type: index` for category-rollup artifacts"
type: adr
status: accepted
date: 2026-05-03
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: []
---

# ADR 0025 — `type: index` for category-rollup artifacts

## Context

The `system/product-specs/active/` folder contains five files whose
job is grouping, not describing a single component:

- `delivery-and-infra.md`
- `knowledge-and-admin.md`
- `pipeline-operations.md`
- `tenancy-and-access.md`
- `worker-roles.md`

They each declare `type: spec`, but their bodies are navigation
pages — `What this category covers` + `Components` + `Cross-cutting
concerns` + `Links`. They lack the `Capabilities` / `Interfaces` /
`Dependencies` sections that the active-spec template requires for
every other file in the folder.

The shape is real and load-bearing: the registry's `parent` field
already references these IDs, the admin panel's information
architecture mirrors them, and the discovery order in
[`AGENTS.md`](../../AGENTS.md) leans on them. But the frontmatter
type lies about what they are. The validator can't enforce category-
specific structure, and a human reading the folder gets two
different shapes labelled identically.

The same pattern exists, less acutely, in `system/designs/active/`
(`pipeline-operations.md`, `tenancy-and-access.md`).

## Options considered

1. **Flesh them out as full specs.** Add Capabilities / Interfaces /
   Dependencies sections at the category level. Pros: zero schema
   change. Cons: a category's "capabilities" are the union of its
   components' — content duplicates content that already lives
   correctly in the leaf files, and drifts as leaves change. Most of
   the value of these files comes from the navigation shape, not from
   restating leaf behaviour at a higher level.

2. **Introduce `type: index` as a first-class artifact type.**
   Update the spec template, validator, and migrate the five files.
   Pros: the frontmatter matches reality, the validator can enforce
   category-specific structure, and the discovery rule "if it's a
   subject-named active file with `type: spec`, it has the spec
   shape" is restored. Cons: small one-time migration; the `_TEMPLATE`
   file gains a third template block.

3. **Move them out of `product-specs/active/`.** Put them in
   `system/categories/` or as folder-level `_<category>.md` files.
   Pros: clearer separation. Cons: bigger refactor — the discovery
   order in `AGENTS.md` would need a new entry, the `parent` field
   semantics would change, and design rollups (`pipeline-operations`,
   `tenancy-and-access`) would also need to move. The disruption
   isn't justified by the gain over option 2.

## Decision

**Option 2.** Introduce `type: index` as a recognised artifact type
in `system/product-specs/` and `system/designs/`. Update
`_TEMPLATE.md` with a third template block defining the index shape.
Update `scripts/validate.py` to accept `type: index` and enforce its
required sections. Migrate the five product-spec rollup files and the
two design rollup files to `type: index`. Keep filenames, IDs, and
registry entries unchanged — this is a frontmatter change, not a
rename.

## Rationale

- The five files already have a consistent, useful shape. We're not
  inventing a new artifact, we're naming one that already exists.
- `type: spec` lying about what these files are leaks into every
  audit ("why don't these have Capabilities?"). Naming it correctly
  closes that question permanently.
- Migration cost is bounded: one validator change, one template
  change, frontmatter on seven files. No content rewrites, no
  registry-shape changes, no cross-link sweep.
- A future "should this be an index or a spec?" call becomes obvious
  by inspection — the index template asks for `Components`, the spec
  template doesn't.

## Consequences

- **Positive:**
  - Validator can enforce index-specific required sections
    (`Components`, `Cross-cutting concerns`).
  - The active-spec template becomes a tighter contract — every
    `type: spec` file genuinely describes a component.
  - The pattern generalises: design rollups can adopt the same type.
- **Negative:**
  - `_TEMPLATE.md` grows a third block; registry types now include
    `index` as a value (the registry shape itself doesn't change).
  - Tooling that filters on `type: spec` (e.g. ad-hoc scripts) may
    need to treat `type: index` as a sibling.
- **Follow-ups:**
  - Apply the same rename to the two design rollups
    (`designs/active/pipeline-operations.md`,
    `designs/active/tenancy-and-access.md`).
  - Consider migrating the equivalent `system/services/REGISTRY.md`
    or other "this folder collects N things" files if they land on
    the same shape.
