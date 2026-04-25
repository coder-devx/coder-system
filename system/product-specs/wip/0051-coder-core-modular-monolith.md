---
id: '0051'
title: coder-core modular monolith hardening
type: spec
status: wip
owner: ro
created: 2026-04-25
updated: 2026-04-25
last_verified_at: 2026-04-25
served_by_designs: ['0051']
related_specs:
  - task-orchestration
  - knowledge-api
  - multi-tenancy
  - audit-log
  - observability
  - developer-worker
  - reviewer-worker
  - pm-worker
  - architect-worker
  - team-manager-worker
---

# 0051 — coder-core modular monolith hardening

## Problem

`coder-core` has grown from the original walking skeleton into the
runtime center of the Coder system: project CRUD, auth, tenant ACLs,
knowledge reads and writes, task orchestration, role-worker execution,
MCP, audit, escalation, self-healing, secret rotation, budget gates,
metrics, and external integrations all live in one FastAPI service.

That shape is still the right deployment model. The strongest system
invariants — project-scoped data access, audit correlation, worker
identity, task state transitions, and knowledge-write safety — cross
feature boundaries. Splitting prematurely into microservices would
replace local call/transaction complexity with distributed call,
deployment, observability, and data-consistency complexity.

The problem is internal coupling, not process size. Some API routers
carry business workflow directly, transaction boundaries are not
uniformly obvious, cross-module calls can bypass a clear application
interface, and the natural future extraction seams (worker runtime,
knowledge service, orchestration, audit/ops) are not explicit enough.
This slows changes and makes it harder to know whether a bug fix is
local or crosses an invariant.

This spec makes `coder-core` a cleaner modular monolith: one service,
one database, one test suite, but with explicit internal modules,
application-service boundaries, dependency direction, and extraction-
ready interfaces.

## Users / personas

- **Coder maintainers** need to add features without re-reading the
  entire `coder-core` call graph.
- **Future worker-runtime maintainers** need a clean boundary around
  dispatch and role execution before considering process extraction.
- **Security reviewers** need tenant isolation and audit invariants to
  be enforced centrally rather than by repeated handler convention.
- **Operators** need safer deploys: a refactor should reduce coupling
  and risk without introducing a second service to operate.

## Goals

- Keep `coder-core` as a single deployable service for this phase.
- Make FastAPI routers thin: HTTP/auth/request mapping only, with
  business workflows delegated to application services.
- Define first-class internal modules for projects, tasks, pipeline,
  knowledge, workers, audit, escalations, ops, and integrations.
- Centralize transaction ownership in application services or explicit
  unit-of-work helpers.
- Centralize project access checks and project-scoped query helpers so
  tenant isolation is enforced by construction.
- Define internal protocols for future extraction seams, especially
  worker dispatch, knowledge repository access, audit recording, and
  event publication.
- Move most business-logic coverage below FastAPI: unit/service tests
  should exercise workflows without needing an HTTP client.
- Preserve all public HTTP, MCP, CLI, and admin-panel contracts.

## Non-goals

- No new microservices.
- No database split.
- No queue/broker replacement unless a small in-process interface is
  needed to describe the existing behavior.
- No route renames or frontend rewrites.
- No broad style-only refactor. Each moved workflow needs either a
  clearer boundary, less duplication, stronger invariant enforcement,
  or easier tests.
- No change to project isolation semantics, auth modes, worker model
  routing, budget behavior, or knowledge schemas.

## Scope

### Stage 1 — Boundary map and guardrails

- Produce a `coder-core` module-boundary map covering current routers,
  domain models, worker modules, integrations, background jobs, and
  shared helpers.
- Document allowed dependency direction:
  `api -> application services -> domain/repositories -> db/integrations`.
- Identify forbidden edges, especially feature modules importing API
  routers, workers reaching through unrelated feature internals, or
  handlers bypassing project ACL helpers.
- Add lightweight import-boundary tests or static checks for the most
  important forbidden edges.

