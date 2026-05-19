---
id: coder-core-modular-monolith
title: coder-core modular monolith
type: spec
status: active
owner: ro
created: 2026-04-26
updated: 2026-05-17
last_verified_at: 2026-05-17
summary: coder-core stays a single deployable with explicit internal boundaries so out-of-process extraction is one-file work later.
served_by_designs: [coder-core-modular-monolith]
related_specs: [continuous-deployment, tenant-isolation, audit-log, task-orchestration, knowledge-api]
parent: delivery-and-infra
---

# coder-core modular monolith

## What it is

`coder-core` is a single deployable FastAPI service with one Postgres
database. Internally it is structured as a modular monolith — explicit
module boundaries, an application-service workflow layer, and
`Protocol`-style extraction seams — so an out-of-process worker
runtime or knowledge service can be split out later without rewriting
callers. This is the shape we keep, not a milestone we ship; the
boundaries are enforced in CI and re-asserted on every PR.

## Capabilities

- **Enforced module boundaries.** `import-linter` runs in CI via
  `make boundaries` with these contracts:
  - `api → application services → domain/repositories → db/integrations`.
  - `domain` is independent (no imports from `api`, `mcp`, `workers`).
  - `mcp` does not depend on the HTTP `api` package.
  - `integrations` are leaf adapters.
  - Feature modules (`workers`, `knowledge`, `ops`, …) do not depend
    on adapter modules (`api`, `mcp`).
  - A tech-debt ledger in `pyproject.toml` records any tactically
    ignored edges; an empty ledger is the steady state.

- **Application-service workflow layer.** FastAPI routers authenticate,
  validate input, and delegate to one service method. The service owns
  the transaction boundary, calls the domain repositories and
  integrations, and returns either a domain object the router maps to
  a response model or raises a typed error the router maps to HTTP
  status. High-churn workflows in services: task create / retry /
  merge / override, plan approve / reject, knowledge create / update /
  approve / reject / ship / verify, project create / update / archive
  / rotate-api-key, audit recording.

- **Tenant isolation by construction.** `coder_core/access.py`'s
  `load_in_project()` is the single canonical row-scope check; every
  mutation/read workflow goes through it instead of ad-hoc `project_id`
  filters. The [tenant-isolation](./tenant-isolation.md) harness
  asserts the property continuously.

- **Atomic mutation + audit.** `record_audit_event()` writes into the
  caller's open session — never commits or flushes — so a rollback on
  the outer mutation transaction rolls the audit row back with it.
  `tests/test_audit_atomicity.py` injects a failure into the audit
  write mid-workflow for five representative services covering the
  three commit shapes (caller-commits, service-commits, log-row-
  co-mutation) and asserts the mutation row reverts.

- **Extraction-ready interfaces.** `coder_core/contracts.py` declares
  `Protocol`-style interfaces for the boundaries we'd extract first.
  The most load-bearing one is `WorkerDispatcher`, plumbed through
  every service that kicks a worker (`tasks.plan_service.approve_plan`,
  `tasks.service.create_task_in_project / retry_task_in_project /
  override_task_in_project`). The default `_InProcessWorkerDispatcher`
  implementation lives in `coder_core/workers/__init__.py`; tests
  inject mocks via `set_dispatcher`. Replacing the implementation
  with an out-of-process RPC client is a one-file change.

- **Service-level testing.** Most workflow tests run against the
  service module directly without spinning up `httpx.AsyncClient`; the
  route tier retains smoke coverage for auth, status codes, and
  response shape. Feature-change PRs touch fewer unrelated modules
  than before the hardening.

## Interfaces

- `make boundaries` — runs `import-linter` against the contracts in
  `coder-core/pyproject.toml`. Required CI step on every PR.
- `coder-core/docs/module-boundaries.md` — enumerates current
  modules and the allowed dependency direction. Source of truth for
  the `import-linter` contracts.
- `coder_core/access.py` — `load_in_project()` and friends.
- `coder_core/contracts.py` — `Protocol` interfaces for the
  extraction seams (`WorkerDispatcher` today; more land here on
  each new seam).
- `coder_core/workers/__init__.py` — default in-process dispatcher;
  `set_dispatcher()` for tests and future RPC swap.

## Dependencies

- [continuous-deployment](./continuous-deployment.md) — the boundary
  contract lives in CI, which the deploy pipeline runs.
- [tenant-isolation](./tenant-isolation.md) — exercises the
  `load_in_project()` contract end-to-end.
- [audit-log](../tenancy/audit-log.md) — exercises the audit-atomicity
  invariant.
- [task-orchestration](../pipeline/task-orchestration.md) — the
  `WorkerDispatcher` extraction seam.
- [knowledge-api](../knowledge/knowledge-api.md) — workflow-layer
  consumer of the modular shape.

## Evolution

- 2026-04-26 — Initial hardening shipped as WIP 0051: module-boundary
  doc, four import-linter contracts (zero ignored exceptions at ship),
  seven thin-adapter routers, `access.py` consolidation,
  `contracts.py` + `WorkerDispatcher` extraction seam, 80 service-level
  tests, audit-atomicity regression coverage across five services.
- 2026-05-03 — Promoted to active subject-slug.

## Links

- Designs: [coder-core-modular-monolith](../../../designs/active/delivery/coder-core-modular-monolith.md)
- Repos: [coder-core](../../../repos/coder-core.md)
- Related components: [continuous-deployment](./continuous-deployment.md),
  [tenant-isolation](./tenant-isolation.md),
  [audit-log](../tenancy/audit-log.md),
  [task-orchestration](../pipeline/task-orchestration.md),
  [knowledge-api](../knowledge/knowledge-api.md)
