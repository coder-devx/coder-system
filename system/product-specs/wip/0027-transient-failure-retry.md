---
id: "0027"
title: Automatic retry on transient failures
type: spec
status: wip
owner: ro
created: 2026-04-15
updated: 2026-04-15
served_by_designs: ["0027"]
related_specs: [task-orchestration, developer-worker, pm-worker, architect-worker, team-manager-worker, reviewer-worker]
---

# Automatic retry on transient failures

## Problem

When a worker's `claude` invocation hits an upstream hiccup —
Anthropic 529 overloaded, 429 rate limited, a socket timeout, or a
transient DNS failure — the task lands in `failed` with a stderr
snippet nobody wants to read, and the pipeline stops. The operator
eventually notices, clicks "retry" in the admin panel, and the same
run succeeds on the next try.

We've had two back-to-back weeks where >40% of the `failed` tasks were
cleared by a single manual retry. That's not a product failure — the
model produced nothing to validate against. It's plumbing. And with
Phase 3 spec 0028 (concurrent pipelines) about to multiply the
exposure, the current "human clicks retry" loop won't scale.

Spec 0025 just landed a *content* retry path (re-prompt on schema
violation). This spec is the *transport* retry path: distinct from
schema failure, distinct from genuine model errors, applied once the
worker classifies the failure as transient.

## Users / personas

- **Operator** — wants the overnight queue to survive a 5-minute
  Anthropic blip without waking them up.
- **Pipeline chain** — a mid-run transient on the architect task
  shouldn't force the chain owner to re-kick from spec approval.
- **Cost-conscious owner** — transient retries must have a ceiling so
  a sustained Anthropic outage doesn't burn tokens in a tight loop.

## Goals

- Detect transient-class failures via a small, explicit taxonomy
  (HTTP 429 / 5xx, connection errors, read timeouts) *before* marking
  the task `failed`.
- Retry with exponential backoff and jitter, up to a bounded budget,
  without the operator seeing anything other than a log line on the
  task's row.
- On final exhaustion, mark the task `failed` with
  `failure_kind="transient"` and a structured `failure_detail` so the
  admin UI and runbook can treat it as distinct from schema failures.
- Keep transient retries orthogonal to content retries (0025): each
  has its own budget, its own counter, its own admin affordance.
- Observability: retry attempts, retry successes, retry exhaustions
  are logged as structured events so the operator can see whether
  transients are clustered (incident) or diffuse (background noise).

## Non-goals

- Not retrying schema failures. Those already have their own loop
  (spec 0025). A transient + schema compound failure retries for the
  transient side only; if the retry then produces a schema-invalid
  payload, the schema path takes over.
- Not retrying genuine model errors (`error_max_turns`, content policy
  rejections, bad prompts). The model produced something the system
  understands as "no, not that" — retrying will produce the same.
- Not a general task-level retry mechanism. Whole-task retries
  (`original_task_id` lineage, spec 0019) remain operator-initiated.
- Not a replacement for server-side circuit-breaking. If Anthropic is
  fully down, we back off and fail; we don't queue indefinitely.

## Scope

**In:**

- A `_transient.py` helper used by all five role workers that
  classifies a subprocess result (exit code + stderr patterns + CLI
  envelope `subtype`) as `transient` / `permanent` / `unknown`.
- Retry loop in the developer/reviewer/pm/architect/team-manager
  workers that wraps the existing single `claude` invocation.
- Exponential backoff with full jitter. Default budget: 3 retries,
  base delay 2s, cap 30s. All configurable via env vars.
- `tasks.failure_kind="transient"` and `tasks.failure_detail` with the
  last classification, attempt count, and the final stderr snippet,
  reusing the columns added in spec 0025.
- Structured log events:
  `worker_transient_retry.{attempt,succeeded,exhausted}` with
  `{role, attempt, delay_ms, error_kind}`.
- Admin task detail: a yellow retry-history chip that shows
  "recovered after N transient retries" on success or a distinct
  "transient failure" panel on exhaustion, reusing the 0025 panel
  pattern.

