---
id: provision-coder-core-worker
title: Provision the coder-core-worker Cloud Run Job (spec 0056)
type: runbook
status: active
owner: ro
created: 2026-04-28
updated: 2026-04-28
last_verified_at: 2026-04-28
applies_to_services: [coder-core]
applies_to_integrations: [cloud-run-jobs]
---

# Provision the coder-core-worker Cloud Run Job

## When to run this

One-time bootstrap when rolling out spec 0056's Cloud Run Job
dispatch path. After the Job exists, the CI deploy workflow's
"Sync recurring job images" step keeps its image in sync with every
push to `main` automatically.

You should run this:

- Once per environment (currently only `vibedevx` / prod) before
  enabling Phase 2's per-project soak (`coder.worker_via_job_enabled = TRUE`)
- Again if the Job ever needs to be recreated (manual delete, env
  change requiring a new spec, etc.)

## Who can run this

Operator with `roles/run.admin` on the `vibedevx` project, or anyone
holding the `gha-deployer` SA's break-glass credential.

## Prerequisites

- `gcloud` authenticated for the target project
- The `coder-core` SERVICE is already deployed to the target region
  (we copy its env config; running this against an empty project
  would produce an unconfigured Job)
- The `coder-core` runtime service account
  (`coder-core-sa@vibedevx.iam.gserviceaccount.com`) exists and has
  the same IAM bindings as the live service (Cloud SQL Client,
  Secret Manager accessor, etc.)

## Background

Spec 0056 moves worker dispatch out of the in-process asyncio path
on the HTTP service into a per-task Cloud Run Job execution. The
`coder-core-worker` Job is the unit of execution: one Job execution
runs one task to completion, writes terminal status to the DB, and
exits. The HTTP service kicks executions via the Cloud Run Admin v2
`jobs.run` endpoint with `TASK_ID` injected per execution
(`coder_core.workers.job_kick`).

The Job's container image is the same as the service image; the
entry point overrides default to running `python -m
coder_core.workers.entry`.

Spec / design / runbooks:

- system/product-specs/wip/0056-worker-dispatch-durability.md
- system/designs/wip/0056-worker-dispatch-durability.md
- system/runbooks/zombie-task-recovery.md (the symptom this Job exists to fix)

## Steps

### 1. Capture the live service's env + secrets

The Job needs the same env as the service so the dispatcher can
reach the DB, GitHub, secret manager, model APIs, etc. Mirror via
`gcloud`:

```bash
PROJECT=vibedevx
REGION=europe-west1
SERVICE=coder-core
IMAGE=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" \
        --format='value(spec.template.spec.containers[0].image)')
RUNTIME_SA=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" \
        --format='value(spec.template.spec.serviceAccountName)')
CLOUD_SQL_INSTANCE=$(gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" \
        --format='value(metadata.annotations."run.googleapis.com/cloudsql-instances")')

# Dump env + secrets to a YAML file we'll re-apply to the Job
gcloud run services describe "$SERVICE" --project="$PROJECT" --region="$REGION" \
  --format=json \
  | jq '.spec.template.spec.containers[0] | {env, envFrom}' > /tmp/coder-core-env.json
```

