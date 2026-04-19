---
id: "0030"
title: Model tier routing
type: spec
status: wip
owner: ro
created: 2026-04-18
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: ["0030"]
related_specs: [task-orchestration, observability, pm-worker, architect-worker, team-manager-worker, developer-worker, reviewer-worker]
---

# Model tier routing

## Problem

Every role worker runs on the same model today — in practice, the
most capable one available. That's correct for hard work (a net-new
Architect design, a non-trivial Developer patch) and waste on
rubber-stamp work (GC-job acceptance checks, one-line Developer
fixes, trivial Reviewer passes on a patch that only touches tests).

Anthropic ships a tier'd lineup: Haiku is ~5× cheaper and fast
enough for simple synthesis work; Sonnet is the mid-tier; Opus is
the top tier. Without tier routing we pay top-tier prices on
every task, including the ones Haiku would happily handle. With
0029 trimming input tokens, this spec attacks the other half of
the cost equation: the per-token rate.

## Users / personas

- **Project owner** — cares that costs drop without quality
  regressing. If tier routing routes a hard task to Haiku and
  ships a broken PR, the saving is negative.
- **Operator** — watches the approval-rate gauge after each
  tier-routing change. Needs per-role quality-vs-cost numbers
  visible so the routing policy is tunable, not a black box.
- **Worker authors** — write the prompts. Need the routing
  policy to be declarative (role + task-kind → tier), not
  hand-coded per call.

## Goals

- Default model per role with a per-task override hook.
- Cheaper tiers for task kinds whose historical Reviewer
  approval rate is >95% on the current top-tier model
  (evidence: 0028's admin metrics already track per-role
  approval rates).
- ≥25% additional cost reduction on routable tasks with no
  measurable quality regression (Reviewer approval rate,
  schema-retry rate, PR-merge rate).
- Per-project opt-out via settings — a cautious project owner
  can pin their whole fleet to the top tier.
- Admin panel shows per-role model in use + per-tier
  approval-rate breakdown.

## Non-goals

- Auto-learning the routing policy. Policy is human-edited;
  this spec surfaces the data to inform edits, it does not
  automate them.
- Cross-provider routing (OpenAI, local models). Stay within
  the Anthropic API.
- Prompt rewriting per-tier. A prompt that works on Sonnet
  should also work on Haiku; if it doesn't, that's a prompt
  bug, not a routing bug.
- Output caching or speculative routing (run Haiku, fall back
  to Sonnet on bad output). Route once, accept the result.

## Scope

- **Routing policy table** — `model_tier_policy.yaml` at the
  project template root. Keys: `role` × `task_kind` → one of
  `haiku` / `sonnet` / `opus`. Shipped default covers every
  current role+task_kind combination with a conservative
  choice (nothing drops below today's tier without an
  explicit entry).
- **Per-task override** — `tasks.model_tier_override` nullable
  column. When set, bypasses the policy. Used by the
  orchestrator for retries (a schema-retry on Haiku can
  escalate to Sonnet on the second attempt).
- **Worker glue** — `_model_for_task(role, task_kind,
  override) → model_id` resolved once at dispatch; passed to
  `anthropic.messages.create()`.
- **Per-project opt-out** — `projects.pin_top_tier bool`
  (default False). When True, every task routes to the
  top tier regardless of policy. For audit/compliance
  projects that can't risk quality variance.
- **Metrics** — `tasks.model_id` recorded on every task
  (already written via the response envelope, just surface
  it). `/v1/projects/{id}/metrics` gains `by_tier`:
  `{haiku: {approval_rate, avg_cost, avg_duration}, sonnet:
  {...}, opus: {...}}`. Admin `/metrics` gains a per-tier
  strip.
- **Rollout flag** — `settings.tier_routing_enabled: bool =
  False`. When False, every task routes to the current
  top-tier default (status quo). When True, the policy
  table is consulted. Per-project opt-out layers on top of
  the flag.

## Acceptance criteria

