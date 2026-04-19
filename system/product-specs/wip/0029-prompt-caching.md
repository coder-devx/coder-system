---
id: "0029"
title: Prompt caching & shared context reuse
type: spec
status: wip
owner: ro
created: 2026-04-18
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: ["0029"]
related_specs: [task-orchestration, observability, knowledge-api, pm-worker, architect-worker, team-manager-worker, developer-worker, reviewer-worker]
---

# Prompt caching & shared context reuse

## Problem

Every role worker re-sends the same prefix to Anthropic on every
task: the role system prompt, the project AGENTS.md, and the slice of
`active/` knowledge the prompt pulls in. Inside one pipeline run, the
PM / Architect / TM / Developer / Reviewer tasks also re-read
overlapping slices of the same project repo — nothing is shared.

Input-token spend dominates per-pipeline cost (see the
`/metrics` `daily_cost` chart — input is >80% on every sampled
day). This is pure waste: the content the model is re-reading has
not changed between the first call and the hundredth. Anthropic
already ships prompt caching on the API we're using; we just don't
opt in.

## Users / personas

- **Project owner** — pays the bill. Cares that a run that costs
  $X today costs $0.5X once this ships, with no quality change.
- **Operator** — watches the `/metrics` dashboard and the Slack
  cost alert. Cares that the cache-hit metric is visible, because
  "cost dropped" without an explanation is indistinguishable from
  "we broke billing".
- **Worker authors** (PM, Architect, TM, Dev, Reviewer roles) —
  write the prompts. Cares that opting into caching doesn't force
  a prompt rewrite every time a WIP ships.

## Goals

- ≥40% reduction in input tokens on orchestrated pipeline runs,
  measured against the 7-day baseline of the week before enable.
- No measurable regression in output quality (Reviewer approval
  rate, schema-retry rate, pipeline success rate).
- Cache-hit ratio is a first-class metric on `/metrics`, not a
  log-scraped number.
- Shared "project context block" (AGENTS.md + relevant
  `active/` subgraph at `min_freshness=40`) is computed once per
  pipeline run and passed as a cache-hit-friendly prefix to every
  sibling task in that run.

## Non-goals

- Output caching. Two PM draft tasks with identical input should
  still re-run — this isn't about memoising decisions.
- Cross-pipeline sharing. A cache block computed for run A should
  not leak into run B; cache keying stays per-run.
- Model tier routing (0030) — this spec doesn't pick cheaper
  models, only trims what we send to whichever model is chosen.
- Retroactive caching on already-running tasks. Ship as an opt-in
  flag; flip fleet-wide after shadow soak.

## Scope

- **Role prompts** — split every role's system prompt into a
  static prefix + task-specific suffix; mark the prefix as
  `cache_control: ephemeral`. Covers PM, Architect, TM,
  Developer, Reviewer.
- **Project context block** — new helper in
  `coder_core.workers.context` that produces the per-run
  context (AGENTS.md + an `active/` subgraph keyed off the
  spec's `affects_*` list, with a `min_freshness=40` floor per
  ADR 0014). Computed once at pipeline-run start, attached to
  every task in the run via `pipeline_run_contexts` (new
  denormalized table).
- **Cache-hit metrics** — extend `TaskRow` with
  `cache_read_input_tokens` + `cache_creation_input_tokens`
  (Anthropic returns these in the response envelope). Feed
  into `/v1/projects/{id}/metrics` as a new `cache_hit_ratio`
  field and a Recharts card on the admin `/metrics` page.
- **Rollout flag** — `settings.prompt_caching_enabled: bool =
  False`. Shadow-soak for 48 h with caching disabled but
  cache-read fields recorded; flip to True fleet-wide after
  the baseline looks clean.

Out of scope for this WIP: 0030 (tier routing), 0031 (budgets),
0032 (regression alerts). Those chain on this one.

## Acceptance criteria

