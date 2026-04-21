---
id: auto-approve-rollout
title: Auto-approval — infra wiring + staged flag rollout
type: runbook
status: active
owner: ro
created: 2026-04-21
updated: 2026-04-21
last_verified_at: 2026-04-21
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [gcp]
---

# Auto-approval rollout

The auto-approval code (evaluator, pending/applied/undone state
machine, tick, accept-now + undo endpoints, admin UI) is deployed and
flag-gated on `AUTO_APPROVE_ENABLED` / `VITE_AUTO_APPROVE_ENABLED`.
This runbook covers the infra wiring (one-time) and the staged flag
rollout (multi-day — don't skip stages).

Product view: [0040 spec](../product-specs/wip/0040-confidence-auto-approve.md).
Design: [0040 design](../designs/wip/0040-confidence-auto-approve.md).
Same Cloud Run Job + Scheduler shape as
[secret-rotation-scheduler](./secret-rotation-scheduler.md); copy the
`gcloud` commands below rather than hand-translating from 0038's.

## What's wired on prod today (as of 2026-04-21)

- Cloud Run **Job** `coder-core-auto-approve-tick` (europe-west1) runs
  `python -m coder_core.approvals.tick` in the `coder-core` image.
- Cloud Scheduler job `coder-core-auto-approve-tick` (europe-west1,
  `* * * * *` UTC — every minute) triggers the Job via the Cloud Run
  Admin API, OAuth as `coder-core-sa`.
- `AUTO_APPROVE_ENABLED` is still **`false`** on both service and Job
  — every tick exits with `skipped: "disabled"`, as intended.
- Zero per-project opt-ins. `projects.auto_approve_spec_enabled` /
  `_design_enabled` / `_plan_enabled` all `NULL` across the fleet;
  even if the fleet flag flipped, no gate would evaluate until
  opt-in.

## When to run this

- Infra wiring (steps 1–3) is already done for `vibedevx`. Replay is
  for disaster recovery or for a fresh GCP project.
- Stage 1 → 2 → 3 rollout (steps 4+) runs when the product decision
  is taken to start earning auto-approvals on `coder` (canary) and
  then expanding.

## Who can run this

Operator with the same grants as
[secret-rotation-scheduler](./secret-rotation-scheduler.md) — plus
`run.admin` to update the service env for flag flips. Stage progression
is a **product decision**, not an SRE one; the approval for each stage
sits with the project owner.

## Prerequisites

- `coder-core` service running and reachable.
- Migrations 0044 (`auto_approvals`) and 0045
  (`projects.auto_approve_*_enabled` columns) applied. Check with:
  ```sh
  curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
    https://coder-core-<hash>.a.run.app/v1/projects/coder \
    | jq '{auto_approve_spec_enabled, auto_approve_design_enabled, auto_approve_plan_enabled}'
  # All three should be present (null values are fine; absence means
  # migration didn't land).
  ```
- `AUTO_APPROVE_ENABLED` unset (or `false`) on service + Job. Flip
  last, after the Job + Scheduler are verified.

## Steps

### 1. Create the Cloud Run Job

```sh
IMAGE=$(gcloud run services describe coder-core \
  --project=vibedevx --region=europe-west1 \
  --format='value(spec.template.spec.containers[0].image)')

gcloud run jobs create coder-core-auto-approve-tick \
  --project=vibedevx \
  --region=europe-west1 \
  --image="$IMAGE" \
  --service-account=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --set-cloudsql-instances=vibedevx:europe-west1:coder-core-db \
  --set-env-vars=ENVIRONMENT=prod,CLOUD_SQL_INSTANCE=vibedevx:europe-west1:coder-core-db,CLOUD_SQL_USER=coder-core-sa@vibedevx.iam,CLOUD_SQL_DATABASE=coder_core,GCP_PROJECT_ID=vibedevx,GITHUB_APP_ID=3325027 \
  --set-secrets=ANTHROPIC_API_KEY=ANTHROPIC_API_KEY:latest,GITHUB_APP_PRIVATE_KEY=coder-github-app-private-key:latest,BROKER_SIGNING_KEY=coder-core-broker-signing-key:latest \
  --command=python \
  --args=-m,coder_core.approvals.tick \
  --task-timeout=5m \
  --max-retries=0
```

### 2. Smoke-test the Job with the flag still off

```sh
gcloud run jobs execute coder-core-auto-approve-tick \
  --project=vibedevx --region=europe-west1 --wait
```

Logs should show `"skipped": "disabled"` then `Container called exit(0)`.
If the container errors here, don't touch the scheduler — fix the
container first.

### 3. Wire Cloud Scheduler → Job

```sh
# The `coder-core-sa` → `roles/run.invoker` binding is already in
# place from the secret-rotation rollout (see secret-rotation-scheduler
# runbook). Re-applying is a no-op.
gcloud projects add-iam-policy-binding vibedevx \
  --member=serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --role=roles/run.invoker --condition=None

gcloud scheduler jobs create http coder-core-auto-approve-tick \
  --project=vibedevx \
  --location=europe-west1 \
  --schedule="* * * * *" \
  --time-zone="UTC" \
  --http-method=POST \
  --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/vibedevx/jobs/coder-core-auto-approve-tick:run" \
  --oauth-service-account-email=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform"
```

1-minute tick matches the spec's "A 1-minute Cloud Scheduler tick
finalises expired pending rows." Wait one minute, then:

```sh
gcloud run jobs executions list \
  --project=vibedevx --region=europe-west1 \
  --job=coder-core-auto-approve-tick --limit=3
```

The latest execution should be from the scheduler, `Completed`, with
logs showing `"skipped": "disabled"`.

### 4. Stage 1 — schema-only shadow (no flag, no opt-in)

Pick a window — **one pipeline cycle minimum** — where you watch:

- Every PM/Architect/TM worker output includes `self_confidence` per
  its output schema (0025). Missing = a `failure_kind="schema"` task,
  not an auto-approval. Tail the metrics page's prompt-version table;
  every worker role should have a single current version with ≥ 20
  tasks and a success rate within 1 pp of pre-0040 baseline.
- The tick runs every minute with `skipped: "disabled"` — sanity on
  the infra not going dark after the 0040 image deploys. Pin the
  admin panel's Fleet queue widget alongside.

A red flag here is a spike in `failure_kind="schema"` that wasn't
present before. That means 0040's schema-bump to add `self_confidence`
broke a worker. Roll back the image (`gcloud run services update-traffic
--to-revisions=<previous-revision>=100`) and fix the schema drift
before progressing.

### 5. Stage 2 — evaluator runs shadow, no publish

Flip on the fleet flag (still no per-project opt-in):

```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=AUTO_APPROVE_ENABLED=true

gcloud run jobs update coder-core-auto-approve-tick \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=AUTO_APPROVE_ENABLED=true \
  --image="$IMAGE"
```

Without per-project opt-in, every evaluation lands `Manual(reason)` —
no `auto_approvals` rows get created, no SSE events fire, nothing
changes for operators. What you gain: structured evaluator output
in the logs for every gate evaluation, with the reason (confidence
below threshold, no opt-in, insufficient history, etc.). Run this for
**at least 72 hours** — long enough for every gate kind (spec,
design, plan) to have ≥ 20 evaluator outputs. Look at the distribution
of `worker_score` across roles; compare against the thresholds in the
spec (85/90/80). If a role's scores cluster far below its threshold,
that role isn't ready — leave it at `false` when you opt projects in
at stage 3.

### 6. Stage 3 — per-gate opt-in, one gate at a time

Pick one project (recommend `coder` as canary) and one gate (spec is
typically first — lowest blast radius). Opt in via the project PATCH:

```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"auto_approve_spec_enabled": true}' \
  https://coder-core-<hash>.a.run.app/v1/projects/coder
```

Now the evaluator can return `EligibleForAuto(window_seconds=600)` for
`coder`'s spec gates. On eligibility:

1. A row lands in `auto_approvals` with `status='pending'`.
2. SSE `auto_approval_pending` fires; the admin panel shows a
   countdown card.
3. The 1-minute tick finalises after 10 minutes (`window_expires_at <
   now()`): transitions to `applied`, writes audit, publishes
   `knowledge_approved`, runs chain hook.
4. An operator can click **Accept now** to skip the wait or **Undo**
   to revert — both within the 10-minute window.

**Watch for a week:**

- Auto-approve rate — the spec's primary metric. Non-zero means the
  machinery works; zero means the threshold filtered everything out
  (score too stringent? history < 5? check the evaluator reasons).
- Undo rate — if humans are regularly clicking undo, the threshold
  is too low. Spec's target is < 5% fleet-wide; a sustained > 10% is
  a rollback signal. Undo spawns a revision task, so the human's
  action also appears in the pipeline.
- Developer-task success rate on chains that started from
  auto-approved spec vs manually-approved spec. A > 3pp drop in the
  auto bucket is a rollback signal.

After a week of steady metrics, flip the next gate (`_design_enabled`,
then `_plan_enabled`). Then the next project.

**Rollback at any stage:**

```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=AUTO_APPROVE_ENABLED=false

gcloud run jobs update coder-core-auto-approve-tick \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=AUTO_APPROVE_ENABLED=false \
  --image="$IMAGE"
```

Flag off → no new evaluations; existing `pending` rows still finalise
(by design, to avoid stuck state) but no new ones are created. Opt-in
rows in `projects` stay set; clearing them requires a PATCH with
`null`/`false`. Per-project opt-out (`_enabled=false`) beats the fleet
flag if both are on.

## Success condition

- Cloud Run Job `coder-core-auto-approve-tick` exists with the
  expected image/SA/entrypoint.
- Cloud Scheduler job `coder-core-auto-approve-tick` is `ENABLED` with
  `* * * * *` schedule and a recent `lastAttemptTime`.
- During Stages 1–2: every tick exits with `skipped: "disabled"` (or
  after flag flip, `null` + `finalized: []`). No executions go red.
- During Stage 3: `auto_approvals` table has `applied` rows; audit
  log has `auto_approval.applied` (and sometimes `.undone`) entries;
  admin panel shows recent auto-approvals and their undo countdowns.

## If something goes wrong

- **Tick executions started going red** — check logs first; a
  per-row failure is captured in the `errored` array and usually
  traces to a specific pipeline run. Fix the data (e.g. a
  hand-intervened pipeline_run in a bad state) and the next tick
  picks it up. A systemic failure (every tick red) warrants a
  rollback of the fleet flag.
- **Flag flipped but tick still says `skipped: "disabled"`** — env
  var name gotcha. pydantic-settings has no prefix, so it's
  `AUTO_APPROVE_ENABLED` — not `CODER_AUTO_APPROVE_ENABLED`. Check:
  `gcloud run jobs describe coder-core-auto-approve-tick ... | grep AUTO_APPROVE`.
- **Human clicked Undo but the chain already dispatched** —
  shouldn't happen: `knowledge_approved` and chain dispatch are
  withheld until the window closes. If it does, it's an ordering bug
  in the tick — file one.
- **Undo rate spikes during canary** — halt the ramp. The threshold
  for that gate is too low. Leave the project's opt-in on; options:
  (a) push the per-gate threshold in the evaluator config higher and
  redeploy, (b) revoke the opt-in for that one gate on that one
  project until the fix ships.

## Related

- Runbook:
  [secret-rotation-scheduler](./secret-rotation-scheduler.md) — same
  Cloud Run Job + Scheduler pattern; copy the shape, not the
  secrets.
- ROADMAP entry: Phase 7 / 0040.
- AGENTS.md rule 5 — this runbook moves into `active/` alongside a
  spec + design fold after 0040 has soaked through Stage 3 for at
  least a month.