Inspect `/tmp/coder-core-env.json`. The keys you care about are
`CLOUD_SQL_*`, `BROKER_SIGNING_KEY` (Secret Manager ref),
`ANTHROPIC_API_KEY` (Secret Manager ref), `GH_APP_*`, and the spec
0056 fleet flag `CODER_WORKER_DISPATCH_VIA_JOB` (don't include — the
Job itself doesn't need to know whether it was kicked).

### 2. Create the Job

```bash
gcloud run jobs create coder-core-worker \
  --project="$PROJECT" \
  --region="$REGION" \
  --image="$IMAGE" \
  --service-account="$RUNTIME_SA" \
  --set-cloudsql-instances="$CLOUD_SQL_INSTANCE" \
  --command=python \
  --args="-m,coder_core.workers.entry" \
  --max-retries=0 \
  --task-timeout=3600s \
  --cpu=2 \
  --memory=4Gi \
  --parallelism=1 \
  --tasks=1 \
  --set-env-vars="CLOUD_SQL_INSTANCE=$CLOUD_SQL_INSTANCE,CLOUD_SQL_USER=coder-core-sa@vibedevx.iam,CLOUD_SQL_DATABASE=coder_core" \
  --set-secrets="BROKER_SIGNING_KEY=broker-signing-key:latest,ANTHROPIC_API_KEY=anthropic-api-key:latest,GH_APP_PRIVATE_KEY=github-app-private-key:latest"
```

Then **mirror the rest of the service's env** by running through
`/tmp/coder-core-env.json` and adding any non-secret env vars the
service has set. The most important for the worker are:

- `GCP_PROJECT_ID=vibedevx`
- `GH_APP_ID=...`
- `GH_APP_INSTALLATION_ID=...`
- Any feature flags the dispatcher reads (`CODER_DEVELOPER_TASK_TIMEOUT_SECONDS=2400`, etc.)

Add them via `gcloud run jobs update coder-core-worker --update-env-vars=...`.

### 3. Smoke-test the Job

Pick a recently-completed task and run the Job against it. The Job
should re-execute the task. Since `dispatch_task` is idempotent
(it leases the row with `SELECT ... FOR UPDATE SKIP LOCKED` and
short-circuits if the row isn't `queued`), a re-run on a completed
task is a clean no-op:

```bash
TASK_ID="<some recently-succeeded task id>"
gcloud run jobs execute coder-core-worker \
  --project="$PROJECT" --region="$REGION" \
  --update-env-vars="TASK_ID=$TASK_ID" \
  --wait
```

Look at the execution's logs:

```bash
gcloud run jobs executions list --project="$PROJECT" --region="$REGION" \
  --job=coder-core-worker --limit=5
gcloud beta run jobs executions logs read <execution-name> \
  --project="$PROJECT" --region="$REGION"
```

Expected output near the bottom:

```json
{
  "task_id": "...",
  "outcome": "completed",
  "elapsed_seconds": 0.3,
  "error": null,
  "final_status": "succeeded",
  "final_stage": "accepted",
  "pr_url": "https://github.com/..."
}
```

### 4. Verify CI image-sync picks the Job up on next push

Push a no-op commit (or wait for the next merge) and watch the
`Sync recurring job images` step in CI. It should now log a Cloud
Run update for `coder-core-worker` (no longer "skipping").

### 5. Grant the runtime SA Cloud Run Jobs invoker permission

The HTTP service kicks the Job via the Cloud Run Admin v2 API. The
service's runtime SA needs IAM permission to invoke the Job:

```bash
gcloud run jobs add-iam-policy-binding coder-core-worker \
  --project="$PROJECT" --region="$REGION" \
  --member="serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com" \
  --role="roles/run.invoker"

gcloud projects add-iam-policy-binding "$PROJECT" \
  --member="serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com" \
  --role="roles/run.developer"
```

`run.invoker` on the Job lets the SA call `jobs.run`.
`run.developer` at the project level lets the SA observe + start
Job executions via the Admin API. (If your security posture
requires tighter scoping, replace `run.developer` with a custom
role that only grants `run.executions.run` on this specific Job.)

## Success condition

- `gcloud run jobs describe coder-core-worker` returns a healthy
  spec
- A smoke-test execution returns `{"outcome": "completed"}` with
  `elapsed_seconds < 60` (idempotent no-op on an already-finished
  task)
- The CI `Sync recurring job images` step updates the Job image on
  push to `main`
- The runtime SA has `run.invoker` on the Job

## If something goes wrong

### "PERMISSION_DENIED" on `jobs.run` calls from the service

The runtime SA is missing `run.invoker` on the Job. Re-run the
binding command in step 5.

### Job execution exits with `outcome: missing_task_id`

The CI sync step doesn't set `TASK_ID` (correctly — that's
per-execution). When kicking from the service, `kick_worker_job`
injects `TASK_ID` via `containerOverrides[0].env`. If you see this
during a kicked execution, the override didn't reach the container —
inspect the execution spec under `gcloud run jobs executions describe`
and confirm the env override is present.

### Job execution times out at `task-timeout`

3600 s / 60 min is set above to give a comfortable margin over the
40-min worker timeout. If a task legitimately needs longer, raise
this. If a task is hanging, the spec 0042 reaper will mark the
**row** TIMED_OUT regardless of the Cloud Run execution state at
`zombie_executing_min_minutes` (45 min as of 2026-04-28).

## Related

- system/runbooks/zombie-task-recovery.md
- system/runbooks/dispatching-developer-tasks.md
- coder-core PR #48 (Phase 1ab — entry module + flags)
- coder-core PR #49 (Phase 1c — wire HTTP dispatch)
