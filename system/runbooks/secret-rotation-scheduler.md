---
id: secret-rotation-scheduler
title: Secret rotation — Cloud Run Job + Scheduler wiring
type: runbook
status: active
owner: ro
created: 2026-04-21
updated: 2026-04-21
last_verified_at: 2026-04-21
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [gcp, github, anthropic]
---

# Secret rotation — Cloud Run Job + Scheduler wiring

The rotation code (registry table, four kind rotators, break-glass +
tick endpoints, admin page) is deployed and flag-gated on
`SECRET_ROTATION_ENABLED` / `VITE_SECRET_ROTATION_ENABLED`. This
runbook documents the operator steps that take 0038 from
"implemented and flag-off" to "ticking in prod."

See the spec ([0038 WIP](../product-specs/wip/0038-secret-rotation.md))
and design ([0038 WIP](../designs/wip/0038-secret-rotation.md)) for
the product and technical views.

## What's wired on prod today (as of 2026-04-21)

- Cloud Run **Job** `coder-core-rotate-secrets` (europe-west1) runs
  `python -m coder_core.rotation.job` in the `coder-core` image.
- Cloud Scheduler job `coder-core-rotate-secrets` (europe-west1,
  `*/15 * * * *` UTC) calls
  `POST https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/vibedevx/jobs/coder-core-rotate-secrets:run`
  with OAuth credentials from `coder-core-sa@vibedevx.iam`. The
  service account has `roles/run.invoker` to execute the Job.
- `coder-core` service + Job both have `SECRET_ROTATION_ENABLED=true`.
- `GET /v1/_admin/secrets` returns `enabled: true`.
- Registry rows: `admin_jwt_signing_key` (next due 2026-05-20) and
  `github_app_private_key` (next due 2026-10-17). No per-project rows
  yet — onboarding should start inserting them for new projects;
  existing projects will need backfill.
- First rotation is one month out (admin JWT on 2026-05-20). Between
  now and then every tick is a no-op; that's the designed soak.

## The Cloud Run **Job** vs HTTP endpoint choice

The tick endpoint `POST /v1/_admin/secrets/tick` is admin-JWT-gated
(HS256 with audience `coder-core/admin`), and admin JWTs are minted
via Google OAuth exchange — not producible from a service account.
Cloud Scheduler's OIDC tokens don't satisfy `_require_admin`. So
rather than widen auth, we run `python -m coder_core.rotation.job`
as a Cloud Run Job — no HTTP, no JWT, just DB access with the same
service account the main service uses. Cloud Scheduler triggers the
Job via the Cloud Run Admin API (`jobs.run`) under the service
account's own OAuth scope. This mirrors the spec's original intent
("Cloud Run Job `coder-core-rotate-secrets`") and the HTTP `/tick`
endpoint stays useful for operator ad-hoc drains.

## When to run this

- Once per GCP project, at the point the fleet is ready to enable
  rotation. Already run on `vibedevx` on 2026-04-21 — this section
  is the replay path for other GCP projects or for disaster
  recovery.
- After a catastrophic event wiped the Cloud Scheduler or Job and
  the admin Secrets page shows no recent runs / every row past due.

## Who can run this

Operator (human) with:

- `roles/run.admin` on the project (to create/update the Cloud Run
  Job) and `roles/cloudscheduler.admin` (for the scheduler).
- `roles/iam.serviceAccountUser` on
  `coder-core-sa@vibedevx.iam.gserviceaccount.com` (to run the Job
  with that SA).
- `gcloud auth login` with a principal in one of the above.

## Prerequisites

- `coder-core` service is running and reachable. Smoke-check:
  `curl -sS -H "Authorization: Bearer $ADMIN_JWT"
  https://coder-core-<hash>.a.run.app/v1/_admin/secrets` returns a
  JSON body with the registry rows.
- `SECRET_ROTATION_ENABLED` unset (or `false`) on the service. Flip
  it last, after the Job + Scheduler are wired, so the transition
  from "enabled but no tick runs" → "ticking" is instantaneous.
- Seed rows exist in `secret_rotations` from migration
  [0042](../../../coder-core/migrations/versions/0042_secret_rotations.py).
- `coder-core-sa@vibedevx.iam.gserviceaccount.com` has
  `roles/run.invoker` at the project level (so Scheduler, running
  as this SA, can invoke the Job).

## Steps

### 1. Create the Cloud Run Job

Same image as the service, same SA, same Cloud SQL attachment. The
Job-specific bit is the overridden container entrypoint
(`python -m coder_core.rotation.job`) and no HTTP port.

