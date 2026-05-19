---
id: knowledge-stack
title: Knowledge stack
type: design
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-02
last_verified_at: 2026-05-02
summary: "How each project's knowledge repo is served, written, and kept fresh."
implements_specs: [knowledge-and-admin]
related_designs: [system-overview, knowledge-repo-model, knowledge-write-api, knowledge-freshness]
affects_services: [coder-core, coder-admin]
parent: knowledge-and-admin
---

# Knowledge stack

The engineering shape of how each project's knowledge repo is
served, written, and kept fresh.

## What this category covers

Engineering counterpart of the
[knowledge-and-admin](../../../product-specs/active/knowledge-and-admin.md)
spec. Groups the designs that govern knowledge-repo IO from
coder-core to GitHub and back to workers.

## Components

- [knowledge-repo-model](./knowledge-repo-model.md) — the
  per-project repo's shape (specs, designs, ADRs, services, repos,
  integrations, runbooks, glossary) and the knowledge-types
  contract the validator enforces.
- [knowledge-write-api](./knowledge-write-api.md) — HTTP write
  surface (`create_artifact_in_repo`, `update_artifact_in_repo`,
  `approve`, `reject`); registry append shape; cross-link
  validation.
- [knowledge-freshness](./knowledge-freshness.md) — automatic
  freshness audit; `last_verified_at` semantics; nightly Architect
  audit dispatch; three-decision shape (`verified` /
  `needs_rewrite` / `uncertain`).

## Cross-cutting concerns

- **Worker prompt assembly**: per design 0057 every worker fetches
  three files from the project's knowledge repo (`_common.md`,
  `<role>/role.md`, `<role>/tasks/<mode>.md`) and the dispatcher
  injects a `Run context` block at the top with `{org}/{repo}` and
  the next-free artifact ID.
- **Worker writes**: the dispatcher's
  `_commit_artifact_with_registry` helper (added in the design 0057
  follow-on) is the single seam for PM specs and Architect designs/
  ADRs — collision-detected, registry-updated, audit-emitted.
- **Validation**: `scripts/validate.py` in this repo enforces
  frontmatter, registry consistency, and cross-link resolution; CI
  runs it on every change.

## Navigation

This design itself is a category entry point — drill into the
component designs above for deeper detail. See [design 0066](./navigation-tree-pattern.md)
for the tree pattern this organisation follows.

## Links

- Specs: [knowledge-and-admin](../../../product-specs/active/knowledge-and-admin.md),
  [knowledge-api](../../../product-specs/active/knowledge-api.md),
  [knowledge-freshness](../../../product-specs/active/knowledge-freshness.md),
  [admin-panel](../../../product-specs/active/admin-panel.md)
