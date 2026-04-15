---
id: "0025"
title: Worker output compliance
type: spec
status: wip
owner: ro
created: 2026-04-15
updated: 2026-04-15
served_by_designs: ["0025"]
related_specs: [pm-worker, architect-worker, team-manager-worker, task-orchestration]
---

# Worker output compliance

## Problem

PM, Architect, and Team Manager workers each ask `claude` for a
structured JSON payload (spec draft, design + ADR list, task plan).
Today the dispatcher parses that payload optimistically: if Claude
emits preamble, wraps the JSON in code fences, drops a required field,
or produces a schema-shaped-but-semantically-broken object, the task
fails late — sometimes after writing a partial artifact or committing
to a branch, sometimes with a stack trace that doesn't point at the
real cause. The operator then retries by hand.

With the pipeline proven end-to-end and Phase 3 pushing for concurrent
runs (0028) and auto-retry on transients (0027), flaky structured
output becomes the dominant residual cause of pipeline stalls —
and the one that *looks* like a bug in the worker code rather than
in the model's output.

## Users / personas

- **Operator** watching the admin panel — wants a failed task to
  either recover itself or fail with a clear reason, not dump a
  parse error.
- **Pipeline chain** — downstream stages assume the upstream artifact
  is well-formed; a malformed PM spec silently poisons architect work.
- **Future auto-approval (0040)** — can't self-report confidence
  scores against unvalidated output.

## Goals

- PM, Architect, and TM workers ship with a declared JSON schema for
  their output, validated before any side effect (file write, DB row,
  commit).
- Malformed output triggers an automatic re-prompt ("your previous
  reply didn't match the schema — here are the errors — try again")
  up to N attempts, inside the same task, before the task fails.
- When all attempts fail, the task exits with a structured failure
  reason (schema error + last raw output snippet) that the operator
  can act on, not a stack trace.
- Observability captures per-worker schema-failure and retry-success
  counts so we can see which prompts are drifting.

## Non-goals

- Not a rewrite of the worker prompts. Prompt quality improvements
  live with whoever owns the worker; this spec is about the guardrail.
- Not covering the developer worker. Developer output is code +
  PR, not a JSON artifact — a different problem.
- Not a general retry framework for transient API errors (that's
  0027). This is specifically about *content* compliance.
- Not changing the human-approval gates.

## Scope

**In:**

- A JSON schema per worker (`pm_draft`, `pm_accept`, `architect`,
  `team_manager`), checked in alongside the worker code.
- A shared `validate_and_retry(raw, schema, prompt_ctx)` helper used
  by all three workers' dispatcher-Phase-4 paths.
- Per-task retry budget (default 2 re-prompts, configurable).
- Structured failure reason written to the task row on give-up —
  `failure_kind: "schema"`, `failure_detail: {...}`.
- Metrics: `worker_schema_failures_total{worker,kind}`,
  `worker_schema_retries_total{worker,outcome}`, exposed via the
  observability endpoints.
- Admin panel surfaces `failure_kind=schema` tasks with the raw
  snippet visible (no digging through logs).

**Out:**

- Streaming / partial validation.
- Auto-fixing malformed output programmatically (e.g., regex-repair).
  Re-prompting is the only remediation.
- Fallback to a weaker model on repeated schema failure — that's a
  Phase 4 concern (0030).

## Acceptance criteria

- [x] Each of PM (draft + accept), Architect, and TM has a schema
      file under `src/coder_core/workers/schemas/`.
- [x] Output is validated *before* any knowledge-write, DB mutation,
      or commit. A schema failure leaves no side effect behind.
- [x] On schema failure, the worker re-prompts Claude with a
      schema-violation message and the original inputs, up to the
      configured retry budget (default 2).
- [x] When retries exhaust, the task transitions to `failed` with
      `failure_kind="schema"` and a `failure_detail` object
      containing the validation errors and the last raw output
      (truncated).
- [x] Schema-failure and retry-outcome events exist on the structured
      log stream (`worker_output_compliance.{ok,failed,retry}`) and
      are picked up by the existing log-based observability feed.
      (coder-core ships structured logs rather than a Prometheus scrape
      — see design 0018; a dedicated counter table would be redundant.)
- [x] Admin task detail view renders `failure_kind="schema"` tasks
      with the raw output snippet and validator errors visible.
- [x] Tests cover: valid output → no retry; malformed → retry →
      valid; malformed × (budget+1) → structured failure;
      side-effect isolation on failure.

**Rollout state (2026-04-15):** All code landed and deployed in
shadow mode (`WORKER_OUTPUT_COMPLIANCE_ENABLED=false`). Enforcement
goes live after a 48 h soak once the shadow logs confirm retry-success
rates are healthy per the runbook.

## Metrics

- **Primary:** pipeline runs that stall with `failure_kind=schema`
  per week → target < 1 after rollout (from a current rate where
  every few runs hit at least one malformed-output incident).
- **Health signal:** retry-success rate per worker. > 70% means
  retries are earning their keep; < 30% means the prompt or schema
  is at fault and should be revised, not just retried.
- **Cost ceiling:** retries multiply token spend; alert if weekly
  retry tokens exceed 10% of total worker tokens.

## Open questions

- **Retry budget default.** 2 re-prompts balances cost vs recovery
  based on eyeballing recent failures, but we should tune once we
  have the retry-success metric live.
- **Schema evolution.** When a worker's output format legitimately
  changes, how do we version the schema so old in-flight tasks don't
  fail the new validator? Probably tie schema version to the task
  row; revisit during design.
- **PM acceptance reports.** These are prose-heavy with structured
  verdicts — validate the verdicts array strictly, leave the prose
  fields free-form?
- **Do we need a "malformed but acceptable" tier** (e.g., trailing
  whitespace, wrapped in code fences) that we repair in-place rather
  than re-prompt for? Likely yes for a small whitelist; design
  decision.

## Links

- Runbook: [worker-schema-failure](../../runbooks/worker-schema-failure.md)
- Related specs: [pm-worker](../active/pm-worker.md),
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [task-orchestration](../active/task-orchestration.md)
- Roadmap: [ROADMAP.md](../ROADMAP.md) — Phase 3, item 0025
