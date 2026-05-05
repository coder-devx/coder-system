---
id: "0056"
title: Worker dispatch durability — move worker subprocesses out of the HTTP service
type: spec
status: wip
owner: ro
created: 2026-04-28
updated: 2026-05-05
last_verified_at: 2026-05-05
served_by_designs: ["0056"]
related_specs:
  - task-orchestration
  - developer-worker
  - architect-worker
  - team-manager-worker
  - reviewer-worker
  - pm-worker
  - continuous-deployment
  - observability
parent: pipeline-operations
---

# 0056 — Worker dispatch durability

## Problem

Today, every role worker (developer, architect, TM, PM, reviewer) runs
as an `asyncio.create_subprocess_exec` child of the `coder-core` Cloud
Run **service** instance that handled the `POST /v1/projects/{p}/tasks`
request. The HTTP request returns 201 immediately; orchestration runs
fire-and-forget as `asyncio.create_task(orchestrate_task(...))` on the
service instance's event loop. Cloud Run can — and does — terminate
service instances when:

1. Idle scaling sends them down (no active HTTP requests for ~15 min)
2. A new revision rolls out (graceful drain with a short grace period)
3. The instance fails healthchecks
4. Per-instance request concurrency drops to zero

When the parent dies, the worker subprocess is killed (POSIX child
inherits parent's lifetime) **and** the asyncio task running
`orchestrate_task` evaporates **before** `dispatcher.dispatch_task`
reaches Phase 3b (the terminal status writeback at
`dispatcher.py:1604–1654`). The task row is left at `status='running'`
with no live worker driving it forward. Side-effect work the worker
already performed (PR opened, commit pushed, branch created) is durable
in GitHub but the row state never reflects it.

### Empirical signal (2026-04-28 wave-2 dispatch session)

Across 5 successive waves of dispatches today, a consistent pattern
emerged:

| Wave | Dispatched | Reached terminal status w/ PR | Zombied |
|---|---|---|---|
| Wave-1 architects | 4 | 4 (one of which opened a PR despite schema-failing the validator) | 0 |
| Wave-1 TMs | 3 | 3 | 0 |
| Wave-2 v1 (initial fire) | 7 | 1 (0047 design — PR #21) | 5 |
| Wave-2 v2 (post-fix #1) | 7 | 1 (0046 fleet flag — PR #46, but at stage=testing) | 4 |
| Wave-2 v3 (post-fix #2) | 4 | 0 | 4 |
| Wave-2 v4–v5 (post-fix #3) | 5 | 0 | 5 |

The wave-1 cohort succeeded because instances were warm and load was
heavy enough to keep them alive for the duration. Wave-2 dispatched
into a colder cluster and hit eviction reliably.

### Three workarounds shipped today (2026-04-28)

These cover *symptoms* of the durability gap, not the cause:

1. **`coder-core` PR #45** — `zombie_executing` remediator now
   transactionally marks stuck rows `TIMED_OUT` (ADR 0011 +
   spec 0042 v1.1). Eliminates permanent-stuck rows.
2. **Runtime env-var flip** — the `coder-core-self-heal-tick` Cloud
   Run **Job** had `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE=dry_run`
   while the **service** had `apply`. Reaper detected zombies but
   wrote `dry_run` rows that filled the cap and never mutated. Fix:
   flip the JOB env var to `apply`.
3. **`zombie_executing_min_minutes` 25 → 45** — the reaper threshold
   was below the worker subprocess timeout
   (`coder_developer_task_timeout_seconds=2400 = 40 min`), prematurely
   killing live workers. Bumped to 45 min so workers get their full
   budget plus 5-min grace.

After all three fixes, **workers still zombie at 40+ min** because the
underlying durability gap is unaddressed. The reaper now produces clean
`TIMED_OUT/orchestrator_died` rows instead of permanent-stuck ones, but
the work is still lost.

## Goals

1. **Worker completion is durable.** A worker that produces output
   reliably persists its terminal status (`succeeded`/`failed`/
   `timed_out`) to the DB regardless of what happens to any other
   process.
2. **Workers can run for the full task budget** without Cloud Run
   service-side eviction killing them. 40 min today; longer when we
   raise per-task budgets.
3. **No additional fragile fan-out.** The fix should not introduce a
   new asyncio fire-and-forget pattern.
4. **Self-heal stays a guardrail, not a load-bearing recovery path.**
   The reaper exists for genuine crashes, not for routine completion.

## Non-goals

- Cross-instance fairness rework (still spec 0028's per-process queue
  scope; that's a separate WIP).
- Heartbeat-based zombie detection (the design §"Not yet shipped"
  variant of 0042; orthogonal).
- Worker prompt-caching changes (spec 0029 phase 2 unaffected).
- Worker model-routing rework (spec 0030 unaffected).

## Approach (sketch — design seals the choice)

Three plausible architectures, listed in order of likely ease and
ranked-by-our-current-best-guess:

### Option A — Worker per Cloud Run Job

Replace the in-process `asyncio.create_subprocess_exec` path with a
Cloud Run Job execution per task dispatch. The HTTP service POST
handler:

1. Creates the task row (`status='queued'`).
2. Calls `gcloud run jobs execute coder-core-worker-tick
   --update-env-vars=TASK_ID=<id>` (or the Cloud Run Admin API
   equivalent) — kicks the Job, returns immediately.
3. Returns 202 Accepted to the caller.

The new `coder-core-worker-tick` Cloud Run Job:

1. Reads `TASK_ID` from env.
2. Loads the task row, sets `status='running'` + `started_at`.
3. Runs the existing role-specific worker code (developer.py,
   architect.py, etc.).
4. On exit — success, failure, or worker-self-timeout — writes the
   terminal status to the DB (the existing Phase 3b code, lifted into
   the Job).

Pros: Cloud Run Job has the right lifecycle (one execution = one
task, exits when done, billed per-second for the actual run). No
asyncio fire-and-forget. The Job runs to completion regardless of
service scaling.

Cons: Each task-dispatch becomes one Cloud Run Job execution. Cost
implications need a back-of-envelope; given Job pricing is per-second
of actual run, should be ~comparable to the current model where the
service instance is alive during the worker run anyway. The
spawn-latency of a Cloud Run Job (cold start ~3–10 s) is the new
overhead — acceptable given the worker itself takes 5–30 min.

### Option B — Worker per HTTP request, synchronous

Keep workers in the service, but make orchestration synchronous within
the HTTP request that triggered it. Cloud Run keeps the request alive
up to 60 min. The dispatch endpoint blocks until orchestration
completes.

Pros: smallest code change.

Cons: 60-min cap is below some legitimate task chains (executing →
testing → fixing can chain past 60 min). Caller has to wait or
poll-and-retry through a streaming protocol. Re-implements what Cloud
Run Jobs already provide cleanly.

### Option C — Self-finalising worker

Keep the in-process subprocess but give the worker DB access. The
worker (or a thin wrapper around the `claude` CLI) writes the terminal
status to the DB directly before exiting. The parent's Phase 3b
becomes optional / idempotent.

Pros: minimal architectural change. Parent death no longer loses
state.

Cons: the worker subprocess is `claude` itself, which we don't
control. We'd need a wrapper script that captures the CLI's stdout
and writes to the DB. Adds DB credentials to the worker container,
which is a security boundary expansion.

### Recommendation

**Option A.** Cloud Run Jobs are the right primitive for batch work,
which is what role workers are. The pattern matches the existing
`coder-core-self-heal-tick`, `coder-core-auto-approve-tick`, and
`coder-core-rotate-secrets` jobs — operationally familiar.

The design (spec 0056-design) refines:

- Cloud Run Job spec (image, env, max-retries, parallelism, timeout)
- Dispatch path: the HTTP service's "kick" mechanism
- Concurrency: per-project caps (today's `_dispatcher_queue.py`
  becomes a DB-backed queue OR moves to a Cloud Run Jobs concurrency
  limit; design picks one)
- Migration: how the existing in-process path is retired (canary
  flag, dual-mode, or hard cut)
- Admin observability: how operators see Job executions per task

## Acceptance criteria

- **AC1** — A Cloud Run Job named (e.g.) `coder-core-worker-tick`
  exists and runs to completion for any role. The Job's image is the
  same `coder-core` image; the entry point is a new module that loads
  the task by ID, runs the role's worker, and writes terminal status.
- **AC2** — `POST /v1/projects/{p}/tasks` no longer spawns a
  subprocess in-process. It creates the row, kicks the Job, returns.
- **AC3** — A worker that runs for ≥40 min reaches a terminal status
  in the DB (succeeded / failed / timed_out) **without** the
  `zombie_executing` reaper firing.
- **AC4** — The `zombie_executing` reaper still functions as a
  guardrail. Synthetic test: kill a Job mid-run, verify the reaper
  marks the row TIMED_OUT within `zombie_executing_min_minutes`.
- **AC5** — The existing `_dispatcher_queue.py` per-project fairness
  is preserved (or replaced with an equivalent at the Job-spawn layer).
- **AC6** — A 50-task fan-out completes in ≤2× the largest single-task
  duration, demonstrating no serialisation regression.
- **AC7** — Cloud Run cost per worker-minute is within ±20 % of the
  pre-change cost (back-of-envelope; observability spec 0032's cost
  alerts cover the actual measurement).
- **AC8** *(2026-05-05 addition — gates Phase 3)* — Reviewer
  `orchestrator_died` rate over a 7-day window on a Job-mode-enabled
  project drops to ≤ 5%. Currently 50% on the Coder project despite
  `worker_via_job_enabled=TRUE`. Phase 3 fleet-default flip cannot
  proceed until this AC is met. Investigation owner: TBD.

## Rollout

Phase 1: dual-mode — in-process subprocess (default) and Cloud Run Job
(behind `CODER_WORKER_DISPATCH_VIA_JOB=true` per-project flag).
**Status: shipped 2026-04-28 (PRs #45–#50, coder-system PRs #28–#34).**

Phase 2: flip `coder` project to Job mode, soak for 1 week, watch
zombie rate drop to ~0.
**Status: opted in 2026-04-29; soak in progress.**

Phase 3: flip fleet default. Decommission in-process path.

### Issues surfaced + resolved during the start of Phase 2 soak (2026-04-29)

The original Phase 1 ship was inert (no project opted in yet), so two
latent issues only fired once `coder.worker_via_job_enabled = TRUE` and
real architect tasks ran via the new path. Both are addressed in
hotfix PRs landed the same day.

1. **Architect's hardcoded 900s timeout fires for the first time.**
   `src/coder_core/workers/architect.py` had `architect_timeout = 900`
   (15 min). The deadline never bit before because Cloud Run service
   eviction killed the worker subprocess earlier (this is the bug the
   spec fixes). With Job-mode workers durable, real architect runs
   exploring the codebase for sealed-spec design refinements
   (empirically 25–46 min on 0046/0048) hit the 900s deadline cleanly.
   Fixed by aligning architect with the other workers: reads
   `settings.coder_developer_task_timeout_seconds` (2400s = 40 min in
   prod), like `pm.py` / `team_manager.py` / `reviewer.py` /
   `developer.py`. **coder-core PR #51.**

2. **Runtime singletons not installed in the Job entry.**
   `coder_core.workers.entry._run_one` calls `dispatch_task` outside
   any FastAPI app, so the GH-token-provider, GH-client, and
   broker-client singletons that `main.create_app.lifespan` installs
   at service startup were never bootstrapped. `get_token_provider()`
   returned `None`, `apply_github_token_env` no-op'd, the worker
   subprocess got no `GH_TOKEN`, and `claude`'s `gh auth` / `git clone`
   calls failed (`"gh CLI is not authenticated"` / `"Source files not
   found"`). The legacy in-process path doesn't have this problem
   because the FastAPI lifespan had already installed the singletons.
   Fixed by adding `_install_runtime_singletons()` /
   `_teardown_runtime_singletons()` to `entry.py`, mirroring the
   lifespan wiring. **coder-core PR #52.**

These both explain why "Phase 1 was fully merged and deployed" yet the
architecture didn't *work* end-to-end until Phase 2 ramp surfaced
them — the assumption "if the path runs the same `dispatch_task`,
behaviour is identical" missed the implicit lifespan-side init that
the legacy path inherited from the FastAPI app. Worth recording so the
next system that inherits a "shared internal API runs in two
container types" pattern remembers to look for app-startup-time side
effects.

### 2026-05-05 — Phase 2 has NOT eliminated orphan deaths

Production data over the 7-day window ending 2026-05-05 shows the
durability gap is **wider than the pre-Phase-2 model suggested**:

| Role | Tasks | `orchestrator_died` | Death rate |
|---|---|---|---|
| reviewer | 18 | 9 | **50%** |
| developer | 27 | 3 | 11% |

**Every one of the 12 deaths is on the `coder` project — which has
`worker_via_job_enabled=TRUE`.** The other four projects (Broker
Test, Smoke, Archive smoke, VibeTrade) had no dispatches in the
window. So Phase 2 is in effect for every observed death; the Job
path is **not** preventing them.

Cost impact: ~$50/day in lost compute (turn-level, from `task_turns`
× Sonnet 4.x pricing). That's ~30% of total daily LLM spend across
all roles. The biggest single waste source in the system today,
ahead of the audit-dup bug ($1.50-6/day) and TM-rerun bug
(~$1.50/week).

#### Hypotheses (need investigation, none confirmed)

1. **Cloud Run Jobs themselves are not survivor-of-instance-churn.**
   Job executions can be evicted on the underlying compute the same
   way services can. If a Job execution is killed mid-run, the worker
   subprocess inside it dies with the same lost-progress signature
   as the legacy path. Worth measuring: do `failure_kind=orchestrator_died`
   rows for the Coder project correlate with Cloud Run Job execution
   failures (`gcloud run jobs executions list --filter='status.state!=Succeeded'`)?

2. **The kick fell back to the legacy path.** [tasks/service.py:251-266](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/tasks/service.py#L251)
   has a graceful fallback to `_schedule_in_process_dispatch` when
   `gcp_project_id` is unset or `kick_worker_job` errors. If a
   transient error causes silent fallback, the row is still created
   but routes through the broken legacy path. Verify by joining
   `tasks.failure_kind='orchestrator_died'` rows against logs for
   `dispatch_via_job.no_gcp_project` / `kick_worker_job` errors.

3. **Reviewer/dev loops exceed the Job task-timeout.** Settings says
   `coder_worker_job_task_timeout` (separate from the developer
   subprocess timeout). If a Cloud Run Job execution hits its
   `--task-timeout` ceiling, GCP terminates the container and the
   worker exits without a terminal status writeback — looks
   identical to orphan death from the DB's POV. Reviewer p95 latency
   was 12 min on observed reviews; if the Job task-timeout is below
   that, this is the primary cause.

4. **Long agentic loops trigger Job memory limits.** A 700-turn
   reviewer accumulates 17M cache_read tokens in working memory.
   If the Job container's memory ceiling is hit, GKE/Cloud Run kills
   it. Same DB-side signature.

#### Phase 3 cannot proceed until the death rate drops

The original Phase 3 plan was "flip fleet default" once Phase 2 soak
showed zombie rate dropping to ~0. Phase 2 soak instead shows the
zombie rate is **higher than expected** for the long-loop roles. The
fleet-flip is therefore **blocked** until the hypotheses above are
investigated and the actual mechanism is fixed.

This update treats spec 0056 as not-yet-shipped despite Phase 2
opt-in. Phase 3 is gated on a new acceptance criterion (AC8 below).

## Open questions

1. **Job concurrency model.** Cloud Run Jobs have a `parallelism`
   knob per execution. Do we run 1 per task (parallelism=1, simpler)
   or 1 Job with N parallel tasks (more efficient, requires sharding
   the queue)? The design seals this.
2. **Cold-start latency.** ~3–10 s per Job cold start. Tolerable for
   long workers; user-visible latency for short ones (TM tasks at 9
   min could feel ~10 % slower). Worth measuring; probably OK.
3. **Service account on the Job.** The current worker subprocess
   runs as the `coder-core` runtime SA. Job runs as the same SA.
   No new IAM surface.
4. **Per-project queue depth.** Today's in-memory queue
   (`_dispatcher_queue.py`) provides per-project fairness. With
   Cloud Run Jobs, each task is an independent execution — fairness
   has to move to either (a) a DB-backed queue with a separate
   admission tick, or (b) a per-project Cloud Run Job (multiple Jobs)
   with their own concurrency caps. Design picks one.

## References

- Today's session transcript at `…/0638afb8-…jsonl` documents the
  empirical run that surfaced this.
- coder-core PR #45 (zombie remediator)
- ADR 0011 (orphan reaper)
- spec 0042 (self-healing watchdog) — heartbeat-based zombie
  detection is the parallel work
- Cloud Run Jobs documentation:
  https://cloud.google.com/run/docs/create-jobs
