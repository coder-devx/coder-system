---
id: "0027"
title: Automatic retry on transient failures
type: design
status: wip
owner: ro
created: 2026-04-15
updated: 2026-04-15
implements_specs: ["0027"]
decided_by: ["0013"]
related_designs: [worker-roles, worker-communication, pm-worker, architect-worker, team-manager-worker]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin]
---

# Automatic retry on transient failures

## Context

Worker subprocesses — the five role workers that shell out to `claude`
— occasionally fail for reasons that have nothing to do with the
task: Anthropic 429 / 529, transient DNS, socket reset, read timeout.
Today the dispatcher captures the failure verbatim, marks the task
`failed`, and the operator clicks "retry" in the admin panel. Two
back-to-back weeks have shown >40% of `failed` rows were cleared by a
single manual retry.

Spec 0025 shipped a *content* retry path: the worker re-prompts claude
when its JSON output fails schema validation. That path lives **inside**
the worker and is orthogonal to transport failures — a 529 on the first
attempt never reaches the schema validator. See
[ADR 0013](../../adrs/0013-worker-level-transient-retry.md) for why
transient retries also live inside the worker rather than at the
dispatcher.

## Goals / non-goals

- **Goals**
  - Classify subprocess failures as `transient`, `permanent`, or
    `unknown` via a small, explicit taxonomy shared by all five
    workers.
  - Retry transient failures with exponential backoff + full jitter,
    up to a bounded budget; surface budget exhaustion as
    `failure_kind="transient"` so the admin panel and runbook treat
    it distinctly from schema failures.
  - Compose cleanly with 0025: the transient loop wraps the subprocess
    invocation; the schema loop wraps the *content* of a successful
    subprocess. No overlapping budgets.
  - Emit structured log events (`worker_transient_retry.*`) that let
    us tell a clustered incident (Anthropic blip) from diffuse
    background noise.
- **Non-goals**
  - Retrying whole-task dispatches from the dispatcher. That round-trips
    the database and re-runs the 0025 compliance gate unnecessarily.
  - Classifying *model* failures (`error_max_turns`, content policy,
    hard prompt errors) as transient. The model produced a definitive
    "no" — retrying produces the same.
  - Circuit-breaking across tasks. A project-wide transient surge
    still hits the per-task budget; add a breaker when the metric
    demands it.
  - Per-project budget overrides. One global knob; tighten later.

## Design

```mermaid
flowchart TB
  subgraph Worker [Role worker]
    Start([dispatch task]) --> TLoop{transient loop<br/>attempt = 0}
    TLoop --> Spawn[spawn claude<br/>subprocess]
    Spawn --> Classify{classify<br/>exit + stderr + envelope}
    Classify -->|transient<br/>+ budget left| Backoff[sleep expo + jitter<br/>attempt += 1]
    Backoff --> Spawn
    Classify -->|transient<br/>+ budget exhausted| TFail[failure_kind = transient<br/>failure_detail = {attempts, delays, error_kind, last_stderr}]
    Classify -->|permanent| PFail[return existing failed<br/>WorkerResult]
    Classify -->|ok| SLoop{0025 schema loop}
    SLoop -->|ok| WB[Phase 4 writeback]
    SLoop -->|schema failure| SFail[failure_kind = schema]
  end
  TFail --> Admin[admin panel:<br/>yellow 'transient failure' panel]
  WB -->|recovered after N retries| Chip[admin panel:<br/>yellow 'recovered after N retries' chip]
```

### Parts

- `src/coder_core/workers/_transient.py` — shared classifier.
  - `classify(exit_code: int, stderr: str, envelope: dict | None) -> Classification`
    where `Classification = Literal["transient", "permanent", "unknown"]`.
  - Pure function; no I/O. Fixture table lives alongside tests.
- `src/coder_core/workers/_transient_retry.py` — the retry wrapper.
  - `async def run_with_transient_retry(spawn: Callable[[], Awaitable[SpawnResult]], *, settings) -> RetryOutcome`
    where `RetryOutcome` is either `Ok(spawn_result)` or
    `TransientFailure(error_kind, attempts, delays_ms, last_stderr)`.
  - Owns the backoff sleep; honours a cancellation token so a
    mid-backoff task cancel wakes early.
- `src/coder_core/workers/{developer,reviewer,pm,architect,team_manager}.py`
  — each wraps its single `claude` invocation in
  `run_with_transient_retry`. No other behavioural change; the
  existing schema loop (for the three structured-output workers)
  continues to run on the returned `SpawnResult`.
- `src/coder_core/workers/dispatcher.py` — on `TransientFailure`,
  writes `tasks.failure_kind="transient"` and `tasks.failure_detail`
  reusing the columns added in 0025's migration
  (`0020_worker_output_compliance`). No new migration.
