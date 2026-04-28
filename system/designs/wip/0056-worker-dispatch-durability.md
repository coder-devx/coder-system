---
id: "0056"
title: Worker dispatch durability — move worker subprocesses out of the HTTP service
type: design
status: wip
owner: ro
created: 2026-04-28
updated: 2026-04-28
last_verified_at: 2026-04-28
implements_specs: ["0056"]
decided_by: []
related_designs:
  - worker-roles
  - worker-communication
  - architect-worker
  - team-manager-worker
  - pm-worker
  - self-healing
  - observability-and-cost-tracking
affects_services:
  - coder-core
affects_repos:
  - coder-core
---

# 0056 — Worker dispatch durability

## Context

See [spec 0056](../../product-specs/wip/0056-worker-dispatch-durability.md)
for the empirical signal that surfaced this. Short version: today's
worker dispatch path runs the role-specific worker subprocess
(`claude` CLI) as a child of the `coder-core` HTTP service instance
that handled the `POST /tasks` request. Cloud Run service-instance
eviction (idle scaling, revision rollouts, healthcheck flaps) kills
the parent and with it the asyncio task running `orchestrate_task`.
The Phase 3b terminal-status writeback at `dispatcher.py:1604–1654`
never lands. The task row stays at `status='running'` forever (until
the spec 0042 self-heal reaper fires — which today, post the
2026-04-28 fixes, marks it `TIMED_OUT/orchestrator_died` cleanly).

The reaper is a guardrail. It catches genuine crashes. Today's
empirical zombie rate (~100 % across wave-2 dispatches) means the
reaper has become the *primary* completion path — that's wrong.
Workers should reach terminal status by *completing*, not by being
reaped.

## Decision (provisional — sealing TBD)

**Move worker dispatch into a per-task Cloud Run Job execution.**
Spec option A. The HTTP service handler kicks the Job and returns
202; the Job runs the worker, writes terminal status, exits. Cloud
Run Jobs have the right lifecycle: one execution = one task,
container exits when work is done, billed per-second of actual run.

The pattern matches the existing operational tooling:

- `coder-core-self-heal-tick` (every-minute self-heal)
- `coder-core-auto-approve-tick` (every-minute auto-approve)
- `coder-core-rotate-secrets` (scheduled rotation)
- `coder-core-migrate` (one-shot migrations)

A new `coder-core-worker` Job slot fits this pattern. Operators
already know the shape (`gcloud run jobs executions list`, log
filters by `resource.labels.job_name`, etc.).

## Architecture

```mermaid
flowchart LR
    A[HTTP Client] -->|POST /v1/projects/{p}/tasks| B[coder-core service]
    B -->|create row<br/>status=queued| D[(coder-core-db)]
    B -->|kick Job execution<br/>TASK_ID env| C[Cloud Run Job<br/>coder-core-worker]
    B -->|202 Accepted| A
    C -->|status=running| D
    C -->|spawn claude subprocess| E[claude CLI]
    E -->|opens PR, pushes commits| F[GitHub]
    E -->|stdout JSON| C
    C -->|Phase 3b writeback<br/>status=succeeded/failed/timed_out| D
    C -->|exit| G[Cloud Run discards container]
    H[coder-core-self-heal-tick] -.guardrail only.-> D
```

The HTTP service:

1. Validates the request, applies multi-tenancy gates, creates the
   `tasks` row with `status='queued'`.
2. Calls Cloud Run Admin API:
   `projects.locations.jobs.run` with overrides
   `containerOverrides[0].env[].TASK_ID = <task_id>` and
   `containerOverrides[0].env[].PROJECT_ID = <project_id>`.
3. Returns 202 Accepted with the task ID. No fire-and-forget
   asyncio task on the service event loop.

The Cloud Run Job (`coder-core-worker`):

- Image: same `coder-core` image (`b47fdf5` etc.) — no new artifact
  to manage.
- Entry point: a new `coder_core.workers.entry` module that loads the
  task from `TASK_ID`, dispatches via the existing
  `dispatcher.dispatch_task`, and exits.
