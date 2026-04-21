---
id: secret-rotation-scheduler
title: Secret rotation — Cloud Scheduler wiring + enable rollout
type: runbook
status: active
owner: ro
created: 2026-04-21
updated: 2026-04-21
last_verified_at: 2026-04-21
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [gcp, github, anthropic]
---

# Secret rotation — scheduler wiring and enable rollout

The rotation code (registry table, four kind rotators, break-glass +
tick endpoints, admin page) is deployed and flag-gated on
`CODER_SECRET_ROTATION_ENABLED` / `VITE_SECRET_ROTATION_ENABLED`. What
this runbook covers: the one-time operator steps that take 0038 from
"implemented and flag-off" to "ticking in prod."

See the spec ([0038 WIP](../product-specs/wip/0038-secret-rotation.md))
and design ([0038 WIP](../designs/wip/0038-secret-rotation.md)) for
the product and technical views. Parallels
[knowledge-freshness-audit](./knowledge-freshness-audit.md) for the
Cloud Scheduler wiring pattern and
[cloud-sql-bootstrap](./cloud-sql-bootstrap.md) for the service-
account prerequisites.

## When to run this

- Once per GCP project, at the point the fleet is ready to flip
  `CODER_SECRET_ROTATION_ENABLED` from its default `false` to `true`.
- After a catastrophic event wiped the Cloud Scheduler job and the
  rotator stopped ticking (admin Secrets page shows no recent runs,
  every row is past due).

## Who can run this

Operator (human) with:

- `roles/cloudscheduler.admin` on the `vibedevx` GCP project.
- `roles/run.invoker` on the `coder-core` service, granted to the
  `coder-core-invoker` service account (already provisioned via
  `infra/terraform/roles.tf` — verify before running).
- An admin JWT for the prod `coder-core` (the break-glass and tick
  endpoints are admin-gated; the OIDC token from the scheduler
  satisfies `_require_admin` via the same path used by
  `/v1/_admin/gc/branches` and the knowledge-freshness audit).

## Prerequisites

- `coder-core` revision with
  [`POST /v1/_admin/secrets/tick`](../../../coder-core/src/coder_core/api/secret_rotation.py)
  live. Smoke-check: `curl -sS -H "Authorization: Bearer $ADMIN_JWT"
  https://coder-core-<hash>.a.run.app/v1/_admin/secrets` returns a
  JSON body with `"enabled": false` plus the seeded registry rows.
- Fleet-wide `CODER_SECRET_ROTATION_ENABLED=false`. Leave it off
  until the scheduler is wired, then flip. Flipping before wiring
  means the admin page shows "enabled on server" but the rotator
  never ticks — confusing signal.
- `secret_rotations` registry rows seeded by migration
  [0042](../../../coder-core/migrations/versions/0042_secret_rotations.py)
  (`admin_jwt_signing_key`, `github_app_private_key`) plus per-project
  rows inserted by onboarding
  (`POST /v1/projects`). Confirm via the admin page at
  `/admin/secrets` or the `GET /v1/_admin/secrets` endpoint.

## Steps

### 1. Create the Cloud Scheduler job

```sh
# Every 15 min. Stays well under the rotators' wall-clock budget —
# each rotation is seconds, so overlapping ticks are not a concern,
# and the per-row advisory lock on canonical_name would guard anyway.

gcloud scheduler jobs create http coder-core-rotate-secrets \
  --project=vibedevx \
  --location=europe-west1 \
  --schedule="*/15 * * * *" \
  --time-zone="UTC" \
  --http-method=POST \
  --uri="https://coder-core-<hash>.a.run.app/v1/_admin/secrets/tick" \
  --headers="Content-Type=application/json" \
  --message-body="{}" \
  --oidc-service-account-email="coder-core-invoker@vibedevx.iam.gserviceaccount.com" \
  --oidc-token-audience="https://coder-core-<hash>.a.run.app"
```

Swap `<hash>` for the current `coder-core` Cloud Run revision host
(`gcloud run services describe coder-core --region=europe-west1
--format='value(status.url)'`).

### 2. Verify the job is scheduled

```sh
gcloud scheduler jobs describe coder-core-rotate-secrets \
  --project=vibedevx \
  --location=europe-west1
```

State should be `ENABLED`. `nextRunTime` should be within 15 min.

### 3. Fire a single manual tick as a smoke test

```sh
gcloud scheduler jobs run coder-core-rotate-secrets \
  --project=vibedevx \
  --location=europe-west1
```

