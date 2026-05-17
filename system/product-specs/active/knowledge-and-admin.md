---
id: knowledge-and-admin
title: Knowledge & admin
type: index
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: "How a project's knowledge is read, written, kept current, and surfaced to operators."
served_by_designs: [knowledge-repo-model, knowledge-write-api, knowledge-freshness]
related_specs: [worker-roles, tenancy-and-access, pipeline-operations]
parent: ~
---

# Knowledge & admin

How a project's knowledge is read, written, kept current, and
surfaced to the human operator.

## What this category covers

Every Coder project has its own *knowledge repo* — a Git repository
with the same shape as `coder-system` itself: services, repos,
designs, ADRs, product-specs, roles, integrations, runbooks. This
category groups the specs that define how that repo is served to
workers, how workers write back to it, how it's kept fresh, how the
human operator interacts with the running system, and how the fleet
of knowledge repos is kept in sync with expected workflow primitives.

## Components

- [knowledge-api](./knowledge/knowledge-api.md) — read-through layer over the
  knowledge repo with a per-project cache. Files, registries, graph
  queries.
- [knowledge-freshness](./knowledge/knowledge-freshness.md) — automatic
  freshness audit that flags stale artifacts and schedules
  Architect-led rewrites.
- [admin-panel](./knowledge/admin-panel.md) — user-facing SPA: pipeline view,
  knowledge browser, plan review, metrics dashboard, drive-mode
  override.
- [onboarding](./knowledge/onboarding.md) — how a new project gets wired into
  Coder for the first time.
- [managed-workflows](./knowledge/managed-workflows.md) — shared primitive for
  installing, verifying, and receiving callbacks from GitHub Action
  workflows across the fleet of managed knowledge repos.

## Cross-cutting concerns

- **Worker reads**: every worker reads the knowledge repo for its
  grounding context — see the `gh api` pattern in the role task
  contracts (e.g. `roles/product-manager/tasks/draft.md`).
- **Worker writes**: PM specs and Architect designs land via the
  Knowledge API write path or the dispatcher's
  `_commit_artifact_with_registry` helper (see design 0057).
- **Audit**: every knowledge write emits a `knowledge.create` /
  `knowledge.update` event in [audit-log](./tenancy/audit-log.md).
- **Pipeline integration**: PM acceptance promotes specs from `wip/`
  to `active/`; design 0057 establishes the per-role/per-mode prompt
  layout that drives this.

## Links

- Designs: [knowledge-repo-model](../../designs/active/knowledge/knowledge-repo-model.md),
  [knowledge-write-api](../../designs/active/knowledge/knowledge-write-api.md),
  [knowledge-freshness](../../designs/active/knowledge/knowledge-freshness.md)
