---
id: tenancy-and-access
title: Tenancy & access
type: index
status: active
owner: ro
created: 2026-05-02
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: Multi-tenancy enforcement and actor attribution at the engineering layer.
implements_specs: [tenancy-and-access]
related_designs: [system-overview, impersonation, audit-log, tenant-isolation]
affects_services: [coder-core, coder-admin]
parent: ~
---

# Tenancy & access

The engineering shape of multi-tenancy enforcement and actor
attribution.

## What this category covers

Engineering counterpart of the
[tenancy-and-access](../../product-specs/active/tenancy-and-access.md)
spec. Groups the designs that make the multi-tenancy invariant real
and that record who did what.

## Components

- [impersonation](./tenancy/impersonation.md) — short-lived role-scoped
  bearer tokens minted via `/v1/projects/{id}/impersonate/{role}`;
  used by local agents (Claude Code, Cursor) and the dispatcher.
- [audit-log](./tenancy/audit-log.md) — single-writer
  `record_audit_event` helper; phase-1 mutation-handler coverage;
  `audit_events` table; per-project + fleet read endpoints.
- [tenant-isolation](./delivery/tenant-isolation.md) — test-suite harness
  that asserts cross-project reads return 403 and pipeline state
  doesn't leak.

## Cross-cutting concerns

- **API surface**: every `/v1/projects/{id}/...` endpoint is
  project-scoped; the canonical row-scope check is
  `coder_core.access.load_in_project`.
- **Worker identity**: workers run under role-scoped GCP service
  accounts (per ADR 0006); the System Admin worker brokers
  time-bounded escalations.
- **Audit coverage**: every dispatcher-driven artifact write now
  emits an audit event (per the dispatcher Phase 4 helper added in
  the design 0057 follow-on).

## Links

- Specs: [tenancy-and-access](../../product-specs/active/tenancy-and-access.md),
  [multi-tenancy](../../product-specs/active/multi-tenancy.md),
  [service-accounts](../../product-specs/active/service-accounts.md)
- ADRs: [0005](../../adrs/0005-multi-tenant-coder-core.md),
  [0006](../../adrs/0006-per-role-service-accounts.md)