- `src/coder_core/config.py` — three env-configurable settings:
  - `worker_transient_retry_budget` (default 3)
  - `worker_transient_retry_base_ms` (default 2000)
  - `worker_transient_retry_cap_ms` (default 30000)
- `coder-admin/src/pages/TaskDetail.tsx` — extends the existing
  failure-detail region. Recovered runs: yellow chip "recovered after
  N transient retries" sourced from
  `task.transient_retry_history` (new nullable column — **see
  migration** below). Exhausted runs: a yellow panel sibling to the
  0025 schema panel, rendering `error_kind`, `attempts`, `delays_ms`,
  and the truncated `last_stderr`.
- `migrations/versions/0021_transient_retry_history.py` — adds
  `tasks.transient_retry_history JSONB NULL`. Populated on both
  success-after-retry (so the admin chip is available) and failure.
  Omitted when attempts == 0, to keep row size in the common case.

### The classifier taxonomy

`classify(exit_code, stderr, envelope)` returns:

- **`transient`** when any of:
  - Envelope `subtype` is `error_overloaded` (claude CLI's term for
    Anthropic 529).
  - `stderr` contains any of: `"rate limit"`, `"429"`, `"529"`,
    `"timed out"`, `"connection reset"`, `"temporary failure in name
    resolution"`, `"socket hang up"` (case-insensitive, exact
    substring, no regex).
  - `exit_code` is one of `{124}` (GNU `timeout`) when the CLI was
    invoked under a wrapper. Not used today but reserved so the table
    survives future wrapping.
- **`permanent`** when `envelope.subtype` is one of
  `{"error_max_turns", "error_during_execution"}` with a model-side
  error detail, or `exit_code == 0` but the output is otherwise
  malformed (which is a `permanent`-to-transient-layer signal; the
  schema loop takes over).
- **`unknown`** for everything else. An `unknown` classification is
  **not** retried — we surface it as the existing failed
  `WorkerResult` and let the operator decide. `unknown` counts toward
  a metric so we can extend the taxonomy when new patterns appear.

The explicit substring list keeps the classifier auditable. A new
failure mode shows up once in admin, once in `unknown`, and then gets
a fixture + entry added to the table — in a PR the reviewer can
reason about.

### Backoff policy

`delay_ms(attempt) = min(cap_ms, random.uniform(0, base_ms * 2 ** attempt))`
— **full jitter**. First retry waits 0–2 s; second 0–4 s; third
0–8 s; capped at 30 s. Budget default 3 ⇒ worst case 4 spawns
(including the original), bounded wall clock ~42 s plus subprocess
time.

Full jitter is chosen over equal-jitter to avoid thundering-herd on
a shared Anthropic blip — when 5 workers hit 529 simultaneously,
equal-jitter has them all retry in the same ~2 s window; full
jitter spreads them 0–2 s. If we later see a run-away collision
pattern we'll switch to decorrelated jitter; the knob lives in
`_transient_retry.py` behind a single function.

### Data flow

1. Worker enters `run_with_transient_retry(spawn=…, settings=…)`.
2. The wrapper calls `spawn()` — a closure that owns the subprocess
   build + stdin + stdout capture + envelope parse. Fresh subprocess
   every attempt; no session state.
3. On return, `classify(exit_code, stderr, envelope)` runs. Outcomes:
   - `transient` + attempts < budget → log
     `worker_transient_retry.attempt`, sleep `delay_ms`, re-spawn.
   - `transient` + attempts == budget → log
     `worker_transient_retry.exhausted`, return `TransientFailure`.
   - `permanent` / `unknown` → return `Ok(spawn_result)` with the
     original failure payload so the caller's existing error path
     runs (including the schema loop for structured workers, which
     will correctly treat malformed output as a schema failure).
   - `transient` that succeeded on attempt > 0 → log
     `worker_transient_retry.succeeded`, return
     `Ok(spawn_result)` with a `retry_history` so the dispatcher can
     persist it.
4. Dispatcher:
   - `TransientFailure` → `tasks.status=failed`,
     `failure_kind="transient"`, `failure_detail={error_kind,
     attempts, delays_ms, last_stderr[:4096]}`,
     `transient_retry_history` NOT populated (covered by
     failure_detail).
   - Recovered run → write `tasks.transient_retry_history = {attempts,
     delays_ms, error_kind}` and continue into the schema loop /
     writeback.

### Structured log events

| Event | Fields |
|---|---|
| `worker_transient_retry.attempt` | `role, task_id, attempt, delay_ms, error_kind, last_stderr_snippet` |
| `worker_transient_retry.succeeded` | `role, task_id, attempts, total_delay_ms, error_kind` |
| `worker_transient_retry.exhausted` | `role, task_id, attempts, total_delay_ms, error_kind, last_stderr_snippet` |
| `worker_transient_retry.unknown` | `role, task_id, exit_code, stderr_snippet` — classifier saw an unfamiliar pattern; review in next taxonomy PR |

