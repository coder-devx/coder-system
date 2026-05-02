---
id: knowledge-freshness-audit
title: Knowledge freshness audit — setup + weekly triage
type: runbook
status: active
owner: ro
created: 2026-04-17
updated: 2026-05-01
last_verified_at: 2026-05-01
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: []
---

# Knowledge freshness audit

Two things in one runbook:

1. **Setup** — how to wire Cloud Scheduler to the nightly audit
   endpoint once per GCP project.
2. **Weekly triage** — the operational pass over the queue the
   nightly pass produces.

See
[knowledge-freshness](../product-specs/active/knowledge-freshness.md)
for the product view and the
[design](../designs/active/knowledge-freshness.md) for the technical
one; ADR
[0014](../adrs/0014-freshness-from-declared-affects.md) pins the
"declared affects, not semantic similarity" constraint.

## Setup — Cloud Run Job + Cloud Scheduler

The nightly audit runs as a **Cloud Run Job** that calls
[`coder_core.ops.knowledge_audit_tick._cli`](../../../coder-core/src/coder_core/ops/knowledge_audit_tick.py),
triggered nightly by a Cloud Scheduler entry. This mirrors the existing
tick jobs (`coder-core-auto-approve-tick`,
`coder-core-self-heal-tick`).

> **Why a Job, not an HTTP scheduler hit?** The
> `POST /v1/_admin/knowledge-audit/run` endpoint requires an admin JWT
> signed with our `broker_signing_key`. Cloud Scheduler can mint OIDC
> tokens but not our admin JWT; the Job-based pattern avoids that auth
> hop by talking directly to the database. The HTTP endpoint stays
> available for operators (admin-JWT bearer) and the **Run audit**
> button on the admin Freshness tab — the Job is just the scheduled
> path.

### One-time provisioning (per GCP project)

```sh
# Prereq: a coder-core image is already pushed to Artifact Registry.
# Use the latest service image; CI's "Sync recurring job images" step
# (see .github/workflows/ci.yml) keeps this in sync on every deploy.
IMAGE="$(gcloud run services describe coder-core \
  --project=vibedevx --region=europe-west1 \
  --format='value(spec.template.spec.containers[0].image)')"

# 1. Create the Cloud Run Job. Same SA + Cloud SQL + secrets as the
#    other tick jobs so the audit can read projects + dispatch tasks.
#    The values below match what coder-core-auto-approve-tick uses
#    today (instance, secret names, env vars). If you change one,
#    change them all together so the prod fleet stays consistent.
gcloud run jobs create coder-core-knowledge-audit-tick \
  --project=vibedevx \
  --region=europe-west1 \
  --image="${IMAGE}" \
  --service-account=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --execution-environment=gen2 \
  --set-cloudsql-instances=vibedevx:europe-west1:coder-core-db \
  --set-env-vars=ENVIRONMENT=prod,CLOUD_SQL_INSTANCE=vibedevx:europe-west1:coder-core-db,CLOUD_SQL_USER=coder-core-sa@vibedevx.iam,CLOUD_SQL_DATABASE=coder_core,GCP_PROJECT_ID=vibedevx,GITHUB_APP_ID=3325027 \
  --set-secrets=GITHUB_APP_PRIVATE_KEY=coder-github-app-private-key:latest,BROKER_SIGNING_KEY=coder-core-broker-signing-key:latest \
  --command=python \
  --args=-m,coder_core.ops.knowledge_audit_tick \
  --max-retries=0 \
  --task-timeout=900s \
  --cpu=1000m \
  --memory=512Mi

# 2. Wire Cloud Scheduler to invoke the Job nightly. 03:00 UTC keeps
#    the audit clear of the auto-approve + self-heal ticks that fire
#    every minute and the rotate-secrets job that fires every 15.
gcloud scheduler jobs create http knowledge-audit-nightly \
  --project=vibedevx \
  --location=europe-west1 \
  --schedule="0 3 * * *" \
  --time-zone="UTC" \
  --http-method=POST \
  --uri="https://europe-west1-run.googleapis.com/apis/run.googleapis.com/v1/namespaces/vibedevx/jobs/coder-core-knowledge-audit-tick:run" \
  --oauth-service-account-email=coder-core-sa@vibedevx.iam.gserviceaccount.com \
  --oauth-token-scope=https://www.googleapis.com/auth/cloud-platform
```

