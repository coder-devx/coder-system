---
id: concurrency-overflow
title: Concurrency overflow — operator triage when the queue climbs
type: runbook
status: active
owner: ro
created: 2026-04-17
updated: 2026-04-17
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: []
---

# Concurrency overflow

Operational guide for the admin panel's **Queue** signals (the
`DispatcherQueue` shipped in spec
[0028](../product-specs/wip/0028-concurrent-pipelines.md) —
per-project strip on the project dashboard, fleet widget on the
admin home). Use this when the widget goes yellow (depth > 10) or
red (depth > 20), or when a managed-project owner reports "my
pipeline is sitting still."

## When to run this

- **Fleet queue widget** on the admin home is yellow for > 2 min or
  red at any point. Auto-refresh is 5 s; a quick spike that
  recovers isn't worth triaging.
- **Per-project Queue strip** on a project dashboard is amber / red
  while the project owner reports delayed pipeline progress.
- `dispatcher_queue.exhausted`-shaped events start dominating the
  observability feed (sustained enqueued-but-not-dequeued).
- `worker_transient_retry.exhausted` rate climbs alongside queue
  growth — it's worth knowing whether retries are piling into the
  cap or the provider is degraded.

## Who can run this

Operator with admin JWT. Most remediations are single
configuration writes (env var flip or per-project soft cap);
nothing here needs a code change.

## What the signals mean

A **Queue** strip value is the count of orchestrations currently
*waiting* for a slot — not the count running. `Workers 3/4` plus
`Queue 0` is the normal healthy state. `Workers 4/4` plus
`Queue 7` means the cap is saturated and seven tasks are queued.

The widget colour bands are thresholds, not targets. A short
amber window during a plan-approval burst is expected. Sustained
amber or any red is a signal to intervene.

**Per-project strip** (`Queue 3 developer:2 · reviewer:1`) breaks
depth down by role so the operator can tell "fan-out plan just
started" (developer-heavy) from "reviewer is slow and piling up"
(reviewer-heavy).

**Fleet widget** (`Fleet queue 7 (busiest: acme ×5)`) surfaces the
driver project as the primary signal. If depth is high but no
single project dominates, it's a fleet capacity limit — raise the
global cap. If one project dominates, it's local — consider a
per-project soft cap instead.

## Triage

1. **Open the admin home.** Note the fleet total and the busiest
   project.
2. **Navigate to the busiest project's dashboard.** Read the
   per-project Queue strip — depth + role breakdown.
3. **Check the global Workers strip** (same project page).
   `Workers N/N` saturated means the cap is the limit; `N/cap` with
   headroom means *fairness* or *soft caps* are the limit.
4. **Classify the shape:**
   - *Single project driving the fleet queue* → contention from one
     tenant. Consider a soft cap (outcome C below).
   - *Multiple projects, all amber* → fleet capacity. Raise the
     cap (outcome B).
   - *Persistent red on one project with Workers not saturated* →
     a pipeline is stuck, not busy. Orphan reaper territory
     (outcome D).
5. **Triage each report within the week.** Amber with no driver is
   the signal to tune; amber with a specific driver is the signal
   to either coach the project owner or set the soft cap.

## Remediation paths

### Outcome A — Wait it out

First response when the widget is amber for < 2 min and you can
see a specific triggering event (a plan just approved, a bulk
retry just fired). Watch the auto-refresh. Most bursts drain in
under 5 min at the default `worker_concurrency=4`.

### Outcome B — Raise the global cap

The fleet is genuinely capacity-limited: depth stays amber across
multiple projects for > 5 min. Bump the Cloud Run env:

```
WORKER_CONCURRENCY=8
```

