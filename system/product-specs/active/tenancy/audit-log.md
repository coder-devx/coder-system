---
id: audit-log
title: Audit log
type: spec
status: active
owner: ro
created: 2026-04-19
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: Every mutation recorded with actor, action, before, after.
served_by_designs: [audit-log]
related_specs: [admin-panel, impersonation, service-accounts, task-orchestration, knowledge-api]
parent: tenancy-and-access
---

# Audit log

## What it is

A single append-only record of every mutation `coder-core` performs —
who did it, when, against what target, and the before/after snapshot
when the target is a tracked row. Every high-signal mutation endpoint
calls one helper (`record_audit_event`) inside its own transaction so
an audit row either lands with the mutation or not at all. Operators
query the log through per-project and fleet admin pages to reconstruct
an incident timeline, review a peer's actions, or answer a customer's
"who approved this?" without triangulating Cloud Run logs against git.

## Capabilities

- **Single append-only table.** `audit_events` (migration 0041) holds
  `id` (ULID, time-ordered), `project_id` (nullable for fleet-scoped
  actions), `actor`, `actor_method`, `action`, `target_type`,
  `target_id`, `before`/`after` JSONB, `correlation_id`, `created_at`,
  `retention_until` (`created_at + 365d`). No foreign keys — deleting
  a project never cascades audit rows.
- **One writer helper.** `coder_core.audit.record_audit_event(session,
  *, caller, action, target_type, target_id, project_id=None,
  before=None, after=None, correlation_id=None)` inserts a row into
  the caller's open session; it does not flush or commit. Rollback on
  the outer transaction rolls the audit row back with it — audit and
  mutation are atomic.
- **Correlation IDs per request.** `CorrelationMiddleware` accepts
  `X-Correlation-ID` (ULID only; malformed → 400
  `invalid_correlation_id`) or mints a fresh ULID, stamps
  `request.state.correlation_id`, and echoes the header on the
  response. Every audit row written during that request shares the
  ID; worker-initiated writes reuse the task's `pipeline_run_id` so a
  run's events cluster naturally.
- **Phase-1 mutation coverage.** Audit rows are written on 2xx for
  `knowledge.create_artifact` / `update_artifact` /
  `update_checkboxes` / `approve` / `reject`,
  `tasks.retry` / `override` / `merge`,
  `task_plans.approve` / `reject`,
  `budget.grant` / `revoke` / `monthly_reset`,
  `pipeline_runs.override`,
  `projects.archive` / `rotate_api_key`,
  `impersonate.issue_token`,
  `regression.acknowledge`, and `sessions.revoke`.
- **Per-project + fleet read.**
  `GET /v1/projects/{id}/audit-events` returns rows for the calling
  project only (existing `require_project_auth` gate).
  `GET /v1/admin/audit-events` (admin-JWT-gated) returns fleet rows
  with an optional `project_id` filter. Both accept `actor`, `action`,
  `target_type`, `since`, `until`, `limit` (≤200, default 50), and
  `after=<id>` — a keyset cursor on the ULID id (reverse-lexical).
- **Admin page with filters.** `/projects/:projectId/audit` and
  `/admin/audit` render a table with timestamp (local TZ + UTC
  tooltip), actor, action, target, project (fleet view), and a
  correlation chip that clicks through to all rows with the same ID.
  Expand-row shows `before`/`after` JSON pretty-printed side-by-side.
  Loading / empty / error branches render.
- **Retention stamp.** Every row carries `retention_until` computed at
  insert. No GC job yet — a later spec runs eviction; the column makes
  that change a wiring swap, not a migration.
- **Rollout flag.** `CODER_AUDIT_LOG_ENABLED` (default true) gates the
  writer helper only. Flag off → `record_audit_event` short-circuits,
  reads keep working on historical rows, and the admin page shows a
  "Audit logging disabled" banner above the table. Backout is one env
  flip — no rollback of migration 0041 (whose downgrade raises by
  design).

## Interfaces