**Out:**

- Retrying the whole task dispatch from the dispatcher layer. Retries
  happen *inside* the worker so the subprocess context is cheap to
  re-spawn and we don't round-trip the database.
- Circuit breaking across tasks. A project-wide transient surge still
  hits the per-task budget; we'll add a breaker when the metric shows
  we need it.
- Per-project retry budget overrides. One global knob for now; tighten
  later if a project reports different needs.

## Acceptance criteria

- [ ] `coder_core.workers._transient.classify(exit_code, stderr, envelope)`
      returns one of `transient`, `permanent`, `unknown` with fixtures
      covering 429, 529, `error_overloaded`, `read timed out`,
      `connection reset`, and a handful of non-transient stderr
      samples from past runs.
- [ ] Each of developer / reviewer / pm / architect / team-manager
      workers loops `classify` + backoff around the existing `claude`
      invocation. On `transient` with retries remaining, sleep and
      retry; on `permanent` or budget exhaustion, return the existing
      failed `WorkerResult` shape.
- [ ] Retry budget, base delay, and cap are env-configurable
      (`WORKER_TRANSIENT_RETRY_BUDGET` default 3,
      `WORKER_TRANSIENT_RETRY_BASE_MS` default 2000,
      `WORKER_TRANSIENT_RETRY_CAP_MS` default 30000).
- [ ] When all retries fail, `tasks.failure_kind="transient"`,
      `tasks.failure_detail` is a JSON blob
      `{error_kind, attempts, delays_ms[], last_stderr}`; no
      side-effectful writeback runs.
- [ ] `worker_transient_retry.*` log events fire at each attempt with
      the role, attempt number, chosen delay, and classification.
- [ ] Admin task detail: recovered runs show a small yellow chip
      "recovered after N transient retries"; exhausted runs render a
      yellow panel equivalent in shape to the 0025 schema panel.
- [ ] Tests: unit tests for `classify`; a worker-level test that uses
      a stubbed subprocess to cover transient-then-success and
      transient × (budget+1) paths; a dispatcher-level test that
      verifies `failure_kind="transient"` is written on exhaustion
      without other side effects.

## Metrics

- **Primary:** weekly rate of tasks manually retried by the operator
  that were later confirmed transient. Target: < 2 per week after
  rollout (baseline is ~20).
- **Health signal:** retry-success rate. Above 85% → retries are
  buying what the spec promises. Below 60% → the classifier is
  misbehaving or backoff is insufficient.
- **Cost ceiling:** weekly tokens spent in retries. Alert if retry
  tokens exceed 5% of total worker tokens (lower than 0025's 10%
  since transients don't consume tokens for prompt work).

## Open questions

- **Shared transient classifier vs per-worker.** Exit-code semantics
  are probably the same across all workers; envelope `subtype`
  definitely is. One shared module is the intent, but a follow-up may
  need per-worker overrides (e.g. architect's 900 s timeout is
  intentional, not transient). Revisit during design.
- **Jitter policy.** Full jitter is the default; equal-jitter is an
  alternative if we see thundering-herd on a shared Anthropic blip.
  Pick one and document.
- **Interaction with 0025 schema retries.** A transient-then-schema
  sequence is plausible. Confirm that the outer transient loop sees
  only subprocess-level failures and the inner 0025 loop handles
  model-output failures; no overlap of budgets, no double counting.
- **Backoff on cancel.** If the operator cancels a task mid-backoff,
  the sleep should wake early. Implementation detail for design.

## Links

- Runbook: [worker-transient-failure](../../runbooks/worker-transient-failure.md)
  (to be drafted alongside the design).
- Related specs: [task-orchestration](../active/task-orchestration.md),
  [developer-worker](../active/developer-worker.md),
  [reviewer-worker](../active/reviewer-worker.md),
  [pm-worker](../active/pm-worker.md),
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md).
- Roadmap: [ROADMAP.md](../ROADMAP.md) — Phase 3, item 0027.