While the flag is still off the tick endpoint returns
`{"skipped": "disabled", "rotated": [], "windows_closed": []}`.
That's the expected "wired-but-flag-off" shape — confirms the
OIDC token is accepted and the endpoint is reachable.

### 4. Flip the flag

Update the `coder-core` Cloud Run service env:

```sh
gcloud run services update coder-core \
  --project=vibedevx \
  --region=europe-west1 \
  --update-env-vars=CODER_SECRET_ROTATION_ENABLED=true
```

This triggers a new revision. Watch the deploy complete — a minute or
two — then re-check `GET /v1/_admin/secrets`: the response body's
top-level `"enabled"` flips to `true` and the admin page's "disabled"
banner disappears.

### 5. Watch the first real tick

Either wait ≤ 15 min for the next scheduled tick, or force one with
`gcloud scheduler jobs run coder-core-rotate-secrets ...` as in
step 3. First tick's effect depends on the registry state:

- **Fresh fleet (post-migration):** every row has `next_due_at` in
  the past (seed sets it to `created_at + cadence_days`, so the
  singletons are due on the cadence boundary from migration time).
  The first tick will rotate **everything due**. This is usually
  fine because the rotators are idempotent, but if you'd rather
  stagger, set each row's `next_due_at` manually to spread the
  first batch over a day or two before enabling.
- **Steady state:** typically zero rotations per tick; occasional
  windows closed. Quiet is success.

Confirm via the admin `/admin/secrets` page: `last_rotated_at`
advances, `next_due_at` recomputes, any `old_value_expires_at`
appears for a row currently in its dual-value window.

### 6. Confirm audit trail

```sh
curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
  "https://coder-core-<hash>.a.run.app/v1/_admin/audit-events?action=secret.rotate&limit=10"
```

One row per rotation with `actor_method=system`,
`after.trigger="scheduled"`, and a correlation ID matching the
scheduler run ID.

## Success condition

- Cloud Scheduler job `coder-core-rotate-secrets` is `ENABLED` with
  `*/15 * * * *` schedule.
- `GET /v1/_admin/secrets` returns `"enabled": true`.
- After one tick: admin page shows recent `last_rotated_at` for
  rows that were due, zero `last_error` values, and no past-due
  red chips.
- Audit log contains `secret.rotate` rows correlated to the
  scheduler run IDs.

## If something goes wrong

- **Tick returns 401** — the OIDC token isn't being accepted. Check
  the scheduler job's `oidc-service-account-email` is
  `coder-core-invoker@vibedevx.iam.gserviceaccount.com` and the
  service has `roles/run.invoker`. Compare against the
  knowledge-freshness scheduler job, which uses the same pattern.
- **Tick returns `{"skipped": "disabled", …}` after flag flip** —
  the revision update either failed or hasn't finished rolling.
  `gcloud run services describe coder-core --region=europe-west1
  --format='value(spec.template.spec.containers[0].env)'` shows the
  current env set; verify `CODER_SECRET_ROTATION_ENABLED=true`.
- **A rotator fires `secret_rotation.failed` Slack alert** — the
  row's `last_error` is set on the admin page; `next_due_at`
  doesn't advance so the next tick retries. If the error persists
  for three consecutive ticks, disable just that kind via the
  break-glass path (set `cadence_days` high to push `next_due_at`
  out) and investigate. Common causes: missing IAM on Secret
  Manager, Anthropic admin API quota, GitHub App key cap (two
  active keys maximum — clear an expired one before rotating).
- **Admin Secrets page renders but all rows show past-due red
  chips** — either the scheduler isn't firing (check
  `gcloud scheduler jobs describe` for `ENABLED` + recent
  `lastAttemptTime`) or every tick is skipping (flag off; see
  above).
- **First tick rotates everything at once and causes a burst of
  auth churn** — stagger by pushing each row's `next_due_at`
  forward before enabling. Worst case the dual-value windows
  overlap cleanly and no caller sees a 401; but staggering is
  cheap insurance for the first enable.

## Related

- Spec: [0038 — automated secret rotation](../product-specs/wip/0038-secret-rotation.md)
- Design: [0038 — automated secret rotation](../designs/wip/0038-secret-rotation.md)
- Adjacent runbooks:
  [knowledge-freshness-audit](./knowledge-freshness-audit.md) (same
  Cloud Scheduler + OIDC pattern),
  [cloud-sql-bootstrap](./cloud-sql-bootstrap.md) (service-account
  prereqs).
- AGENTS.md rule 5 — this runbook will move into `active/` alongside
  the spec + design fold once 0038 has completed its ramp.