- `GET /v1/projects/{id}/audit-events?actor=&action=&target_type=&since=&until=&after=&limit=`
  — per-project list, newest-first, keyset-paginated on ULID `id`.
- `GET /v1/admin/audit-events?project_id=&…` — fleet list, admin JWT.
- Request/response header: `X-Correlation-ID` — accepted when ULID,
  echoed on every response.
- Admin routes: `/projects/:projectId/audit`, `/admin/audit`.
- Python: `record_audit_event(...)` (internal import; no public SDK).
- Env: `CODER_AUDIT_LOG_ENABLED`.

## Dependencies

- task-orchestration — every mutation handler wires the helper.
- impersonation — `CallerIdentity.actor` / `actor_method` are the row
  authorship fields; broker tokens flow through unchanged.
- admin-panel — page consumes the two read endpoints.
- Postgres (`audit_events`, migration 0041).

## Evolution

- 0037 Audit log service (shipped 2026-04-19) — migration 0041 adds
  the `audit_events` table with indexes on `(project_id, created_at)`,
  `(actor, created_at)`, `(action, created_at)`, `(correlation_id)`.
  Downgrade is irreversible by design (`raise RuntimeError` — no
  rollback should drop audit data). `coder_core.audit.record_audit_event`
  + `Actions` constant module land the helper + action-string registry.
  `CorrelationMiddleware` registers before the auth middleware so the
  ID is set even on unauthenticated requests. Phase-1 wires the 15
  highest-signal mutation endpoints listed in Capabilities.
  `AuditLog.tsx` admin page + `listProjectAuditEvents` /
  `listFleetAuditEvents` client bindings. Behind
  `CODER_AUDIT_LOG_ENABLED` (default on).
- 0041 Escalation action namespace (shipped 2026-04-22) — five new
  actions registered with `Actions`: `escalation.opened`,
  `escalation.rung_fired`, `escalation.acknowledged`,
  `escalation.resolved`, `escalation.expired`. Every escalation
  state transition writes an `audit_events` row inside the same
  transaction as the `escalations` row update; the watcher's
  system-initiated transitions use `actor_type='system'`,
  `actor_id='escalation-watch'`. Slack-button acks from external
  users that don't resolve to an internal `user` land
  `actor_type='slack_external'` with the raw Slack handle captured
  in the row for traceability. See [escalations](../pipeline/escalations.md).
- 0042 Self-heal action namespace (shipped 2026-04-22) — two new
  actions: `self_heal.remediated`, `self_heal.failed`. The 5-minute
  watchdog writes a row per successful or errored remediation;
  `skipped_cap` and `dry_run` outcomes are attempt-row only (no
  audit event, to avoid noise). See [self-healing](../pipeline/self-healing.md).
- Claude OAuth auth-mode action (shipped 2026-04-22) — new
  `project.set_auth_mode` action registered with `Actions` and
  emitted from the admin `PATCH /v1/_admin/projects/{id}/auth-mode`
  handler. Captures the prior + new mode for the trail.
- `0054` Orchestrator reconciliation action namespace (shipped
  2026-04-28) — two new actions registered in `Actions`:
  `task.pr_url_reconciled_from_github` (successful reconciliation of
  a missing PR URL from GitHub) and `task.pr_url_reconcile_failed`
  (GitHub call errored or returned unexpected shape). Both write
  `target_type='task'`, `target_id=<task_id>`, `project_id=<project>`;
  success `details` carry `{pr_url, branch_name, commit_sha}`;
  failure `details` carry `{error_class, error_message}`. Written
  inside `_reconcile_pr_url_from_github` (fail-soft: exception →
  audit row + return None, never blocks the STUCK path). Observable
  via `/audit-events` filtered to these action strings; headline KPIs:
  reconciliation hit rate and failure rate per week. See
  [task-orchestration](../pipeline/task-orchestration.md).

## Links

- Designs: [audit-log](../../../designs/active/tenancy/audit-log.md)
- Related components: admin-panel, impersonation, service-accounts,
  task-orchestration, knowledge-api, escalations, self-healing
