---
id: "0038"
title: Automated secret rotation
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-21
last_verified_at: 2026-04-21
served_by_designs: ["0038"]
related_specs: [service-accounts, continuous-deployment, multi-tenancy, admin-panel, impersonation, audit-log]
---

# Automated secret rotation

## Problem

Coder holds a handful of long-lived secrets today. Each one has a
different rotation story, and most of those stories are "we rotate
when something breaks." Specifically:

- **Per-project API keys** — a rotate endpoint exists
  (`POST /v1/projects/{id}/rotate-api-key`) but nothing schedules
  calls to it. In practice, keys are never rotated.
- **Per-project Anthropic API keys** — set once at project onboarding,
  mounted via Secret Manager, no rotation mechanism documented.
- **Admin JWT HS256 signing secret** — named in `coder-admin`, rotated
  by hand the one time we've had reason to.
- **GitHub App private key** — explicitly documented as "no rotation
  chore — if compromised, regenerate and replace." A leaked key stays
  valid until a human notices.
- **Slack bot + signing secrets, Cloud SQL break-glass** — out of
  scope for this spec (Slack = low risk & low frequency, Cloud SQL
  break-glass is rotated after every use and lives in 1Password).
- **Impersonation tokens** — already short-lived and revocable; no
  rotation concept applies.

For internal dogfooding this is tolerable — the blast radius of a
leak is a single tenant. For external pilots it is not. The first
security-review question ("how do you rotate?") needs an answer
better than "we do it when we remember," and "key compromised"
needs to be a cron tick, not an overnight incident.

This spec adds a scheduled rotator that runs as a Cloud Run Job
behind Cloud Scheduler (same shape as the nightly regression
detector), a dual-value window pattern so rotation is zero-downtime
per secret, an audit row per rotation via 0037, and an admin surface
that shows per-secret last-rotated / next-due + a "rotate now"
button for break-glass.

## Users / personas

- **Security reviewer for a pilot** — wants to read "per-project API
  keys rotate every 90 days; admin JWT secret every 30 days; GitHub
  App key every 180 days" and see the last-rotated timestamp on every
  secret in the admin panel.
- **Oncall operator during a suspected leak** — wants to click
  "rotate now" for the scoped secret and have the old value
  invalidated within one dual-value window, with an audit row
  attributing the rotation.
- **SRE who owns the system** — wants rotation to happen
  automatically without a runbook task; when it fails, wants one
  Slack alert, not a pager.
- **Future us adding a new secret** — wants one registration point
  so a new secret inherits rotation for free instead of reimplementing
  the pattern.

## Goals

- **One scheduled rotator.** A single `rotate_secrets` job sweeps a
  registry of rotatable secrets at a 15-minute tick. Each entry
  declares its rotation cadence, its dual-value window, and the
  plug-in helper that performs the write + propagation + old-value
  invalidation.
- **Zero-downtime per secret.** Every rotation follows a dual-value
  window: write the new secret, switch readers to the new secret,
  leave the old value valid for a configurable overlap, then
  invalidate the old value. No in-flight request fails because of
  rotation.
- **Rotatable surface (phase 1):** per-project API keys, per-project
  Anthropic API keys, admin JWT HS256 signing secret, GitHub App
  private key.
- **Every rotation lands in the audit log.** New action
  `secret.rotate` with `target_type=secret`, `target_id=<canonical
  name>`, `actor_method=system`, `after.trigger="scheduled"` or
  `"break_glass"`. Correlation ID is the rotator's run ID.
- **Admin surface.** A new Admin → Secrets tab lists every rotatable
  secret with `canonical_name`, `cadence_days`, `last_rotated_at`,
  `next_due_at`, `dual_value_window_expires_at` (if any), and a
  "rotate now" button for privileged admins. A red chip appears on
  any secret whose `next_due_at` has passed without a successful
  rotation.