### Stage 2 — Application-service layer

- Introduce application services around the highest-churn workflows:
  task creation/retry/merge, task-plan approve/reject, knowledge
  create/update/ship/verify, project admin mutations, audit recording,
  and worker dispatch kickoff.
- Keep routers as adapters that authenticate, validate, call one
  service method, and map domain/application errors to HTTP.
- Keep response models and route behavior unchanged.

### Stage 3 — Transaction and unit-of-work cleanup

- Make transaction ownership visible for each mutation workflow.
- Prevent helper functions from committing opportunistically unless the
  helper explicitly owns the whole workflow.
- Co-locate audit writes with the mutation transaction when atomicity
  is required.
- Add tests for rollback behavior on representative failures.

### Stage 4 — Tenant isolation by construction

- Promote project access checks and project-scoped repository/query
  helpers into shared internal APIs.
- Update mutation/read workflows touched by this spec to use those
  helpers instead of ad hoc `project_id` filters.
- Extend the existing isolation manifest/checks when new internal
  surfaces expose tenant-scoped behavior.

### Stage 5 — Extraction-ready interfaces

- Define `Protocol`-style boundaries for:
  - worker dispatch / role execution
  - knowledge repository reads and writes
  - audit event recording
  - event/SSE publication
  - external GitHub/GCP/Slack adapters
- Keep implementations in-process.
- Ensure interfaces are shaped around Coder semantics, not transport
  assumptions. A future extraction should be able to replace an
  implementation with a queue or network client without rewriting
  callers.

### Stage 6 — Test migration

- Convert representative HTTP-heavy behavior tests into service-level
  tests where possible.
- Keep a small set of route tests for auth, status codes, response
  shape, and integration wiring.
- Add regression tests for the currently fragile freshness-date case:
  freshness tests must freeze or inject "today" rather than depend on
  wall-clock drift.

## Acceptance criteria

- [ ] Public API compatibility: existing `coder-core` route tests still
  pass without route/response contract changes.
- [ ] `make check` passes in `coder-core`.
- [ ] A checked-in module-boundary document exists for `coder-core`.
- [ ] At least four high-churn routers have thin-adapter shape, with
  workflow logic moved into application services.
- [ ] Task creation/retry/merge, knowledge write/ship, project admin
  mutation, and plan approve/reject each have an obvious transaction
  owner.
- [ ] Representative mutation tests prove audit + data writes are
  atomic where required.
- [ ] Project ACL enforcement for touched workflows goes through shared
  access/query helpers.
- [ ] Import-boundary/static tests catch at least the highest-risk
  forbidden edges.
- [ ] Service-level tests cover the main workflows moved out of routers.
- [ ] Worker dispatch is called through an internal interface rather
  than direct router-to-worker coupling.
- [ ] Knowledge repository access is called through an internal
  interface rather than direct ad hoc GitHub calls from unrelated
  modules.
- [ ] The freshness test suite no longer fails as calendar time passes.

## Metrics

- Number of route functions over 100 lines trends down.
- Number of business-logic tests that require `httpx.AsyncClient`
  trends down.
- Isolation suite remains green and blocking.
- `coder-core` `make check` runtime does not grow by more than 20%.
- Feature-change PRs touch fewer unrelated modules after the refactor
  compared with the prior month.

## Open questions

- Should import-boundary checks use a small custom pytest, `grimp`,
  `import-linter`, or a simpler `rg`-based guard?
- Should the unit-of-work helper be explicit infrastructure or simply
  documented use of `db.session_scope()` plus service ownership?
- Which router is the first pilot: `tasks`, `knowledge`, or
  `task_plans`?
- Should worker dispatch become an in-process queue interface now, or
  only a protocol around the existing dispatcher call?

## Links

- Design: [0051](../../designs/wip/0051-coder-core-modular-monolith.md)
- Related specs: task-orchestration, knowledge-api, multi-tenancy,
  audit-log, observability, worker specs