```sh
IMAGE=$(gcloud run services describe coder-core \
  --project=vibedevx --region=europe-west1 \
  --format='value(spec.template.spec.containers[0].image)')

gcloud run jobs create coder-core-rotate-secrets \
  --project=vibedevx \
  --region=europe-west1 \
  --image="$IMAGE" \
  --service-account=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --set-cloudsql-instances=vibedevx:europe-west1:coder-core-db \
  --set-env-vars=ENVIRONMENT=prod,CLOUD_SQL_INSTANCE=vibedevx:europe-west1:coder-core-db,CLOUD_SQL_USER=coder-core-sa@vibedevx.iam,CLOUD_SQL_DATABASE=coder_core,GCP_PROJECT_ID=vibedevx,GITHUB_APP_ID=3325027 \
  --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,GITHUB_APP_PRIVATE_KEY=coder-github-app-private-key:latest,BROKER_SIGNING_KEY=coder-core-broker-signing-key:latest \
  --command=python \
  --args=-m,coder_core.rotation.job \
  --task-timeout=10m \
  --max-retries=0
```

When `coder-core` ships a new image, the Job keeps running the old
image until you re-update it. Two choices for staying current:

- **Coupled:** add a post-deploy step in the CI workflow that bumps
  the Job's image to whatever the service's new image is.
- **Decoupled (chosen here):** leave the Job pinned; update it when
  a rotator-touching PR ships. The Job container is short-lived
  (seconds per tick), so stale is fine for unrelated changes. The
  downside is rotator fixes need an explicit re-update.

### 2. Smoke-test the Job with the flag still off

```sh
gcloud run jobs execute coder-core-rotate-secrets \
  --project=vibedevx --region=europe-west1 --wait
```

Tail the logs: `skipped: "disabled"`, `Container called exit(0)`.
This confirms the container starts, reaches the DB, reads settings,
and exits cleanly. A failure here (usually Cloud SQL socket auth,
or missing IAM) is always cheaper to diagnose before the flag is on.

### 3. Wire Cloud Scheduler → Job

The scheduler posts to the Cloud Run Admin API's `jobs.run` endpoint
with an OAuth token under the service account's own scope. That
avoids standing up a separate invoker SA — `coder-core-sa` is
allowed to invoke its own Jobs via `roles/run.invoker`.

```sh
# Grant once at the project level if not already present.
gcloud projects add-iam-policy-binding vibedevx \
  --member=serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --role=roles/run.invoker --condition=None

gcloud scheduler jobs create http coder-core-rotate-secrets \
  --project=vibedevx \
  --location=europe-west1 \
  --schedule="*/15 * * * *" \
  --time-zone="UTC" \
  --http-method=POST \
  --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/vibedevx/jobs/coder-core-rotate-secrets:run" \
  --oauth-service-account-email=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

Verify:

```sh
gcloud scheduler jobs describe coder-core-rotate-secrets \
  --project=vibedevx --location=europe-west1 \
  --format='value(schedule,state,scheduleTime)'
# */15 * * * *   ENABLED   <next run, within 15m>
```

Force one immediately:

```sh
gcloud scheduler jobs run coder-core-rotate-secrets \
  --project=vibedevx --location=europe-west1
```

A minute later, confirm a fresh Job execution:

```sh
gcloud run jobs executions list \
  --project=vibedevx --region=europe-west1 \
  --job=coder-core-rotate-secrets --limit=3
```

The latest row should be `Completed`. Scheduler's `lastAttemptTime`
should match.

### 4. Flip the flag — service **and** Job

The env var is `SECRET_ROTATION_ENABLED` — **not**
`CODER_SECRET_ROTATION_ENABLED`. The code reads settings via
pydantic-settings without an env prefix, so the name you set must
match the field name exactly (case-insensitive). Watch for the
prefix — it's an easy mistake that silently no-ops the flag.

```sh
# Service — enables /v1/_admin/secrets endpoint and admin page signals.
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=SECRET_ROTATION_ENABLED=true

# Job — enables the tick()'s work path. Set separately; Job envs are
# per-deployment, not shared with the service.
gcloud run jobs update coder-core-rotate-secrets \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=SECRET_ROTATION_ENABLED=true \
  --image="$IMAGE"
```

Confirm:

```sh
curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
  https://coder-core-<hash>.a.run.app/v1/_admin/secrets | jq '.enabled'
# true
```

And one more Job execution, to verify the flag reached the Job:

```sh
gcloud run jobs execute coder-core-rotate-secrets \
  --project=vibedevx --region=europe-west1 --wait