- **Failure is visible, not destructive.** A failed rotation leaves
  the old value in place and fires a `secret_rotation.failed` Slack
  alert; the registry row keeps `last_error` + `last_error_at` so
  the admin page surfaces it.
- **Backout in one flip.** `SECRET_ROTATION_ENABLED` gates the
  scheduler tick; flag-off leaves existing values alone.

## Non-goals

- **No secrets-at-rest re-encryption.** We do not change how secrets
  are stored (GCP Secret Manager with per-secret IAM). We change how
  they are replaced.
- **No detection of compromise.** Break-glass rotation is operator-
  initiated via the "rotate now" button; we don't try to infer leaks.
- **No Slack / Cloud SQL break-glass rotation.** Out of scope per the
  Problem section; documented and deferred.
- **No rotation of impersonation tokens.** Already short-lived; the
  session-revoke endpoint covers break-glass today.
- **No multi-region / multi-account.** Coder still runs in a single
  GCP project (`vibedevx`). The rotator reads and writes that
  project's Secret Manager.
- **No retirement of the `rotate-api-key` endpoint.** The scheduled
  rotator *calls* the existing endpoint for per-project API keys;
  operators can still hit it directly.
- **No custom KMS.** GCP Secret Manager is the key store; rotation
  uses Secret Manager's versioning directly.

## Scope

- **New registry table** `secret_rotations` (migration 0042):
  - `canonical_name: str` (PK, e.g. `admin_jwt_signing_key`,
    `project:coder:api_key`, `project:coder:anthropic_key`,
    `github_app_private_key`)
  - `kind: str` (enum-like string: `project_api_key`,
    `project_anthropic_key`, `admin_jwt_signing_key`,
    `github_app_private_key`)
  - `project_id: str | None` (populated for per-project kinds)
  - `cadence_days: int`
  - `dual_value_window_hours: int` (time the old value stays valid
    after the new one is written; kind-specific default — see below)
  - `last_rotated_at: datetime | None`
  - `next_due_at: datetime` (computed at write; rotator picks rows
    where `next_due_at <= now`)
  - `last_error: str | None`, `last_error_at: datetime | None`
  - `old_value_expires_at: datetime | None` (set during dual-value
    window; nulled on invalidation)
  - `rotation_version: int` (opaque monotonic counter for audit
    correlation).

- **Kind-specific rotators** — `coder_core.rotation.rotators.<kind>`:
  Each is a plug-in with a uniform interface:
  ```python
  async def rotate(entry: SecretRotationRow, *, secret_manager) -> RotationResult:
      ...
  ```
  returning the new version ID + the `old_value_expires_at` the
  rotator chose. Kinds:
  - **`project_api_key`** — calls the existing
    `rotate_project_api_key(project_id)` helper; writes the new
    hash to `projects.api_key_hash`, keeps the old hash in a new
    `projects.api_key_hash_previous` column (migration 0043) for
    the dual-value window. Auth middleware accepts either hash if
    `old_value_expires_at > now()`. Window default: **24 h**.
  - **`project_anthropic_key`** — generates a new Anthropic API key
    via the Anthropic admin API (new integration, **see 0038
    design**), writes it as a new Secret Manager version, tombstones
    the prior version after the window. Window default: **48 h**
    (long enough to cover worker in-flight sessions + a canary).
  - **`admin_jwt_signing_key`** — writes a new HS256 secret to
    Secret Manager; issuer starts signing with the new secret;
    verifier accepts both for the window, then drops the old
    version. Window default: **2 h** (admin tokens are 8 h TTL;
    two hours covers in-flight sessions — longer windows are
    wasted).
  - **`github_app_private_key`** — generates a new RSA key via the
    GitHub App API's new-key endpoint, writes it to Secret Manager;
    both keys remain usable until the window ends, then the old
    key is revoked via the same API. Window default: **6 h**.

