---
id: "0005"
title: Multi-tenant Coder Core, project-aware in every call
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: [system-overview]
---

# ADR 0005 — Multi-tenant Coder Core, project-aware in every call

## Context

Coder will manage many projects. We need to decide whether each project
gets its own Coder Core instance, or whether one Core instance serves
many projects.

## Options considered

1. **One Coder Core per project** — strong isolation, no cross-tenant bugs,
   but operationally heavy: separate deploy, separate database, separate
   secrets per project. Onboarding a new project means standing up a new
   stack.
2. **Multi-tenant Coder Core** — one deployment, all projects sharing
   compute and code. Project isolation is enforced in software
   (`project_id` is required on every API call, ACL-checked).
3. **Hybrid** — multi-tenant control plane, per-project data plane.

## Decision

Multi-tenant Coder Core. Every API call is project-scoped: `project_id`
is required (in URL or token claims), and every code path that touches
data, secrets, GitHub, or GCP must carry the active `project_id` through.
There is no operation that acts across projects without an explicit fan-out
authorized by the user.

## Rationale

Per-project instances are operationally prohibitive for the rate of new
projects we expect. Multi-tenant lets us onboard a project by creating
a row in a table. The cost is discipline: project-awareness must be
enforced from day one in code, tests, and reviews — not retrofitted.

## Consequences

- Positive: trivially cheap to onboard a new project.
- Positive: one place to operate, monitor, and upgrade.
- Negative: a class of cross-tenant bugs is now possible (data leak,
  permission bleed). Mitigations:
  - `project_id` is a typed parameter on every internal function, not a
    string-keyed lookup.
  - Tests must include a "two projects, one request" case.
  - Audit log records `project_id` on every action; the Consultant role
    watches for cross-project access patterns.
- Follow-up: define the project ACL model in a follow-up design before
  the first multi-project release.
