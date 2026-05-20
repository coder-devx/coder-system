---
id: '0033'
title: Polymorphic project_kind over a separate product entity
type: adr
status: proposed
date: '2026-05-10'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- studio-b2c-portfolio
---

# ADR 0033 — Polymorphic project_kind over a separate product entity

## Context

The Studio introduces B2C products that differ from existing internal-tool projects: different role workers, different pipeline gates, different lifecycle events (launch gate, kill workflow, Stripe metering). We needed to decide how to represent this difference in the data model.

## Options considered

1. **`project_kind` enum column on `projects`** — a single polymorphic `projects` table with a discriminator column. Worker eligibility, pipeline gate types, and integration availability are resolved by joining `project_kind` against a per-kind registry. The existing dispatcher, API routes, and admin panel project switcher all work unchanged.
2. **Separate `products` table and aggregate root** — `products` is a first-class entity with its own CRUD API, its own pipeline model, and its own admin panel section. `projects` and `products` coexist as siblings in the data model.
3. **Sub-typing via a nullable `b2c_project_config` extension table** — `projects` stays as-is; a one-to-one extension row holds Studio-specific fields. Effectively option 1 without the enum discriminator, deferring discrimination to nullable-join conditionals.

## Decision

Polymorphic `project_kind` (option 1).

## Rationale

A separate `products` aggregate would fork the dispatcher (two task queues, two lease tables, two escalation paths), the API (`/v1/products/` alongside `/v1/projects/`), the admin panel project switcher, and the knowledge repo model — for the sole benefit of type-system clarity at the aggregate boundary. Option 1 gives the same discriminability at the query layer at a fraction of the divergence cost. Option 3 defers the discrimination problem to nullable-join conditionals without naming it, which is harder to maintain than an explicit enum without being cheaper to implement than option 2. Worker eligibility via a per-kind registry table means adding a new `project_kind` in the future is a data migration, not a code change.

## Consequences

- Positive: dispatcher, ACL, audit log, secret rotation, escalation, and knowledge API work for Studio projects with zero changes.
- Positive: adding a third `project_kind` requires only a migration and registry entries, not API additions.
- Negative: Studio-specific fields (Stripe Connect account id, kill threshold config) live in `project_config JSONB` or a Studio-specific extension table, not strongly typed columns. Mitigation: typed accessors in `coder_core/studio/models.py` with JSON schema validation on write.
- Follow-up: add `project_kind` to every admin-panel query index that filters projects before Phase A ships.