- Timeout: 60 min (Cloud Run Job hard cap is higher; we set 60 min
  to be safe above the worker's own 40 min budget).
- Max retries: 0 (idempotency lives at the row level — a re-run
  would re-do the work; we don't want that automatically).
- Service account: `coder-core-sa@vibedevx.iam` (same as the
  service today; no new IAM surface).

## Per-project fairness (concurrency cap)

The current per-process queue (`_dispatcher_queue.py`) provides
fairness within a single service instance. With Cloud Run Jobs each
task is an independent execution; the queue mechanism has to move.

Two options:

### Option F1 — DB-backed admission queue + a new admission tick

- The HTTP service inserts the row at `status='queued'`. **It does
  NOT immediately kick the Job.**
- A new Cloud Run Job `coder-core-admission-tick` (every 30 s, say)
  scans `status='queued'` rows, applies per-project fairness,
  promotes selected ones to `status='running'`, and kicks
  `coder-core-worker` Job executions for them.

Pros: fairness is centrally enforced and persistent. Survives any
service eviction.

Cons: 30 s admission latency for cold starts; one more component.

### Option F2 — Per-project Cloud Run Job with parallelism cap

- One `coder-core-worker-{project}` Job per project, with
  `parallelism = N` (the project's concurrent-task cap).
- Cloud Run Jobs natively respect the parallelism cap.

Pros: no extra service.

Cons: Cloud Run Jobs in v2 only support up to 10000 tasks per
execution but the *parallelism* knob applies to a single execution's
tasks, not across executions. We'd need to model "an execution per
project" and re-execute on dispatch. Awkward.

**Recommendation: F1.** A small admission tick is the cleaner long-term
shape and matches our other tick-based components. Short-term
admission latency is acceptable for tasks that take 5–30 min.

## Migration

### Phase 1 — Dual-mode (1–2 days)

- Ship the `coder-core-worker` Job + admission-tick + new entry
  module. **Keep the in-process subprocess path as default.**
- Add a per-project tri-state column `projects.worker_via_job_enabled`
  (NULL = fleet default off; TRUE = opt-in).
- Add fleet flag `CODER_WORKER_DISPATCH_VIA_JOB=false` (default).
- The dispatch endpoint reads both: if either is on for this
  project, go through the Job path; otherwise the legacy in-process
  path.

### Phase 2 — Soak on `coder` self (3–5 days)

- Flip `coder.worker_via_job_enabled = TRUE`.
- Watch:
  - `worker_zombie_rate{project=coder}` should drop to ~0
  - `worker_completion_p50/p95/p99` should be within 10 % of pre-change
  - Cost per worker-minute within ±20 %
- If green, proceed.

### Phase 3 — Fleet flip + decommission (1 day)

- Flip `CODER_WORKER_DISPATCH_VIA_JOB=true` fleet-wide.
- Watch for 1 week.
- Remove the in-process dispatch path, the per-process queue, the
  service-side asyncio fire-and-forget. Net deletion ~500 LOC.

## Acceptance criteria (mapped to spec ACs)

- **AC1 — Job exists & runs.** `gcloud run jobs describe
  coder-core-worker --region=europe-west1` returns a healthy job.
  Synthetic smoke test (a tiny dispatch through the Job path)
  succeeds end-to-end.
- **AC2 — Service stops spawning subprocesses.** `git grep
  asyncio.create_subprocess_exec` in `coder_core/workers/` shows
  zero matches in the dispatch path (only test fixtures retain it).
- **AC3 — 40-min worker reaches terminal status without reaper
  firing.** Synthetic test: a worker that intentionally sleeps 40
  min then writes a result. The row reaches `succeeded` without
  passing through `timed_out`.
- **AC4 — Reaper guardrail still works.** Synthetic: SIGKILL the
  Job mid-run; reaper marks the row `TIMED_OUT/orchestrator_died`
  within `zombie_executing_min_minutes` (45 min).
- **AC5 — Per-project fairness preserved.** Dispatch 4 tasks
  project A + 4 project B simultaneously; admission interleaves
  them so A doesn't monopolise the cap.
- **AC6 — Fan-out concurrency.** 50 tasks dispatched at once
  complete in ≤2× the largest single-task duration.
- **AC7 — Cost within 20 %.** Cost-per-worker-minute back-of-envelope
  shows ±20 %.

## Open questions

- Cold-start latency: do we need pre-warmed Job executions for
  user-visible-latency-sensitive tasks? Probably not — TM/dev tasks
  take 5–30 min; 5–10 s of cold start is noise.
- Admission tick cadence: 30 s vs 60 s. 30 s for snappier promotion;
  60 s aligns with self-heal-tick.
- Backpressure: when the admission tick can't keep up (huge dispatch
  burst), how do queued tasks signal lag? Probably reuse `stuck_queued`
  pattern with a higher threshold.

## References

- Spec 0028 — concurrent pipelines (per-process queue origin)
- Spec 0042 — self-heal reaper (zombie remediator)
- Spec 0011 — orphan reaper (precursor)
- Spec 0027 — transient retry (worker-side resilience)
- Cloud Run Jobs API:
  https://cloud.google.com/run/docs/create-jobs
  https://cloud.google.com/run/docs/execute/jobs
- coder-core PR #45 — zombie remediator terminal-mark fix