- [ ] `model_tier_policy.yaml` exists in the project template,
  validated by `scripts/validate.py` (every cell populated,
  no typos on role or task_kind). **Deferred** — phase 1
  ships with a simpler per-role config
  (`settings.worker_model_low_tier_{role}`) rather than a
  per-(role × task_kind) table. The yaml table is the v2
  evolution once per-task-kind discrimination proves
  necessary.
- [x] `resolve_tier_model(role, project, explicit_override)`
  in `coder_core.workers.dispatcher` is the single resolution
  point; the dispatcher stamps the result on
  `WorkerInput.model_override` and every worker's existing
  fallback (`task.model_override or settings.worker_model_{role}`)
  picks it up transparently. `tasks.model` still records
  what actually ran.
- [x] `tasks.model_override` lands via migration 0037 as a
  nullable string. Retry-time writes are deferred until the
  orchestrator's schema-retry path opts in.
- [x] `tier_routing_enabled=False` → every task runs on the
  role default; `tier_routing_enabled=True` → low-tier model
  picked for roles with a non-empty
  `worker_model_low_tier_{role}`; `projects.pin_top_tier=True`
  pins to top regardless; `False` forces policy regardless.
  Migration 0036 adds the per-project column.
- [x] `/v1/projects/{id}/metrics` returns `by_tier` rollup
  with task_count, succeeded, success_rate, total_cost_tokens,
  avg_cost_tokens — classified by model-name prefix
  (haiku/sonnet/opus/unknown). Admin panel rendering pending.
- [ ] 48 h shadow soak with flag off and `model_id` capture
  on produces a per-tier baseline; flag enabled on canary
  project shows ≥25% cost reduction on routable tasks with
  approval-rate delta ≤1 pp. **Canary live 2026-04-19** —
  `coder` project carries `pin_top_tier=false`; reviewer tasks
  on `coder` route to `claude-haiku-4-5-20251001` from this
  revision on. Fleet `tier_routing_enabled` still False.
  Measurement opened via `/metrics` `by_tier` on the `coder`
  project; pending 48 h data.
- [x] Per-project opt-out exercised in a test: `pin_top_tier=True`
  returns None from the resolver (routes to role default)
  regardless of the fleet flag state.

## Metrics

- **Primary:** fleet average cost-per-pipeline-run ≥25% below
  pre-flag baseline on routable tasks; fleet Reviewer
  approval rate within 1 percentage point of baseline.
- **Per-tier:** Haiku approval rate ≥95% on tasks routed to
  it; Sonnet approval rate ≥98% (higher bar: it's the mid-
  tier, if Sonnet can't hit this we're mis-routing).
- **Cost alert:** existing `SLACK_COST_ALERT_THRESHOLD`
  continues; new per-tier quality alert fires if any tier's
  approval rate drops more than 2 pp over rolling 7 days.

## Open questions

- What task-kind granularity is right? Per-role only ("all
  architect work → Sonnet") is cheap but coarse; per-role ×
  per-task-kind ("architect design → Opus, architect
  ship-draft → Sonnet") is the target. Design needs to pin
  the enum.
- Escalation on schema-retry: blanket "retry on Sonnet after
  Haiku failure" or role-specific? Probably role-specific,
  but the policy should declare it.
- How does a low-tier routing interact with 0029's prompt
  caching? Different models have different cache keys — so
  a tier change invalidates the cache. Not a blocker, but
  the policy should avoid flapping tiers inside a pipeline
  run.

## Links

- Designs: [0030 — model tier routing](../../designs/wip/0030-model-tier-routing.md)
- Related specs: [observability](../active/observability.md),
  [task-orchestration](../active/task-orchestration.md),
  role workers ([pm-worker](../active/pm-worker.md),
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [developer-worker](../active/developer-worker.md),
  [reviewer-worker](../active/reviewer-worker.md)).
- ROADMAP: Phase 4 — Cost & Token Efficiency; chains on
  [0029 — prompt caching](./0029-prompt-caching.md) for the
  full cost equation and unblocks
  [0031 — budget gates](./0031-token-budgets.md) (budgets
  downshift by tier when the soft cap trips).