- **Scheduler tick** — new Cloud Run Job `coder-core-rotate-secrets`
  triggered every 15 min by Cloud Scheduler (parallels the nightly
  regression detector). The tick:
  1. Selects `secret_rotations` rows where
     `next_due_at <= now() AND (last_error_at IS NULL OR
     last_error_at < now() - INTERVAL '15 min')` (single-writer
     advisory lock on `canonical_name`).
  2. Dispatches to the kind-specific rotator.
  3. On success, updates `last_rotated_at`, `next_due_at`,
     `old_value_expires_at = now() + dual_value_window_hours`,
     `last_error = NULL`, `rotation_version += 1`; writes an
     `audit_events` row with `action=secret.rotate` and
     `correlation_id=<run_id>`.
  4. On failure, writes `last_error` + `last_error_at`, fires
     `secret_rotation.failed` Slack alert (dedup per canonical_name
     per hour), and **does not** advance `next_due_at` (retry on
     next tick with backoff on error).

- **Dual-value window sweeper** — the same tick also closes windows:
  for every row where `old_value_expires_at < now()`, invalidate the
  old value (kind-specific: delete the `projects.api_key_hash_previous`,
  disable the old Secret Manager version, revoke the old GitHub App
  key, remove the old JWT secret from the verifier's accepted list),
  then null `old_value_expires_at`. A final audit row
  (`action=secret.rotate.window_closed`) records the close.

- **Break-glass endpoint** — `POST /v1/_admin/secrets/{canonical_name}/rotate-now`:
  admin-JWT gated; forces `next_due_at=now()` and writes an
  `audit_events` row with `after.trigger="break_glass"`. The next
  tick (≤15 min) performs the rotation. Returns 202 with the
  expected completion window.

- **Admin page** — new `/admin/secrets` route in coder-admin (fleet
  only, not per-project). Table: canonical name, kind, project,
  cadence, last rotated, next due, in-window y/n, last error (if
  any), "Rotate now" button per row. Red chip on past-due rows.
  Empty, loading, error states all render.

- **Rollout flag** — `SECRET_ROTATION_ENABLED` (default false
  in dev until the first green soak, then on in prod). Flag off →
  scheduler tick is a no-op; admin page shows the "Disabled"
  banner; break-glass endpoint returns 503 with a message.

- **Onboarding registration** — project onboarding
  (`POST /v1/projects`) auto-inserts two rows into `secret_rotations`:
  one `project_api_key`, one `project_anthropic_key`. The singleton
  rows (`admin_jwt_signing_key`, `github_app_private_key`) are
  seeded by migration 0042's data step.

## Acceptance criteria

- [ ] AC1: Migration 0042 creates `secret_rotations` with the 11
  columns listed above and seed rows for the two singletons.
  Migration 0043 adds `projects.api_key_hash_previous TEXT NULL`.
  Onboarding inserts two rotation rows per project.
- [ ] AC2: Cloud Run Job `coder-core-rotate-secrets` runs on the
  15-min Cloud Scheduler trigger when
  `SECRET_ROTATION_ENABLED=true`. Flag off → scheduler hook
  returns 204 without touching the DB.
- [ ] AC3: For each of the four kinds, `rotate(...)` writes a new
  value, updates `last_rotated_at` / `next_due_at` /
  `old_value_expires_at`, and emits an `audit_events` row with
  `action=secret.rotate`, `target_type=secret`,
  `target_id=<canonical_name>`, `after.trigger=scheduled`,
  `correlation_id=<run_id>`.
- [ ] AC4: During the dual-value window, both the old and new values
  authenticate successfully:
  - `project_api_key` — requests with either hash succeed until
    `old_value_expires_at`.
  - `project_anthropic_key` — workers receive the new key on their
    next broker fetch; in-flight workers with the old key continue
    to 200 for ≤ `dual_value_window_hours`.
  - `admin_jwt_signing_key` — admin JWTs signed with either secret
    verify until `old_value_expires_at`.
  - `github_app_private_key` — both keys open installations until
    `old_value_expires_at`.
- [ ] AC5: After `old_value_expires_at`, the next tick invalidates
  the old value (kind-specific) and emits
  `action=secret.rotate.window_closed` audit rows. Requests using
  the old value 401/403 from that point forward.
- [ ] AC6: A failing rotator writes `last_error` + `last_error_at`,
  fires one deduped `secret_rotation.failed` Slack alert, and leaves
  the old value intact. The next tick retries with backoff.
- [ ] AC7: `POST /v1/_admin/secrets/{canonical_name}/rotate-now`
  (admin-JWT-gated; non-admin 403) forces the rotation on the next
  tick and writes an `audit_events` row with
  `after.trigger=break_glass`.
- [ ] AC8: `/admin/secrets` renders the registry with all columns,
  renders a red chip on past-due rows, exposes "Rotate now" (calls
  the break-glass endpoint), and renders empty / loading / error
  states. Bundle delta < 8 kB gzipped.
- [ ] AC9: A per-endpoint integration test per kind asserts the full
  round-trip (new version written → both values work → window closes
  → old value fails) against a test Secret Manager stub.

## Metrics

- **Primary (operational):** `next_due_at > now()` on every row —
  i.e. zero past-due secrets across the fleet. The admin page's
  red-chip count is the dashboard.
- **Secondary:** `secret_rotation.failed` rate. Any non-zero weekly
  rate gets attention; two consecutive failures on the same
  canonical name page an operator via the existing Slack alerter.
- **Guardrail:** zero auth-failure spikes around rotations. A spike
  during a window = window too short; a spike after window close =
  readers caching past the window. Track via existing observability
  per-project auth-4xx rate, alert if +2σ within 1 h of a
  `secret.rotate` audit row.

## Open questions

- **Anthropic admin API access.** The `project_anthropic_key`
  rotator needs a key that itself can issue new per-project keys.
  Does Anthropic's current customer API support programmatic key
  creation / rotation? If not, phase-1 punts this kind to manual
  (rotator no-ops with an explicit "unsupported" audit row), and
  the spec ships with three kinds live + one documented stub.
- **Dual-value window on the GitHub App.** GitHub supports two
  active private keys per App but enforces a one-week grace once
  a key is deleted. We should confirm our 6h window closes well
  before that bound and doesn't accidentally rely on GitHub's
  deletion grace.
- **Admin JWT verifier cache.** The FastAPI middleware decodes the
  JWT per request today. Do we need an in-memory "accept both
  secrets" set, or is the straightforward `try secret_new else
  try secret_old` pattern fine for 2 h? Probably the latter.
- **Rate-limit interaction.** Rotating an API key invalidates the
  caller's rate-limit bucket (keyed on project id, not key). No
  change expected, but worth explicit test.
- **Per-project Anthropic key budget impact.** If we cycle the key
  while a worker is deep in a long-running call, does Anthropic's
  usage telemetry attribute the call to the old or new key? Affects
  `/metrics` `daily_cost` attribution during the window. Deferred
  to a phase-2 observability line.
- **Scheduler drift vs 15-min tick.** If the Cloud Run Job takes >
  15 min (extremely unlikely — each rotation is seconds), the next
  tick may overlap. The advisory lock on `canonical_name` already
  guards per-row concurrency, but a belt-and-braces "at most one
  job in flight" Cloud Scheduler contract is worth confirming.

## Links

- Designs: [0038 — automated secret rotation](../../designs/wip/0038-secret-rotation.md)
- Related specs: [service-accounts](../active/service-accounts.md),
  [continuous-deployment](../active/continuous-deployment.md),
  [multi-tenancy](../active/multi-tenancy.md),
  [admin-panel](../active/admin-panel.md),
  [impersonation](../active/impersonation.md),
  [audit-log](../active/audit-log.md).
- ROADMAP: Phase 6 — Security & Compliance. Successor to 0037 (audit
  log) in the same phase; prerequisite for 0039 (tenant isolation
  test harness — isolation tests should assert that a rotated key
  is rejected promptly).
