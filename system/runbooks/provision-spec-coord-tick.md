---
id: provision-spec-coord-tick
title: Provision the coder-core-spec-coord-tick Cloud Run Job + Scheduler (spec 0068)
type: runbook
status: active
owner: ro
created: 2026-05-05
updated: 2026-05-05
last_verified_at: 2026-05-05
applies_to_services: [coder-core]
applies_to_integrations: [cloud-run-jobs, cloud-scheduler]
---

# Provision the coder-core-spec-coord-tick Cloud Run Job + Scheduler

## When to run this

One-time bootstrap to put the spec 0068 lifecycle coordinator on a
real schedule. The CI deploy workflow's "Sync recurring job images"
step already includes `coder-core-spec-coord-tick` in its list and
silently skips when the Job doesn't exist; running this for the
first time turns the skip into a real image bump on every push.

You should run this:

- Once per environment (currently only `vibedevx` / prod).
- Again if the Job is ever recreated (manual delete, env rename,
  region migration).

## Who can run this

Operator with `roles/run.admin` and `roles/cloudscheduler.admin` on
the `vibedevx` GCP project, plus
`roles/iam.serviceAccountUser` on
`coder-core-sa@vibedevx.iam.gserviceaccount.com`. The break-glass
`gha-deployer` SA also works.

## Prerequisites

- `gcloud` authenticated for the target project
  (`gcloud config set account ro@vibedevx.com` then
  `gcloud auth login` if needed).
