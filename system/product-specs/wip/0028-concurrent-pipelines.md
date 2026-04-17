---
id: "0028"
title: Concurrent pipeline execution with per-project fairness
type: spec
status: wip
owner: ro
created: 2026-04-17
updated: 2026-04-17
served_by_designs: ["0028"]
related_specs: [developer-worker, task-orchestration, observability]
---

# Concurrent pipeline execution with per-project fairness

## Problem

Today every task dispatches immediately into its own `asyncio.create_task`
coroutine. One Cloud Run instance cheerfully spawns 20+ `claude`
subprocesses when a TM approves a fan-out plan — memory blows up,
Anthropic rate-limits return at the API boundary, and downstream
observability rolls all the noise into one noisy window.

**What's already live (v0 global cap).** A process-wide
`asyncio.Semaphore` bounded by `worker_concurrency` (default 4)
gates `orchestrate_task`. Admin has
`GET /v1/projects/{id}/ops/concurrency` exposing `{cap, in_flight, available}`.
That's the minimum-safe slice: a single instance can't dispatch 100
concurrent subprocesses.

**What's missing (this spec).** The global cap is fleet-level — a
single busy project can hold every slot and starve every other
tenant. Multi-tenancy (ADR 0005) promises per-project isolation;
the dispatch layer currently doesn't honour it. And queue depth is
opaque: the concurrency gauge shows how many are running, not how
many are waiting, per project or globally.

Two failure modes we've observed since the global cap shipped:

- Project A approves a 30-task plan. Projects B and C's tasks
  submitted in the same minute sit waiting 5+ minutes until A
  drains.
- An operator notices a pipeline stalled; no visible way to tell
  whether the task is "running slow" or "queued behind N others"
  without tailing logs.

## Users / personas

- **Operator watching the admin panel** — needs a visible queue
  depth per project, not just per-instance concurrency.
- **Managed-project owner** — expects their pipeline to make
  progress regardless of what another project is doing on the same
  Cloud Run instance.
- **SRE on-call** — needs a per-project queue-depth alert when a
  single project dominates the fleet for too long.
- **Future autoscaler (0041/0042 territory)** — will need queue
  depth as a scaling signal. Shipping it here now unblocks that.

## Goals

- Preserve the global cap (already shipped). No behavioural change
  when only one project is active.
- Enforce **per-project fair scheduling**: when tasks from multiple
  projects are queued, slots rotate by project rather than arrival
  order so no single project can monopolise the cap.
- Expose **queue depth** per-role and per-project via an
  observability endpoint + gauge, not just the process-wide
  in-flight count.
- Per-project lease quotas are **soft** by default — a single
  project can use all N slots when no one else is waiting. The
  fairness kicks in as contention signal, not as a hard ceiling.
- Runbook for the operator: what queue-depth growth means, when to
  widen the cap vs when to shed load.

## Non-goals

- **Multi-instance coordination.** The cap + fairness are
  per-process. Two Cloud Run instances each running 4 tasks yields
  8 concurrent subprocesses fleet-wide. We'll coordinate across
  instances when Cloud Run scale-out becomes a real concern; for
  now min-instances=1 matches the operational shape.
- **Priority queues or SLA-aware scheduling.** Fairness is strict
  round-robin by project; no tenant is "more important" than another.
- **Rate limiting at the HTTP boundary.** The task-create endpoint
  stays non-blocking. Backpressure surfaces via queue depth, not
  via 429s to clients.
- **Replacing the current global cap.** The semaphore stays; fair
  scheduling is a layer that chooses *who enters* when contention
  exists.

## Scope

**In:**

- A per-project queue ordering layer in front of the process-wide
  semaphore. When multiple tasks are waiting, the dispatcher
  selects the next project round-robin over those with queued
  work. A project with no waiters yields its slot to the next.
- Queue-depth tracking per `(project_id, role)`. Updated on enqueue
  and dequeue; exposed via `GET /v1/projects/{id}/ops/queue-depth`
  and aggregated fleet-wide at `GET /v1/ops/queue-depth` (admin-only).
- Observability: structured log events
  `dispatcher_queue.{enqueued,dequeued,starved_yield}` with
  `{project_id, role, queue_depth}`. Emits on every state change.
- A per-project concurrency knob (`projects.worker_concurrency_soft`,
  nullable; NULL means "share the global cap"). When set, the
  project yields its slot once it has used its soft cap and
  someone else is waiting. Used by projects that explicitly want
  to be bounded even on an idle fleet.
- Admin panel — a "Queue" strip on each project dashboard showing
  depth per role and a global "Fleet queue" widget for the
  admin home.
- Runbook `runbooks/concurrency-overflow.md` — operator decision
  tree when queue depth climbs above target.

**Out:**

- A second-level scheduler that considers task complexity,
  historical latency, or PM priority.
- Dynamic `worker_concurrency` scaling based on observed CPU /
  memory. The cap is deployment-time config.
