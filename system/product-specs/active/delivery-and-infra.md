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
served_by_designs: [coder-core-modular-monolith]
related_specs: [audit-log, continuous-deployment, knowledge-and-admin, observability, pipeline-operations, tenancy-and-access, tenant-isolation]
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

- [continuous-deployment](./delivery/continuous-deployment.md) — push-to-main
  CD with health-check, migration job, and traffic shift.
- [tenant-isolation](./delivery/tenant-isolation.md) — pytest harness +
  manifest drift checks that prove cross-project reads return 4xx,
  secrets aren't exfiltrated, and pipeline state doesn't leak.
- [coder-core-modular-monolith](./delivery/coder-core-modular-monolith.md)
  — the internal modular-monolith contract enforced by `import-linter`
  + application-service layer + extraction-ready `Protocol`s that
  keep `coder-core` shippable as one deployable.

## Cross-cutting concerns

- **Pipeline observability** (in [pipeline-operations](./pipeline-operations.md))
  surfaces deploy and migration status to the admin panel.
- **Audit log** records every deploy action — see
  [audit-log](./tenancy/audit-log.md).
- **Secret rotation** (separate WIP track, see roadmap) feeds the
  service-accounts surface in [tenancy-and-access](./tenancy-and-access.md).

## Links

- Designs: [system-overview](../../designs/active/system-overview.md),
  [coder-core-modular-monolith](../../designs/active/delivery/coder-core-modular-monolith.md)
- Repos: [coder-core](../../repos/coder-core.md),
  [coder-admin](../../repos/coder-admin.md),
  [coder-system](../../repos/coder-system.md)
- Related components: [tenant-isolation](./delivery/tenant-isolation.md),
  [continuous-deployment](./delivery/continuous-deployment.md),
  [coder-core-modular-monolith](./delivery/coder-core-modular-monolith.md),
  [audit-log](./tenancy/audit-log.md), [observability](./pipeline/observability.md)