- `coder-core` service is already running in
  `europe-west1` and the latest image carries the
  `coder_core.spec_runs.coordinator` module — landed in coder-core
  PR [#113](https://github.com/coder-devx/coder-core/pull/113), with
  the remaining probes in PRs
  [#124](https://github.com/coder-devx/coder-core/pull/124) and
  [#125](https://github.com/coder-devx/coder-core/pull/125).
- Cloud SQL connector socket `/cloudsql/vibedevx:europe-west1:coder-core-db`
  is already wired into the runtime SA via the existing tick Jobs
  (`coder-core-self-heal-tick`, `coder-core-rotate-secrets`).

## Background

ADR [0015](../adrs/0015-ship-gate-in-coder-pipeline.md) put the
ship gate inside the Coder pipeline. Spec
[0068](../product-specs/wip/0068-spec-lifecycle-coordinator.md)
generalises the same pattern one stage up: a 60-second tick walks
every active `spec_runs` row, evaluates state-specific probes, and
either advances the run (dispatching the next role's worker task
where applicable) or short-circuits via a circuit breaker.

The coordinator's claim-and-process loop is in
`src/coder_core/spec_runs/coordinator.py`. It mirrors
`coder_core.approvals.tick` in shape: one HTTP-free tick per
scheduled invocation, per-row sessions so a single failure can't
stall siblings, `FOR UPDATE SKIP LOCKED` so two ticks can't both
claim the same row.

The Job's container image is identical to the service image; only
the entrypoint overrides change.

## Steps

### 1. Create the Cloud Run Job

Mirror `coder-core-self-heal-tick`'s shape; the spec-coord tick is
strictly DB-bound (no GitHub or Anthropic calls — those happen on
the dispatched worker tasks themselves) so the env is minimal:

```sh
PROJECT=vibedevx
REGION=europe-west1
SERVICE=coder-core
IMAGE=$(gcloud run services describe "$SERVICE" \
  --project="$PROJECT" --region="$REGION" \
  --format='value(spec.template.spec.containers[0].image)')

gcloud run jobs create coder-core-spec-coord-tick \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --command=python \
  --args="-m,coder_core.spec_runs.coordinator" \
  --max-retries=0 \
  --task-timeout=120s \
  --cpu=1 \
  --memory=512Mi \
  --parallelism=1 \
  --tasks=1 \
  --set-env-vars=ENVIRONMENT=prod,CLOUD_SQL_INSTANCE=vibedevx:europe-west1:coder-core-db,CLOUD_SQL_USER=coder-core-sa@vibedevx.iam,CLOUD_SQL_DATABASE=coder_core,GCP_PROJECT_ID=vibedevx
```

Notes:

- `--task-timeout=120s` is generous; a real tick takes <5 s. The
  cap is loose enough to absorb a one-off DB stall without falsely
  killing the tick.
- `--set-cloudsql-instances` is intentionally **omitted**, matching
  the existing tick Jobs. Cloud SQL access goes through the
  in-process `cloud-sql-python-connector` library + IAM auth, not
  the Cloud Run-managed sidecar.
- `--max-retries=0` is the same value the other tick Jobs use; a
  failed tick is the next tick's problem, not a retry's.
- `--cpu=1 --memory=512Mi` mirrors `self-heal-tick`. Bump if the
  fleet grows past ~100 simultaneous spec_runs and the tick starts
  needing more headroom.
- **Circuit breakers ship default-OFF** behind
  `spec_run_breakers_enabled` (see coder-core PR
  [#125](https://github.com/coder-devx/coder-core/pull/125)). Add
  `--update-env-vars=SPEC_RUN_BREAKERS_ENABLED=true` per Step 5
  once the soak passes.

### 2. Smoke-test the Job

Run one execution by hand and confirm the container starts, reaches
the DB, runs a tick, and exits cleanly. With no candidate rows the
tick is a clean no-op (`{"succeeded": 0, "errored": 0, "processed": []}`).

```sh
gcloud run jobs execute coder-core-spec-coord-tick \
  --project="$PROJECT" --region="$REGION" --wait
```

Inspect the logs:

```sh
gcloud run jobs executions list \
  --project="$PROJECT" --region="$REGION" \
  --job=coder-core-spec-coord-tick --limit=3

EXEC=$(gcloud run jobs executions list \
  --project="$PROJECT" --region="$REGION" \
  --job=coder-core-spec-coord-tick --limit=1 \
  --format='value(name)')
gcloud beta run jobs executions logs read "$EXEC" \
  --project="$PROJECT" --region="$REGION"
```

Expected output near the bottom of the log:

```json
{"succeeded": 0, "errored": 0, "processed": []}
```

A non-zero `processed` count is fine if any spec_runs rows exist —
the goal is "tick ran end-to-end without exception."

### 3. Wire Cloud Scheduler → Job

The runtime SA already has `roles/run.invoker` on the project from
the rotation runbook (Step 3 in
[secret-rotation-scheduler.md](secret-rotation-scheduler.md)). If
you're starting from a fresh GCP project, run that grant first.

```sh
gcloud scheduler jobs create http coder-core-spec-coord-tick \
  --project="$PROJECT" \
  --location="$REGION" \
  --schedule="*/1 * * * *" \
  --time-zone="UTC" \
  --http-method=POST \
  --uri="https://${REGION}-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/${PROJECT}/jobs/coder-core-spec-coord-tick:run" \
  --oauth-service-account-email=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

`*/1 * * * *` (every minute) matches the design's 60-second tick
budget. Bump to `*/5 * * * *` if the fleet stays small and the
once-a-minute log noise is undesirable; the only cost of a longer
cadence is per-row dispatch latency, capped at the cadence interval.

Verify and force one immediate run:

```sh
gcloud scheduler jobs describe coder-core-spec-coord-tick \
  --project="$PROJECT" --location="$REGION" \
  --format='value(schedule,state)'
# */1 * * * *   ENABLED

gcloud scheduler jobs run coder-core-spec-coord-tick \
  --project="$PROJECT" --location="$REGION"

# Confirm a fresh execution lands within ~30 s.
gcloud run jobs executions list \
  --project="$PROJECT" --region="$REGION" \
  --job=coder-core-spec-coord-tick --limit=3
```

### 4. Verify CI image-sync now picks the Job up

Push a no-op commit to coder-core's `main` (or wait for the next
real merge) and watch the `Sync recurring job images` step in CI.
It should now log a successful Cloud Run update for
`coder-core-spec-coord-tick` instead of the previous `skipping`
line.

The relevant loop is in
`coder-core/.github/workflows/ci.yml` around the `for job in
coder-core-auto-approve-tick coder-core-knowledge-audit-tick
coder-core-rotate-secrets coder-core-self-heal-tick
coder-core-spec-coord-tick coder-core-worker; do` block. The Job
name was added in coder-core PR
[#122](https://github.com/coder-devx/coder-core/pull/122) ahead of
this provisioning step, so the loop has been silently skipping
since then.

### 5. (After soak) flip circuit breakers ON

The cost / stuck breakers are gated by
`spec_run_breakers_enabled` (default OFF). Flip after at least
24 h of clean ticks confirms the coordinator is producing the
expected state-advance audit rows and not pausing healthy runs:

```sh
gcloud run jobs update coder-core-spec-coord-tick \
  --project="$PROJECT" --region="$REGION" \
  --update-env-vars=SPEC_RUN_BREAKERS_ENABLED=true
```

The defaults from coder-core's
`Settings.spec_run_*` fields apply: $50 cap, 3-attempt retry cap,
per-project `sla_stall_minutes` (already on `projects` rows). Tune
`SPEC_RUN_COST_CAP_USD` per environment if needed.

## Success condition

- `gcloud run jobs describe coder-core-spec-coord-tick` returns a
  healthy spec.
- A smoke-test execution returns `{"succeeded": 0, "errored": 0, "processed": []}` (or non-zero counts if there are real rows) and exits 0.
- `gcloud scheduler jobs describe coder-core-spec-coord-tick`
  shows `state: ENABLED` and `schedule: */1 * * * *`.
- A subsequent push to coder-core `main` triggers a successful
  `Sync recurring job images` step (no more "skipping" line).
- `audit_events` starts accumulating `spec_run.transitioned` rows
  for any newly-accepted spec.

## If something goes wrong

### `PERMISSION_DENIED` from Scheduler when invoking the Job

The runtime SA lacks `roles/run.invoker` at the project level. Run:

```sh
gcloud projects add-iam-policy-binding "$PROJECT" \
  --member=serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --role=roles/run.invoker --condition=None
```

### Job execution times out at 120 s

The `tick()` function is bounded by the size of the candidate
spec_runs claim list and one DB round-trip per row. 120 s is
generous (~hundreds of rows). If the tick legitimately needs
longer, raise `--task-timeout`. If a single row is hanging the
tick, check the row's `paused_reason` and ack via the admin
spec-runs endpoint.

### Job execution exits 1 with a SQLAlchemy connection error

Cloud SQL connector failed to authenticate. Common causes:

- `CLOUD_SQL_USER=coder-core-sa@vibedevx.iam` is missing the
  `.iam` suffix or has a stray `.gserviceaccount.com`.
- The runtime SA lost `roles/cloudsql.client` on the project.
- The Cloud SQL instance is paused / restarted.

### Tick logs `spec_coordinator.tick_completed` but state never advances

Either:
- All candidate rows have `paused_reason IS NOT NULL` (operator
  paused them, or a circuit breaker tripped). Check the admin
  spec-runs view.
- The probe condition for the row's state isn't satisfied yet
  (e.g., DESIGNING with the architect still running). This is
  expected; the tick is observe-only until the probe matches.

## Related

- [provision-coder-core-worker.md](provision-coder-core-worker.md) —
  same shape for the spec 0056 worker Job.
- [secret-rotation-scheduler.md](secret-rotation-scheduler.md) —
  the canonical Cloud Scheduler → Job wiring template.
- coder-core [PR #113](https://github.com/coder-devx/coder-core/pull/113) —
  coordinator scaffold.
- coder-core [PR #122](https://github.com/coder-devx/coder-core/pull/122) —
  added the Job name to the image-sync loop.
- coder-core [PR #124](https://github.com/coder-devx/coder-core/pull/124) —
  remaining probes.
- coder-core [PR #125](https://github.com/coder-devx/coder-core/pull/125) —
  circuit breakers.
