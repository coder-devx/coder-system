---
id: "0013"
title: Transient retry lives inside the worker, not at the dispatcher
type: adr
status: accepted
date: 2026-04-15
deciders: [ro]
relates_to_designs: [pm-worker, architect-worker, team-manager-worker, worker-roles, worker-communication]
---

# ADR 0013 — Transient retry lives inside the worker, not at the dispatcher

## Context

Spec 0027 adds automatic retry on transport-level failures (Anthropic
429 / 529, connection resets, read timeouts) so the overnight pipeline
queue survives a 5-minute provider blip without waking an operator.
The retry loop has to live somewhere. Two obvious candidates:

1. **Inside the worker.** Wrap the existing single `claude` subprocess
   call in a retry helper that re-spawns on a transient classification.
   The dispatcher sees one `WorkerResult` — succeeded (possibly with a
   retry history) or failed.
2. **At the dispatcher.** The dispatcher calls the worker, catches a
   distinguished `TransientError`, sleeps, and re-dispatches the same
   task — potentially rehydrating from the database.

Both "work" in the happy case. The choice matters for how retries
interact with the database, the schema-validation loop (0025), the
orphan reaper (ADR 0011), and the admin-panel user model.

## Options considered

1. **Retry inside the worker (this ADR).** The worker owns the retry
   budget, the backoff sleep, and the classification. The dispatcher
   is oblivious: it sees a `WorkerResult` with a `retry_history` on
   the happy path or a `TransientFailure` on give-up.
2. **Retry at the dispatcher.** The worker raises `TransientError`;
   the dispatcher catches, sleeps, re-runs `workers.<role>.run(task)`.
   The task row stays in `running`; a "retry attempt" counter lives
   on the row.
3. **A separate retry coordinator service.** Scheduled job watches for
   `failure_kind="transient"` rows and re-queues them. Rejected as
   over-engineered for the observed problem size (manual retries
   today clear in one click; this pattern is designed for a stream
   10× bigger).

## Decision

Adopt **option 1 — retry inside the worker**. The dispatcher's
contract with workers is unchanged: one call, one result. Transient
retries, including the backoff sleep and budget accounting, are an
internal detail of the worker.

## Rationale

**Cost and latency.** A re-spawn of the `claude` subprocess from the
same worker is cheap: no database round-trip, no re-parse of the
system prompt, no re-fetch of the repos manifest, no re-dispatch
through the task queue. Dispatcher-level retry rebuilds all of that
context on every attempt, and a 5-minute Anthropic blip that causes
4 retries at 2, 4, 8, 16 s backoff would also pay for 4× database
round-trips and 4× context-build passes.

**Composition with 0025.** The schema loop (0025) lives inside the
worker; it wraps the *content* of a successful subprocess. Putting
the transient loop inside the same worker means the two loops nest
naturally: transient wraps the spawn, schema wraps the output of a
successful spawn. At the dispatcher level we'd have to distinguish
"worker returned schema failure" from "worker returned transient
failure" *and* decide whether to retry each — duplicating the
classification that already lives in the worker. Keeping both loops
inside the worker puts the decision at a single layer.

**Orphan reaper semantics.** ADR 0011's reaper looks for tasks stuck
in `running` past a per-role deadline. A worker-internal retry keeps
the task in `running` for the full retry duration — one long run, one
row, one reaper check. A dispatcher-level retry either (a) writes
intermediate `failed` states the reaper would race against, or
(b) invents a new `retrying` state the reaper has to understand. Both
are strictly worse than "the reaper sees what it always sees".

**Operator mental model.** The admin panel already shows per-task
state. A dispatcher-level retry makes a single operator action
(click "retry") look different from a system action (dispatcher
retry) — the first spawns a new task, the second keeps the same
row. Worker-internal retry collapses both to "the row keeps
running; retry history is a detail on the row".

## Consequences

- **Positive.** Dispatcher stays simple. The worker↔dispatcher
  contract is unchanged.
- **Positive.** 0025's schema loop composes naturally inside the
  transient loop with zero new plumbing.
- **Positive.** The reaper and admin panel continue to see a single
  `tasks` row per logical task, regardless of retries.
- **Positive.** `tasks.transient_retry_history` is a diagnostic
  artifact on a single row, not a join across retry attempts.
- **Negative.** The worker subprocess holds open longer (up to
  ~42 s extra wall clock at default budget). Cloud Run CPU-always
  is already required for background workers; this adds to the
  envelope but stays well inside Cloud Run's 60 min request
  ceiling.
- **Negative.** If the worker process itself dies mid-retry (pod
  OOM, instance restart), the retry budget is lost with it — the
  reaper re-dispatches from scratch. Acceptable: a pod death is
  already a rare event and the re-dispatch starts fresh anyway.
- **Follow-up.** Spec 0028 (concurrent pipelines) may add a
  dispatcher-level *rate* knob (e.g. "no more than K concurrent
  transient retries") on top of the per-worker budget. That's a
  complement, not a replacement.
