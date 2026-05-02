---
id: delivery-and-infra
title: Delivery & infra
type: spec
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-02
last_verified_at: 2026-05-02
served_by_designs: [system-overview, "0051"]
related_specs: [pipeline-operations, knowledge-and-admin, tenancy-and-access]
parent: ~
---

# Delivery & infra

How code reaches production and how the system itself stays
maintainable.

## What this category covers

The hard-infrastructure side of the product: how every commit on
`main` flows to a running revision, how the codebase is structured to
keep scaling, and how the test harness pins the multi-tenancy
contract.

## Components

- [continuous-deployment](./continuous-deployment.md) — push-to-main
  CD with health-check, migration, recurring-job sync, and traffic
  shift.
- [tenant-isolation](./tenant-isolation.md) — test-suite harness
  that asserts cross-project reads return 403, secrets aren't
  exfiltrated, and pipeline state doesn't leak.
- [0051-coder-core-modular-monolith](./0051-coder-core-modular-monolith.md)
  — module-boundary contracts enforced by import-linter; the seam an
  out-of-process worker extraction would bind to.

## Cross-cutting concerns

- **Pipeline observability** (in [pipeline-operations](./pipeline-operations.md))
  surfaces deploy and migration status to the admin panel.
- **Audit log** records every deploy action — see
  [audit-log](./audit-log.md).
- **Secret rotation** (separate WIP track, see roadmap) feeds the
  service-accounts surface in [tenancy-and-access](./tenancy-and-access.md).

## Links

- Designs: [system-overview](../../designs/active/system-overview.md),
  [0051-coder-core-modular-monolith](../../designs/active/0051-coder-core-modular-monolith.md)
- Repos: [coder-core](../../repos/coder-core.md),
  [coder-admin](../../repos/coder-admin.md),
  [coder-system](../../repos/coder-system.md)