```

Logs should now show `"skipped": null` with `rotated: []` /
`windows_closed: []` (provided nothing is due). That's the steady
state.

### 5. Watch the first real tick

Either wait for the next scheduled tick (≤ 15 min) or force one as
in step 3. First-tick behaviour depends on `next_due_at`:

- **Nothing due** (the 2026-04-21 enable state): `rotated: []`,
  `windows_closed: []`, `skipped: null`. Soak.
- **Fresh fleet (post-migration), singletons due immediately:**
  every tick can rotate one or more rows. Rotators are idempotent
  but if you'd rather stagger the first batch, push each row's
  `next_due_at` forward by a day or two **before** flipping. After
  the first natural rotation per row, cadence keeps them naturally
  staggered.
- **Steady state** (post first cycle): typically zero rotations per
  tick; an occasional `windows_closed` entry when a dual-value
  window elapses. Quiet is success.

Confirm via admin `/admin/secrets`: `last_rotated_at` advances,
`next_due_at` recomputes (`last_rotated_at + cadence_days`), any
`old_value_expires_at` appears during the dual-value window.

### 6. Confirm audit trail

```sh
curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
  "https://coder-core-<hash>.a.run.app/v1/projects/<project_id>/audit-events?action=secret.rotate&limit=10"
```

One row per rotation with `actor_method=system`,
`after.trigger="scheduled"`, and a correlation ID from the Job run.
For fleet-scope secrets (admin JWT, GitHub App key), query
`/v1/admin/audit-events` instead of the per-project endpoint.

## Success condition

- Cloud Run Job `coder-core-rotate-secrets` exists with the
  expected image, SA, env, command.
- Cloud Scheduler job `coder-core-rotate-secrets` is `ENABLED` with
  `*/15 * * * *` schedule.
- `GET /v1/_admin/secrets` returns `"enabled": true`.
- Most recent execution shows `skipped: null` and exit 0. Either
  empty `rotated` (nothing due) or actual rotations with matching
  audit rows.
- Admin `/admin/secrets` shows no past-due red chips and no
  `last_error` values.

## If something goes wrong

- **Scheduler triggers but Job doesn't execute** — Scheduler
  `lastAttemptTime` advances but `gcloud run jobs executions list`
  shows no new row. IAM: the scheduler's SA lacks
  `roles/run.invoker`. Re-apply the bind from step 3.
- **Job starts but errors immediately** — usually Cloud SQL IAM
  (missing `roles/cloudsql.client` on the SA) or secret access
  (`roles/secretmanager.secretAccessor`). Compare the Job's SA
  against the service's; they should match.
- **Flag flipped but tick still shows `skipped: "disabled"`** —
  the env var name is wrong. `pydantic-settings` has no prefix
  here; use `SECRET_ROTATION_ENABLED`, not `CODER_SECRET_ROTATION_ENABLED`
  (common mistake carried over from the spec text). `gcloud run
  jobs describe ... | grep -A1 ROTATION` confirms what the Job
  actually has.
- **`aiohttp.client.ClientSession: Unclosed connector` warnings
  in logs** — a rotator instantiates an HTTP client but the Job
  process exits before GC closes it. Cosmetic; exit code is 0 and
  the tick still commits the DB. Cleanup TODO.
- **A rotator fires `secret_rotation.failed` Slack alert** — the
  row's `last_error` is set on the admin page; `next_due_at`
  doesn't advance so the next tick retries. If the error persists
  across three consecutive ticks, push `next_due_at` far out to
  suppress retries while you investigate. Common causes: missing
  IAM on Secret Manager, Anthropic admin API quota, GitHub App
  two-key cap (clear an expired key before rotating).
- **Admin Secrets page shows every row past due** — either the
  scheduler isn't firing (`gcloud scheduler jobs describe` for
  `ENABLED` + recent `lastAttemptTime`) or every tick is skipping
  (flag off; see above).

## Related

- Spec: [0038 — automated secret rotation](../product-specs/wip/0038-secret-rotation.md)
- Design: [0038 — automated secret rotation](../designs/wip/0038-secret-rotation.md)
- Adjacent runbooks:
  [cloud-sql-bootstrap](./cloud-sql-bootstrap.md) (SA + Cloud SQL
  permissions),
  [knowledge-freshness-audit](./knowledge-freshness-audit.md) (the
  other scheduler-driven background job pattern, though it uses the
  HTTP-endpoint path with an admin JWT instead of a Cloud Run Job).
- AGENTS.md rule 5 — this runbook will migrate to `active/`
  alongside the spec + design fold once 0038 has soaked in prod.
