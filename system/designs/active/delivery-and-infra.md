---
id: delivery-and-infra
title: Delivery & infra
type: index
status: active
owner: ro
created: '2026-05-17'
updated: '2026-05-17'
last_verified_at: '2026-05-17'
summary: CI/CD, module boundaries inside coder-core, and the tenant-isolation test harness.
implements_specs: [delivery-and-infra]
related_designs: [system-overview, coder-core-modular-monolith, continuous-deployment]
affects_services: [coder-core, coder-admin]
parent: ~
---

# Delivery & infra

The engineering shape of how code reaches production and how the
runtime structure stays coherent.

## What this category covers

Engineering counterpart of the
[delivery-and-infra](../../product-specs/active/delivery-and-infra.md)
spec. Groups the designs that govern build / deploy pipelines, the
modular-monolith boundaries inside `coder-core`, and the
cross-tenant-leak detection harness.

## Components

- [continuous-deployment](./delivery/continuous-deployment.md) — `main`-merge
  auto-deploy via Workload Identity Federation; canary at 0% traffic,
  health-check on `/v1/health`, Cloud Run Jobs sync, traffic shift.
- [coder-core-modular-monolith](./delivery/coder-core-modular-monolith.md) —
  layered import contracts enforced by `import-linter` (adapters →
  services → domain); the four Protocol seams in `contracts.py` that
  prepare extraction-ready feature modules.
- [tenant-isolation](./delivery/tenant-isolation.md) — test-suite harness that
  asserts every endpoint enforces `project_id` scoping; cross-tenant
  reads return 404 (not 403) by construction.

## Cross-cutting concerns

- **Boundaries are CI-enforced**: `make boundaries` (also part of
  `make check`) runs `import-linter` against four contracts; new
  violations fail the merge — never silently ignored.
- **Deploy pipeline syncs recurring jobs**: every image push updates
  the Cloud Run Jobs that run the recurring ticks (`auto-approve`,
  `rotate-secrets`, `self-heal`, etc.) so they always run the same
  code as the service.
- **Tenant isolation is structural**: `coder_core.access.load_in_project`
  is the single canonical row-scope check; the modular-monolith
  contracts forbid alternate SQL paths so the harness only has to
  test one helper.

## Links

- Specs: [delivery-and-infra](../../product-specs/active/delivery-and-infra.md), [continuous-deployment](../../product-specs/active/continuous-deployment.md), [tenant-isolation](../../product-specs/active/tenant-isolation.md)
- ADRs: [0005](../../adrs/0005-multi-tenant-coder-core.md) (multi-tenant invariant)
- Repos: [coder-core](../../repos/coder-core.md), [coder-admin](../../repos/coder-admin.md)