- [x] Every role worker's system prompt is split into
  cache-eligible prefix + task-specific suffix. The prefix
  rides on the `claude` CLI's internal `cache_control` handling
  (we don't construct the API payload directly) — each role
  worker prepends the shared block via
  `coder_core.workers.context.apply_cache_prefix` before writing
  the system-prompt tempfile the CLI reads, gated on the
  effective per-project/global flag.
- [x] A shared per-pipeline-run project context block is built
  once (at pipeline-run creation) and passed to every task in
  that run via the dispatcher (audit log carries `block_hash`
  so sibling byte-identity is grep-able); identical bytes
  produce identical cache keys. Migrations 0032 + 0033 land
  `pipeline_run_contexts` and `tasks.pipeline_run_id`.
- [x] `TaskRow` records `cache_read_input_tokens` and
  `cache_creation_input_tokens`; `/v1/projects/{id}/metrics`
  returns per-role `cache_stats` with `cache_hit_rate`
  (`cache_read / (cache_read + regular_input)`) over the
  requested window.
- [x] Admin `/metrics` page shows a cache-hit-rate table + an
  aggregate `CacheCard` chip on the project overview.
- [x] `settings.prompt_caching_enabled` + per-project
  `projects.prompt_caching_enabled` (migration 0034) gate the
  `cache_control` marker prepend (but not the metric capture —
  metrics stay on so the shadow soak produces a baseline).
- [ ] After 48 h with the flag enabled on a canary project, the
  project's `/metrics` shows ≥40% input-token reduction vs
  its own 7-day pre-enable baseline, with no regression in
  Reviewer approval rate or schema-retry rate (per
  `observability`'s rollup). **Pending canary soak.**
- [x] Documentation: `observability.md` and `task-orchestration.md`
  updated with the new fields and the per-run context behaviour;
  runbook `cache-hit-drop` covers triage for a ratio drop
  (stale prefix, invalidation, prompt rewrite).

## Metrics

- **Primary:** fleet median `cache_hit_ratio` ≥ 0.5 after 7 days
  enabled. Per-project `input_tokens_per_pipeline_run` ≥40%
  below its pre-enable baseline.
- **Guardrails:** Reviewer approval rate within 1 percentage
  point of baseline; `failure_kind="schema"` rate within 10% of
  baseline (i.e. the prompt split didn't corrupt anything).
- **Cost alert:** existing `SLACK_COST_ALERT_THRESHOLD` keeps
  firing as usual; a new `SLACK_CACHE_HIT_FLOOR` (default 0.3)
  fires on per-project rolling-24h cache-hit-ratio below the
  floor, which is the signal that the prefix is invalidating
  every call (prompt drift or a stale AGENTS.md edit loop).

## Open questions

- Does the per-run context block need a min-freshness override
  for pipelines that run against deliberately-stale artifacts
  (e.g. a freshness-audit rewrite task)? Probably yes, as a
  per-task override on the pipeline-chain dispatch; needs design
  thought.
- Anthropic's cache is keyed on exact byte match of the prefix.
  Does `AGENTS.md` drift across projects enough that we want to
  canonicalise whitespace before caching? Probably not — AGENTS.md
  is stable — but worth a check on the canary.
- Where does the project-context block live when a task is
  re-dispatched? If we store the materialised block on
  `pipeline_run_contexts` we pay storage; if we recompute, we
  risk drift. Leaning "store it" — the design should pin this.

## Links

- Designs: [0029 — prompt caching](../../designs/wip/0029-prompt-caching.md)
- Related specs:
  [observability](../active/observability.md) (where the metric lands),
  [task-orchestration](../active/task-orchestration.md) (where the per-run
  context block is created),
  [knowledge-api](../active/knowledge-api.md) (source of the
  `active/` subgraph with freshness filtering),
  [knowledge-freshness](../active/knowledge-freshness.md) (min_freshness
  floor per ADR 0014),
  role workers ([pm-worker](../active/pm-worker.md),
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [developer-worker](../active/developer-worker.md),
  [reviewer-worker](../active/reviewer-worker.md)).
- ROADMAP: Phase 4 — Cost & Token Efficiency (0029–0032);
  0029 is the dependency gate for 0031 (budget gates) and 0032
  (cost regression alerts).