- **Schedule:** 03:00 UTC. Picked to keep the audit clear of the
  per-minute ticks and the `*/15` rotation job; the Job can run for
  several minutes when the fleet has many projects.
- **Floor / limit:** `DEFAULT_FLOOR=40` and `DEFAULT_LIMIT=5` are
  baked into `coder_core.ops.knowledge_audit.run_once`. Per-project
  overrides still go through the admin endpoint (or the **Run audit**
  button on the admin Freshness tab) — the scheduled job is the
  fleet-wide default-floor pass.
- **Manual verification:** `gcloud scheduler jobs run
  knowledge-audit-nightly --location=europe-west1 --project=vibedevx`
  triggers the Job immediately. The admin Freshness tab shows the
  new run row within a minute, and `gcloud run jobs executions list
  --job=coder-core-knowledge-audit-tick --region=europe-west1` shows
  the underlying execution.
- **One-off operator pass:** the admin Freshness tab's **Run audit**
  button (`POST /v1/_admin/knowledge-audit/run` with admin JWT) is
  still the ergonomic path for "I want to see what's stale right
  now"; no Job invocation needed.

## When to run this

- Once per week — Monday is the default cadence; stays paired with
  the weekly metrics review so the fleet freshness trend can be
  read off the same dashboard.
- Out-of-cadence if the **Needs attention** widget crosses its
  per-project threshold (default 20 open reports).
- Out-of-cadence after a major refactor lands — a deliberate burst
  of `needs_rewrite` reports is expected and triaging them fast
  keeps the repo honest.

## Who can run this

Operator (human) with admin JWT. The Architect worker has already
produced a verdict; this pass decides what to do with it. The PM
worker is the usual next step when a rewrite is needed.

## What the queue contains

The nightly audit dispatches one `knowledge-audit` task per stale
artifact (top 5 per project, below the staleness floor — see the
design for the score model). Each task produces one of three
outcomes:

| Architect decision | What it means | What ends up in the queue |
|---|---|---|
| `verified` | Artifact still matches reality. Call `.../verify` bumps `last_verified_at`. | Nothing — the task closes silently. |
| `needs_rewrite` | Architect identified specific gaps between the artifact and the code. | A report with `gaps: [...]`. |
| `uncertain` | Architect flagged questions a human must answer. | A report with `questions: [...]`. |

Reports are surfaced at **Admin → Freshness** (Needs attention
table) and via
`GET /v1/_admin/knowledge-audit/runs/{run_id}` which returns every
`knowledge_audit_items` row for a pass (including the architect's
`decision` + canonical-JSON `report` once the task completes).
`GET /v1/_admin/ops/freshness` gives the score histogram + oldest-N
across the latest run per project without listing individual runs.

## Triage

Work through the queue **most-recent first**. A fresh rewrite report
is almost always cheaper to action than a month-old one — the
operator's context from adjacent work is usually still warm.

For each report:

1. **Open the report in the admin panel.** Shows the artifact, the
   score at audit time, the Architect's reasoning, and either
   `gaps[]` or `questions[]`.
2. **Sanity-check the Architect's reading.** Spot-check by opening
   the artifact in one tab and the referenced `affects_*` code in
   another. The Architect is rarely wrong here — the declared
   targets are the signal — but a sanity read catches the case
   where a recent commit changed a filename without changing
   behaviour.
3. **Classify the report.** Four outcomes:

### Outcome A — Verified by operator (false positive)

The audit flagged rot that turns out to be a wording nit or a
reorganised section that still describes current reality.