- Apply via `gcloud run services update coder-core --update-env-vars WORKER_CONCURRENCY=8`
  (or the equivalent in the operator's deploy tooling).
- Don't exceed 12 without validating memory headroom — each
  concurrent `claude` subprocess allocates its own transcript
  buffer, and Cloud Run min-instances=1 means one box carries
  the whole cap.
- A running `DispatcherQueue` doesn't auto-pick up the change; the
  next process restart does. If you can't wait for the next
  deploy, use the same update command's implicit restart
  behaviour (or the admin "bounce dispatcher" button if present).

### Outcome C — Set a per-project soft cap

One project is holding every slot and starving others. The
per-project soft cap yields that project's turn once it has
`worker_concurrency_soft` slots in flight *and* another project
has waiters — soft semantics per spec 0028 (yield only on
contention; project can still use the full cap when alone).

- In the admin panel project settings: set "Soft worker cap" to
  N (≤ `worker_concurrency`, usually half). The setting writes
  `projects.worker_concurrency_soft` and the live
  `DispatcherQueue` picks it up on the next admission decision —
  no restart.
- Clear the cap (set to null) when the contention subsides if
  the project otherwise wants the full cap available.

### Outcome D — Stuck pipeline, not a capacity problem

Workers strip shows `Workers N/cap` with headroom but the Queue
strip is non-empty and depth isn't draining. That's not a
contention issue — something is stuck.

- Check for `failure_kind="transient"` tasks in the busiest
  project; see [worker-transient-failure](./worker-transient-failure.md).
- Check for orphaned `running` rows past their per-role deadline
  (ADR 0011's reaper should be handling these; if it isn't,
  investigate the reaper).
- If the orchestration coroutine itself hangs (rare), a process
  restart unblocks the waiter; subsequent re-dispatch from the
  reaper resumes the task.

### Outcome E — Classifier-flagged `unknown` retry spike

The queue-depth widget is a secondary signal when a transient-retry
classifier starts misbehaving (spec 0027). If `unknown`-classified
stderr patterns spike and queue depth climbs alongside, the workers
are retrying inside slots they shouldn't be. Extend the classifier
before dismissing the queue climb.

## Success condition

- Fleet widget returns to green (depth = 0) within 10 min of the
  remediation.
- Busiest-project indicator rotates — no single project
  dominates for more than one drain cycle.
- Per-project waiters P95 wait time stays under 2 min once
  contention passes (see the spec metrics for the weekly rollup).

## If something goes wrong

- **Bumping the cap didn't help.** Either the queue isn't the
  bottleneck (see Outcome D) or memory pressure on the Cloud Run
  box is throttling new spawns. Check CPU/memory in GCP console;
  scale Cloud Run `--cpu` / `--memory` before increasing the cap
  further.
- **Soft cap set but project still dominates.** The soft cap is
  ignored when no other project has waiters (soft semantics). If
  the cap was set expecting hard enforcement, use the runbook's
  Outcome B instead — raise the global cap so the dominating
  project's work completes faster without blocking others.
- **Queue climbs but Workers strip stays under cap.** Most
  likely cause: a `DispatcherQueue` bug leaked admitted events
  without incrementing `in_flight`. File an incident. Workaround:
  restart the coder-core instance — queue state is in-memory and
  resets on boot.
- **Admin strips show 0 depth but users report delays.** The
  orchestration may be hanging before the queue — i.e. before
  `await queue.acquire(...)`. Look for hung POST handlers or
  stuck DB sessions; this isn't a fairness issue.

## Related

- Spec: [0028 — concurrent pipelines](../product-specs/wip/0028-concurrent-pipelines.md)
- Design: [0028 — concurrent pipelines](../designs/wip/0028-concurrent-pipelines.md)
- ADRs: [0005 — multi-tenant coder-core](../adrs/0005-multi-tenant-coder-core.md)
  (per-project isolation is the invariant this spec enforces at
  the dispatch layer).
- Adjacent: [worker-transient-failure](./worker-transient-failure.md)
  (retry storms can masquerade as queue overflow);
  [worker-schema-failure](./worker-schema-failure.md).
