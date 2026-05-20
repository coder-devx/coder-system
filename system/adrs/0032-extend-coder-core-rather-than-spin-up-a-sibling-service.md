---
id: '0032'
title: Extend coder-core rather than spin up a sibling service
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

# ADR 0032 — Extend coder-core rather than spin up a sibling service

## Context

The Studio needs orchestration for B2C product projects: new role workers, new integrations, new domain models (`product_lifecycle`, `studio`). We had to decide whether to extend the existing `coder-core` FastAPI service or provision a separate `coder-studio` service.

## Options considered

1. **Extend coder-core** — add Studio domains as Python modules (`coder_core/studio/`, `coder_core/product_lifecycle/`). New workers land in `coder_core/workers/`. All Studio projects share the existing dispatcher, audit log, escalation, deploy pipeline, and multi-tenancy primitives.
2. **Separate `coder-studio` service** — a second FastAPI service with its own Postgres schema, deploy pipeline, and worker fleet. Communicates with `coder-core` over HTTP for shared primitives (auth, audit, secret rotation, escalations).
3. **Studio as a coder-core plugin** — a dynamically loaded module with its own database migrations, registered at startup. Operationally indistinguishable from option 1 for a Python monolith.

## Decision

Extend coder-core (option 1).

## Rationale

A B2C product is a project with a different `project_kind`. coder-core is already a multi-tenant orchestrator where tenant isolation is enforced by `project_id` (ADR 0005), not by service boundary. A sibling service would duplicate the dispatcher, audit log, escalation pipeline, and secret rotation for no real isolation gain — the Studio tenant's data is already bounded by `project_id` inside the existing schema. The main cost of a single service is disciplined module boundaries, already enforced via the `coder-core-modular-monolith` design's import-linter contracts. If the `product_lifecycle` domain grows heavy enough to warrant runtime isolation, splitting it out is a bounded refactor, not a green-field rewrite.

## Consequences

- Positive: one deploy, one monitor surface, one migration path, one dispatcher to evolve.
- Positive: Studio projects appear in the existing project list, audit log, and metrics dashboard with no new plumbing.
- Negative: coder-core grows. Mitigation: import-linter contracts enforce that `studio` and `product_lifecycle` modules don't bleed into unrelated domains; add both to the contract file before the first Studio migration lands.
- Follow-up: update the import-linter contract file to include `studio` and `product_lifecycle` boundary rules before the Phase A schema migration.
