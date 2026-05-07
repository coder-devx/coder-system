---
id: delivery-and-infra
title: Delivery & infra
type: index
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: How code reaches production and how the system itself stays maintainable.
served_by_designs:
  - system-overview
  - coder-core-modular-monolith
related_specs:
  - pipeline-operations
  - knowledge-and-admin
  - tenancy-and-access
parent: ~
---

# Delivery & infra

How code reaches production and how the codebase itself stays
maintainable enough to ship safely.

## What this category covers

The hard-infrastructure side of the product: how every commit on
`main` flows to a running revision, how `coder-core` is structured to
keep scaling, and how the test harness pins the multi-tenancy contract.

## Components

- [continuous-deployment](./continuous-deployment.md) — push-to-main
  CD with health-check, migration job, and traffic shift.
- [tenant-isolation](./tenant-isolation.md) — pytest harness +
  manifest drift checks that prove cross-project reads return 4xx,
  secrets aren't exfiltrated, and pipeline state doesn't leak.

## Internal modular-monolith contract

`coder-core` is a single deployable FastAPI service with one
Postgres database. Internally it is structured as a modular monolith
— explicit module boundaries, application-service workflow layer,
and `Protocol`-style extraction seams — so an out-of-process worker
runtime or knowledge service can be split out later without rewriting
callers. This is the shape we keep, not a milestone we ship.

**Module boundaries** (enforced by `import-linter` in CI via
`make boundaries`):

- `api → application services → domain/repositories → db/integrations`.
- `domain` is independent (no imports from `api`, `mcp`, `workers`,
  etc.).
- `mcp` does not depend on the HTTP `api` package.
- `integrations` are leaf adapters.
- Feature modules (`workers`, `knowledge`, `ops`, …) do not depend on
  adapter modules (`api`, `mcp`).
- A tech-debt ledger in `pyproject.toml` records any tactically
  ignored edges; an empty ledger is the steady state.

**Application-service layer.** FastAPI routers authenticate, validate
input, and delegate to one service method. The service owns the
transaction boundary, calls the domain repositories and integrations,
and returns either a domain object the router maps to a response model
or raises a typed error the router maps to HTTP status. High-churn
workflows that live in services today: task create / retry / merge /
override, plan approve / reject, knowledge create / update / approve /
reject / ship / verify, project create / update / archive /
rotate-api-key, audit recording.

**Tenant isolation by construction.** `coder_core/access.py`'s
`load_in_project()` is the single canonical row-scope check; every
mutation/read workflow touched by the modular-monolith hardening
goes through it instead of ad-hoc `project_id` filters. The
[tenant-isolation](./tenant-isolation.md) harness asserts the
property continuously.

**Atomic mutation + audit.** `record_audit_event()` writes into the
caller's open session — never commits or flushes — so a rollback on
the outer mutation transaction rolls the audit row back with it.
`tests/test_audit_atomicity.py` injects a failure into the audit
write mid-workflow for five representative services covering the
three commit shapes (caller-commits, service-commits,
log-row-co-mutation) and asserts the mutation row reverts.

**Extraction-ready interfaces.** `coder_core/contracts.py` declares
`Protocol`-style interfaces for the boundaries we'd extract first.
The most load-bearing one is `WorkerDispatcher`, plumbed through
every service that kicks a worker (`tasks.plan_service.approve_plan`,
`tasks.service.create_task_in_project / retry_task_in_project /
override_task_in_project`). The default `_InProcessWorkerDispatcher`
implementation lives in `coder_core/workers/__init__.py`; tests inject
mocks via `set_dispatcher`. Replacing the implementation with an
out-of-process RPC client is now a one-file change.

**Service-level testing.** Most workflow tests run against the
service module directly without spinning up `httpx.AsyncClient`; the
route tier retains smoke coverage for auth, status codes, and
response shape. Feature-change PRs touch fewer unrelated modules
than before the hardening.

**Boundary doc.** `coder-core/docs/module-boundaries.md` enumerates
the current modules + allowed dependency direction; `make boundaries`
fails the build on contract drift.

## Cross-cutting concerns

- **Pipeline observability** (in [pipeline-operations](./pipeline-operations.md))
  surfaces deploy and migration status to the admin panel.
- **Audit log** records every deploy action — see
  [audit-log](./audit-log.md).
- **Secret rotation** (separate WIP track, see roadmap) feeds the
  service-accounts surface in [tenancy-and-access](./tenancy-and-access.md).

## Evolution

- coder-core-modular-monolith — coder-core modular monolith hardening (shipped 2026-04-26 as WIP 0051; promoted to active subject-slug on 2026-05-03).
  Module-boundary doc, four import-linter contracts (zero ignored
  exceptions at ship), seven thin-adapter routers (`tasks`,
  `task_plans`, `pipeline_runs`, `metrics`, `task_messages`,
  `impersonate`, `knowledge` writes), `coder_core/access.py`
  consolidating project ACL, `coder_core/contracts.py` declaring the
  `WorkerDispatcher` extraction seam, 80 service-level tests
  (~5.7 s combined), audit-atomicity regression tests across five
  services.

## Links

- Designs: [system-overview](../../designs/active/system-overview.md),
  [coder-core-modular-monolith](../../designs/active/coder-core-modular-monolith.md)
- Repos: [coder-core](../../repos/coder-core.md),
  [coder-admin](../../repos/coder-admin.md),
  [coder-system](../../repos/coder-system.md)
- Related components: [tenant-isolation](./tenant-isolation.md),
  [continuous-deployment](./continuous-deployment.md),
  [audit-log](./audit-log.md), [observability](./observability.md)
