---
id: tenancy-and-access
title: Tenancy & access
type: spec
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-02
last_verified_at: 2026-05-02
served_by_designs: [impersonation, audit-log, tenant-isolation]
related_specs: [pipeline-operations, worker-roles, knowledge-and-admin]
parent: ~
---

# Tenancy & access

How one Coder system serves many projects in parallel without
crossing wires, and how every action is attributed to a real actor.

## What this category covers

A single Coder deployment manages multiple projects concurrently.
Every API call, log line, audit row, secret, and pipeline event is
project-scoped — the multi-tenancy invariant. This category groups
the specs that make that boundary real and the specs that record who
did what.

## Components

- [multi-tenancy](./multi-tenancy.md) — `project_id` everywhere
  invariant: API request scope, DB row scope, log scope, secret-store
  prefix scope.
- [impersonation](./impersonation.md) — short-lived role-scoped
  bearer tokens minted for local agents (or workers) acting on a
  project's behalf.
- [service-accounts](./service-accounts.md) — per-role GCP service
  accounts with minimum permissions; the System Admin worker brokers
  time-bounded access escalations.
- [audit-log](./audit-log.md) — every mutation is recorded with
  actor, method, action, before/after, project_id, correlation_id;
  retained for compliance review.

## Cross-cutting concerns

- **Worker identity**: workers run under role-scoped service accounts
  (see [worker-roles](./worker-roles.md)) and authenticate through
  brokered credentials.
- **Cross-project reads**: returning a row from a different project
  is a 403, not a silent leak. The single canonical row-scope check
  is `coder_core.access.load_in_project`.
- **Test harness**: [tenant-isolation](./tenant-isolation.md) (in
  [delivery-and-infra](./delivery-and-infra.md)) is the regression
  guard.

## Links

- Designs: [impersonation](../../designs/active/impersonation.md),
  [audit-log](../../designs/active/audit-log.md),
  [tenant-isolation](../../designs/active/tenant-isolation.md)
- ADRs: [0005](../../adrs/0005-multi-tenant-coder-core.md),
  [0006](../../adrs/0006-per-role-service-accounts.md)
