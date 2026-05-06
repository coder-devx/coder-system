---
id: secret-rotation
title: Automated secret rotation
type: spec
status: active
owner: ro
created: 2026-05-06
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: []
related_specs: [service-accounts, audit-log, admin-panel, multi-tenancy, impersonation, continuous-deployment]
parent: tenancy-and-access
---

# Automated secret rotation

## What it is

A scheduled rotator that sweeps a registry of known secrets on a
15-minute tick, replacing long-lived credentials on a declared cadence
and recording every rotation in the audit log. Each secret follows a
dual-value window pattern — new value active immediately, old value
valid for a configurable overlap, then old value invalidated — so no
in-flight request fails because of rotation.

## Capabilities

- **Registry table.** `secret_rotations` (migration 0042) holds one
  row per managed secret: `canonical_name` (PK), `kind`, `project_id`
  (null for singletons), `cadence_days`, `dual_value_window_hours`,
  `last_rotated_at`, `next_due_at`, `last_error` / `last_error_at`,
  `old_value_expires_at`, `rotation_version`. Singleton rows
  (`admin_jwt_signing_key`, `github_app_private_key`) seeded by
  migration 0042's data step; per-project rows inserted by the
  `POST /v1/projects` onboarding handler.

- **Four rotatable kinds (phase 1):**
  - `project_api_key` — calls `rotate_project_api_key(project_id)`,
    writes new hash to `projects.api_key_hash`, parks the prior hash
    in `projects.api_key_hash_previous` (migration 0043); auth
    middleware accepts either hash during the window. Default window:
    24 h.
  - `project_anthropic_key` — generates a new Anthropic API key via
    the Anthropic admin API; new version written to Secret Manager,
    prior version tombstoned after window. Ships as a documented
    no-op stub if programmatic key creation is unsupported by
    Anthropic's API (emits `after.trigger='unsupported'` audit row).
    Default window: 48 h.
  - `admin_jwt_signing_key` — new HS256 secret written to Secret
    Manager; verifier accepts both during the window via sequential
    `try-new / try-old` decode (no in-memory cache). Default window:
    2 h.
  - `github_app_private_key` — new RSA key generated via GitHub App
    API; both keys usable until window closes; old key revoked via
    the GitHub App delete-key endpoint. Default window: 6 h.

- **Scheduler tick.** Cloud Run Job `coder-core-rotate-secrets`
  triggered every 15 min by Cloud Scheduler. Selects rows where
  `next_due_at <= now()` with an advisory lock per `canonical_name`;
  dispatches to the kind-specific rotator; on success updates
  `last_rotated_at`, `next_due_at`, `old_value_expires_at`,
  `rotation_version`, and writes an `audit_events` row with
  `action=secret.rotate`, `target_type=secret`,
  `target_id=<canonical_name>`, `correlation_id=<run_id>`. On
  failure writes `last_error` + `last_error_at`, fires a deduped
  `secret_rotation.failed` Slack alert (once per canonical name per
  hour), and leaves `next_due_at` unchanged so the next tick retries.

- **Dual-value window sweeper.** The same tick also closes windows:
  for rows where `old_value_expires_at < now()`, kind-specific
  invalidation runs (delete `api_key_hash_previous`, disable old
  Secret Manager version, revoke old GitHub App key, drop old JWT
  secret from verifier list); `old_value_expires_at` nulled; a
  final audit row with `action=secret.rotate.window_closed` is written.

- **Break-glass endpoint.**
  `POST /v1/_admin/secrets/{canonical_name}/rotate-now` (admin-JWT
  gated; non-admin 403) forces `next_due_at=now()` and writes an
  audit row with `after.trigger="break_glass"`. Returns 202 with
  the expected completion window (≤ 15 min). The next tick performs
  the actual rotation.

- **Rollout flag.** `SECRET_ROTATION_ENABLED` (default false in dev;
  true in prod after first green soak). Flag off → scheduler tick is
  a no-op, admin page shows a "Disabled" banner, break-glass endpoint
  returns 503.

- **Onboarding.** `POST /v1/projects` auto-inserts two rows per new
  project: one `project_api_key`, one `project_anthropic_key`.

## Interfaces

- Cloud Run Job: `coder-core-rotate-secrets` (Cloud Scheduler, 15 min).
- Break-glass: `POST /v1/_admin/secrets/{canonical_name}/rotate-now`
  — 202 on accepted / 503 when disabled / 403 on non-admin.
- Admin page: `/admin/secrets` — see [admin-panel](./admin-panel.md).
- Env: `SECRET_ROTATION_ENABLED`.
- DB: `secret_rotations` (migration 0042),
  `projects.api_key_hash_previous TEXT NULL` (migration 0043).
- Audit actions: `secret.rotate`, `secret.rotate.window_closed`
  — see [audit-log](./audit-log.md).

## Dependencies

- audit-log — `record_audit_event` called on every rotation and
  window close; `Actions` module holds the two new action constants.
- service-accounts — rotator runs under the SysAdmin role SA;
  reads and writes Secret Manager via broker-escalated credentials.
- admin-panel — `/admin/secrets` page exposes the registry and
  break-glass button.
- multi-tenancy — `project_id` on per-project kinds; singleton rows
  carry `project_id=NULL`.
- Postgres (`secret_rotations` migration 0042; `projects` column
  migration 0043).

## Metrics

- **Primary:** zero past-due rows (`next_due_at > now()` across the
  fleet). Admin page red-chip count is the live dashboard.
- **Secondary:** `secret_rotation.failed` weekly rate. Two consecutive
  failures on the same canonical name page the on-call operator.
- **Guardrail:** per-project auth-4xx rate. A +2σ spike within 1 h of
  a `secret.rotate` audit row signals a window that is too short or
  readers caching stale credentials.

## Evolution

- 0038 Automated secret rotation (shipped 2026-05-06, migrations
  0042 + 0043) — initial implementation. `secret_rotations` table
  seeded with two singleton rows; onboarding auto-inserts per-project
  rows. Four kind-specific rotators behind `SECRET_ROTATION_ENABLED`.
  Break-glass endpoint, dual-value window sweeper, deduped Slack
  failure alerts, and `/admin/secrets` registry tab.

## Links

- Designs: [secret-rotation](../../designs/wip/0038-secret-rotation.md)
- Related components: [service-accounts](./service-accounts.md),
  [audit-log](./audit-log.md), [admin-panel](./admin-panel.md),
  [multi-tenancy](./multi-tenancy.md),
  [impersonation](./impersonation.md),
  [continuous-deployment](./continuous-deployment.md)