- Click **Verify** in the report view. This calls
  `POST .../verify` with a short `summary` ("false-positive audit;
  code matches section X") and closes the report.
- If many reports trend this way for a given artifact, the weights
  need calibration — note in the weekly metrics write-up.

### Outcome B — Small, self-contained fix

The gap is a single paragraph, a renamed path, or an out-of-date
metric name. Operator can write the patch themselves.

- Use `PUT /v1/projects/{id}/knowledge/{type}/{id}` via the admin
  inline editor (or `gh` CLI from a checkout). Include
  `verified_by: <operator-slug>` in the body — this also resets
  `last_verified_at` in the same commit and closes the report.
- Do **not** batch multiple artifacts into one commit; the
  freshness system scores per artifact and wants per-artifact
  provenance.

### Outcome C — Substantive rewrite → open a WIP

The gap is large enough to warrant a planned change: a new section,
a diagram update, a reworked invariants list, or a full rewrite of
the artifact.

- Hand the report to the PM worker with the
  `open_wip_from_audit` task kind. Prompt includes the artifact, the
  gaps, and the existing roadmap phase — PM proposes a numbered WIP
  that will later ship via the write-through ship gate
  ([ship-wip-into-active](./ship-wip-into-active.md)) and merge back
  into `active/`.
- Until the WIP ships, the artifact keeps its low score. That's
  correct: the rot is real, and "a WIP exists" is not the same as
  "the repo is current".

### Outcome D — Uncertain requires subject-matter decision

The Architect couldn't decide because the answer lives in an
unwritten decision (e.g. "did we ever finalise X?").

- Escalate to the subject-matter owner via the pipeline-owner
  Slack channel. Attach the report link.
- Once answered, loop the answer back as either an Outcome B (small
  fix) or C (substantive rewrite).

Each triaged report should leave the queue within the week. A
report that can't be triaged in a week becomes its own signal —
most commonly "we haven't decided what this artifact should say" —
and should be escalated rather than left to rot the queue.

## Success condition

- `knowledge_audit_items.decision IN ('needs_rewrite', 'uncertain')`
  open count returns to zero for the project by end-of-week.
- Median `knowledge_freshness_score` gauge (fleet view on
  `GET /v1/_admin/ops/freshness/metrics`) is flat-or-rising
  week-over-week.
- `knowledge_stale_reads_total` / total typed reads is under 20% for
  every project (if over, the threshold is too tight or the audit
  cadence is too slow).

## If something goes wrong

- **The queue keeps growing.** Five artifacts per night per project
  is the per-project audit cap; if churn is higher, the audit can't
  keep up. First, raise the per-project cap temporarily via the
  trigger payload (`{"project_id": "acme", "limit": 20}`) to clear
  the backlog. If the cap has to stay high, that's a signal to
  rebuild the artifact or raise `min_freshness` on the callers
  reading it — the underlying repo area is in flux.
- **Architect keeps returning `uncertain` on the same artifact.**
  Either the artifact needs a *decision* (escalate once, don't keep
  looping), or the Architect prompt doesn't have enough context;
  bump the `knowledge-audit` task template's context window or
  include ADRs in the prompt and re-run.
- **Many reports with identical wording.** A recent
  taxonomy-level change (e.g. metric rename, service rename) is
  showing up as N reports. Batch them: one Outcome B commit per
  affected artifact, referencing the same commit message; close in
  one sitting.
- **`verify` 409 conflict.** Someone edited the artifact between
  your read and your attestation. Re-fetch, re-verify, try again.

## Related

- Spec: [knowledge-freshness](../product-specs/active/knowledge-freshness.md)
- Design: [knowledge-freshness](../designs/active/knowledge-freshness.md)
- ADRs: [0014 — freshness from declared affects](../adrs/0014-freshness-from-declared-affects.md),
  [0008 — CI validation of the knowledge repo](../adrs/0008-ci-validation-of-knowledge-repo.md)
  (validator enforces `last_verified_at`).
- Adjacent: [ship-wip-into-active](./ship-wip-into-active.md) —
  Outcome C's WIP eventually returns here.