These ride the existing structured-log observability feed (see design
0018 / `observability-and-cost-tracking`); no new Prometheus counters.

### Invariants

- The transient loop spawns a **fresh** `claude` subprocess on each
  attempt; there is no session continuity across retries. This keeps
  the retry behaviourally identical to a manual re-click.
- The transient loop never touches the database during retry. Only on
  final outcome (exhausted or recovered-with-history) does the
  dispatcher write.
- Transient and schema budgets are distinct. A first attempt that
  returns a 529 consumes 1 transient budget and 0 schema budget; a
  retry that returns malformed JSON consumes 0 transient budget and
  1 schema budget. A single task can worst-case spawn
  `(1 + transient_budget) * (1 + schema_budget)` subprocesses —
  caught by the cost-ceiling alert.
- `tasks.failure_kind` is monotonically set: if a task ever succeeds
  at the transient layer, `failure_kind` is `null` or `"schema"`
  (from 0025), never `"transient"`.
- Cancellation pre-empts the backoff sleep: `asyncio.sleep` wrapped
  in a `asyncio.wait_for` against the task cancel event so an
  operator cancel during a 30 s backoff wakes within ~100 ms.

### Edge cases

- **Envelope missing (subprocess died before JSON).** `classify`
  receives `envelope=None`; falls through to stderr substring match.
  If no substring matches, `unknown` — surfaces for taxonomy review.
- **Retry exceeds task deadline.** The per-task deadline (architect
  900 s, others 600 s) wraps the whole worker call. If transient
  retries consume the deadline, the outer timeout fires and the
  existing timeout path handles it — classified as `permanent`
  (architect timeouts are intentional, not transient; see
  `open questions` in spec 0027).
- **Spawn fails before subprocess (exec error).** Treated the same
  as a failed subprocess with `exit_code=127` and a synthetic
  `stderr="exec failed: ..."`; classified `permanent`.
- **Concurrent retries across tasks.** Each task has its own
  transient loop; no cross-task coordination. The cost-ceiling
  alert is the safety net if Anthropic is degraded and all tasks
  retry-bomb together.

## Rollout

Single PR, shadow-first mirroring the 0025 pattern.

1. Ship classifier + wrapper + worker wiring + admin UI + migration
   behind `settings.worker_transient_retry_enabled` (default `false`).
   In shadow mode, the classifier runs and logs
   `worker_transient_retry.shadow_{transient,permanent,unknown}` but
   the existing fail-on-first-error path still drives the worker
   result. This gives us a real-world false-positive signal on the
   classifier before we start re-spawning subprocesses.
2. After 48h of shadow data, review `unknown`-classified events and
   widen the substring table if needed. Flip
   `worker_transient_retry_enabled=true`. Existing in-flight tasks
   are unaffected (worker process already past the check).
3. Admin-panel chip + panel ships in the same PR but is a no-op until
   `transient_retry_history` / `failure_kind="transient"` rows appear.
4. Runbook entry:
   [`worker-transient-failure`](../../runbooks/worker-transient-failure.md)
   — operator steps when a task lands with `failure_kind="transient"`
   (rare once rollout is live — the whole point is that transients
   self-heal).

## Open questions

- **Shared vs per-worker classifier.** The taxonomy is shared today
  because exit codes and envelope shapes are identical across
  workers. Architect's intentional 900 s timeout is the one place a
  per-worker override could land; we'll add a
  `classifier_overrides: dict[role, list[str]]` hook if a second
  role needs one.
- **Full vs decorrelated jitter.** Starting full. Revisit if the
  retry-success-rate metric trends down *and* the aggregate
  retry-delay histogram shows bunching.
- **Should `transient_retry_history` live on the `tasks` row or on
  `task_stage_runs`?** On the row for now — simpler, and the retry
  is worker-local so the granularity of stage-runs is overkill. If
  0028 introduces multi-stage worker invocations, revisit.
- **Cancel-during-backoff guarantee.** The 100 ms wake target is
  aspirational; wrapping `asyncio.sleep` in `wait_for` against the
  cancel event is the implementation intent but the reviewer should
  verify there is no missed signal on the cooperative cancel path.

## Links

- Spec: [wip/0027-transient-failure-retry](../../product-specs/wip/0027-transient-failure-retry.md)
- ADR: [0013 — worker-level transient retry](../../adrs/0013-worker-level-transient-retry.md)
- Peer spec/design: [0025 — worker output compliance](./0025-worker-output-compliance.md)
- Related designs: [worker-roles](../active/worker-roles.md),
  [worker-communication](../active/worker-communication.md),
  [pm-worker](../active/pm-worker.md),
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md)
- Runbook: [worker-transient-failure](../../runbooks/worker-transient-failure.md)