- Cross-project prioritisation or quotas beyond the soft knob.
- Rate-limiting the task API based on queue depth.

## Acceptance criteria

- [ ] `coder_core.workers.orchestrator` gains a per-project
      fairness layer in front of the global semaphore. With N
      projects contending, no single project holds >⌈cap/N⌉ of the
      slots for longer than one completed-task cycle.
- [ ] A new `DispatcherQueue` module (or equivalent) owns the
      per-project round-robin and exposes:
      - `enqueue(project_id, role)` called when
        `orchestrate_task` enters the waiting state.
      - `dequeue() -> (project_id, role)` called when a slot frees.
      - `depth(project_id=None, role=None) -> int` for the
        observability endpoints.
- [ ] `GET /v1/projects/{id}/ops/queue-depth` returns
      `{project_id, total, by_role: {role: depth}}` for that project.
- [ ] `GET /v1/ops/queue-depth` (admin auth) returns fleet-wide
      depths: `{total, by_project: {id: {total, by_role: {role: n}}}}`.
- [ ] Structured log events
      `dispatcher_queue.{enqueued,dequeued,starved_yield}` fire on
      every state change with `{project_id, role, queue_depth,
      wait_ms?}`; no new counter table.
- [ ] `projects.worker_concurrency_soft INT NULL` column added
      (migration 0027). When set and contention exists, project
      is skipped after reaching its soft cap; when NULL the
      project uses the global cap unconditionally.
- [ ] Admin panel: per-project "Queue" strip on the project
      dashboard; fleet "Queue" widget on the admin home; both
      auto-refresh via SSE every 5 s. Depth > 10 for > 2 min
      paints the widget yellow; > 20 paints it red (thresholds
      configurable via settings).
- [ ] Runbook `runbooks/concurrency-overflow.md` covers: reading
      the strip, identifying whether depth is driven by one
      project or by a fleet spike, when to raise
      `WORKER_CONCURRENCY`, when to set per-project soft caps,
      when to kick a stuck dispatcher.
- [ ] Tests: `DispatcherQueue` unit tests over contention shapes
      (single project, two projects alternating, starvation
      avoidance); a dispatcher-level integration test asserting
      that with `worker_concurrency=2` and 6 tasks across 3
      projects, each project gets at least one slot within a
      bounded window; queue-depth endpoint tests covering the
      multi-tenancy ACL.

**Rollout state (2026-04-17):** global cap + admin concurrency
endpoint landed earlier (see
[`task-orchestration`](../active/task-orchestration.md)'s Evolution).
Fairness layer + queue-depth endpoints + admin strips are the
residual work. Shadow the fairness layer via
`DISPATCHER_FAIRNESS_ENABLED=false` for 48 h to confirm the
round-robin doesn't regress single-project throughput before
flipping.

## Metrics

- **Primary:** P95 wait time from task create → `orchestrate_task`
  entry, per project. Target: <30 s at cap under typical
  contention. A project with sustained P95 > 2 min is the
  starvation signal the spec exists to prevent.
- **Fairness health:** ratio of slots occupied by the busiest
  project / total slots over a 1 min window. Under contention the
  ratio should trend toward `1/N` (N = contending projects). If it
  sticks at 1.0, the round-robin is broken.
- **Queue-depth growth rate:** depth per minute averaged over a
  rolling 5 min window. A sustained positive slope means the fleet
  is capacity-limited — widen the cap or shed load.
- **Starvation yield count:** `dispatcher_queue.starved_yield` per
  hour. A project yielding is normal; a project yielding every
  cycle means its soft cap is too tight.

## Open questions

- **Soft-cap vs hard-cap semantics.** First cut makes the
  per-project cap soft (ignored when no one else is waiting).
  Some projects may want hard — a pipeline operator who's paying
  for dedicated capacity but also wants a known ceiling. Probably
  a second column (`worker_concurrency_hard`) later; not v1.
- **Queue ordering within a project.** Round-robin across
  projects, but within a project FIFO. Should `role` be factored
  in (e.g. always pick the oldest developer task before the
  oldest reviewer task)? Deferred — observe first.
- **Cross-instance fairness when we scale out.** With
  min-instances=1 today this is moot. Spec 0028 is explicit about
  single-process scope; cross-instance is a separate concern we'll
  name when it bites.
- **Admin panel refresh cadence.** 5 s SSE on every project
  dashboard might be noisy at fleet scale (N projects × 1 Hz).
  Consider switching to a single fleet-queue SSE with per-project
  deltas once we see > 10 projects.

## Links

- Related specs: [task-orchestration](../active/task-orchestration.md),
  [developer-worker](../active/developer-worker.md),
  [observability](../active/observability.md).
- Related ADRs: [0005 — multi-tenant coder-core](../../adrs/0005-multi-tenant-coder-core.md)
  (per-project isolation is the invariant this spec operationalises
  at the dispatch layer).
- Roadmap: [ROADMAP.md](../ROADMAP.md) — Phase 3, item 0028.
