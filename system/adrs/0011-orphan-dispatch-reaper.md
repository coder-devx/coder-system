---
id: "0011"
title: In-process orphan reaper for Cloud Run dispatches
type: adr
status: accepted
date: 2026-04-14
deciders: [ro]
relates_to_designs: ["0001", "0004"]
---

# ADR 0011 — In-process orphan reaper for Cloud Run dispatches

## Context

`coder-core` dispatches worker runs from inside the HTTP handler via
`asyncio.create_task(orchestrate_task(...))` after the response is sent.
Each dispatch shells out to the `claude` CLI for up to 1200s and then
writes the next state transition back to the `tasks` table.

This pattern fails under Cloud Run's normal lifecycle:

- **Deploys** replace instances. Any in-flight `asyncio` task on the
  outgoing instance is terminated when the SIGTERM grace period
  elapses — far shorter than a developer run.
- **Scaling churn** spins up transient instances above `minScale` when
  load increases and drains them once the request surge ends. Dispatches
  that happened to land on a transient instance die with it.

The observed symptom is a task row stuck at `status='running'` past the
worker's CLI timeout with no further state transitions, no logs from
the worker between dispatch start and "now", and no way to recover
short of a human calling `POST /tasks/{id}/override {"action":"retry"}`.

Observed twice on a single spec-0024 chain-test run (task `6c799ecd`):
once during a deploy that happened mid-pipeline, once during apparent
scaling churn with no correlating deploy.

## Options considered

1. **Cloud Tasks push queue.** Each dispatch becomes an enqueue + a
   separate HTTP request to a worker endpoint. Cloud Tasks retries on
   failure, survives instance churn natively, and decouples dispatch
   lifecycle from HTTP request lifecycle. Requires new GCP resources
   (queue, IAM bindings), a new authenticated HTTP endpoint on
   coder-core (or a sibling service), and rewiring `tasks.py` and the
   stage transitions that re-dispatch (testing → reviewing → fixing).
2. **Pub/Sub push subscription.** Same shape as Cloud Tasks with a
   different substrate. Slightly better for fan-out, slightly worse
   ergonomics for "enqueue this specific task ID with a delay".
3. **Cloud Run Jobs per dispatch.** Each worker run is a Cloud Run Job
   execution, not a background asyncio task. Strongest isolation, but
   highest per-dispatch latency (container cold start per run) and a
   larger rewrite — the orchestrator stops being in-process entirely.
4. **In-process orphan reaper.** Keep the existing dispatch model but
   add a background loop inside each coder-core instance that scans
   for `status='running'` tasks older than the worker timeout and
   re-queues them. Self-healing without new infra. Bounded by a hard
   cap so a genuinely hung worker doesn't thrash forever.
5. **Do nothing, document the manual retry.** Every long chain test
   requires a human on call with `curl`. Not acceptable once multiple
   projects are onboarded.

## Decision

Adopt **option 4 — the in-process orphan reaper — as the near-term fix**,
and keep **option 1 — Cloud Tasks — as the planned structural fix** for
when reaper-induced latency becomes the bottleneck or when we need true
dispatch durability across a full Cloud Run outage.

The reaper:

- Runs as a background `asyncio` task started in the FastAPI `lifespan`
  on every coder-core instance, gated by `reaper_enabled` AND
  `dispatcher_enabled`.
- Wakes every 60s and scans for tasks matching
  `status='running' AND stage IN (executing, testing, fixing, reviewing, enriching) AND started_at < now - 1500s`.
- Requeues via a compare-and-set on `(status, started_at)` so only one
  instance wins when multiple reapers race. The losers see `rowcount=0`
  and skip.
- Caps at 3 reaps per task. The fourth time a task qualifies, the row
  is transitioned to `stage=stuck, status=failed` with an explanatory
  error so a human investigates.

## Rationale

Cloud Tasks is the right long-term answer but it's several days of work
spread across IAM, infra-as-code, a new HTTP endpoint, and rewiring the
stage machine — all while the pipeline is wedged on orphaned dispatches
that a human currently unblocks by hand. The reaper is ~300 lines,
fully covered by tests, and ships today. It turns "pipeline halted,
requires human + curl" into "up to ~25 min extra latency on a long
dispatch when it orphans, self-heals, logs the event".

The 1500 s threshold is the developer-worker CLI timeout (1200 s) plus
a 300 s buffer so healthy long runs are never reaped. The 60 s scan
interval bounds the detection window; the hard cap of 3 reaps bounds
the pathological case.

## Consequences

- Positive: the pipeline self-heals through Cloud Run deploys and scaling
  churn without human intervention.
- Positive: the reaper's log lines (`orphan_requeue`, `orphan_cap_hit`)
  become a visible signal for how often churn is costing us latency — a
  forcing function for deciding when Cloud Tasks is worth the effort.
- Negative: a task orphaned at the very start of the executing stage now
  takes up to 25 min + interval to self-recover instead of completing in
  its normal budget. Latency, not correctness.
- Negative: the reaper shares fate with coder-core. If the whole service
  is down, nothing reaps. Cloud Tasks would not have this property.
- Follow-up: when multi-project load starts producing frequent reaps,
  write the Cloud Tasks design and supersede this ADR.
- Follow-up: the `tasks.py` `create_task` and `override` handlers still
  call `asyncio.create_task(orchestrate_task(...))`. The reaper is the
  safety net, not a replacement — they must keep working, and be the
  fast path.
