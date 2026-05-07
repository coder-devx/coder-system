---
id: prompt-caching-architecture
title: Prompt caching & shared context reuse
type: design
status: active
owner: ro
created: '2026-04-18'
updated: '2026-05-06'
last_verified_at: '2026-05-06'
summary: Prompt caching and shared-context reuse across workers.
implements_specs: []
decided_by: []
related_designs:
- worker-roles
- worker-communication
- observability-and-cost-tracking
- pm-worker
- architect-worker
- team-manager-worker
- knowledge-repo-model
affects_services:
- coder-core
- coder-admin
affects_repos:
- coder-core
- coder-admin
parent: pipeline-operations
---
# Prompt caching & shared context reuse

## Context

Every role worker calls `client.messages.create()` with a full prompt
that starts with a stable prefix (role system prompt + AGENTS.md +
relevant `active/` slice) and ends with a task-specific suffix (the
artifact being drafted, the PR diff being reviewed, etc.). Today
every call re-sends the whole thing, so we pay input-token cost on
bytes the model has already read a thousand times.

Anthropic supports prompt caching: mark a prompt block with
`cache_control: {"type": "ephemeral"}` and subsequent calls with the
same prefix get a cache hit (cheaper, faster). Cache lifetime is
~5 min and scoped per organisation + model + exact byte prefix.

Inside one pipeline run, the 5+ tasks (PM draft, Architect design, TM
plan, N developers, Reviewers) are dispatched within minutes of each
other and share the same project context. If we build the context
block once at run start and feed identical bytes into every sibling,
all the sibling calls hit the cache.

## Goals / non-goals

**Goals**
- Opt into Anthropic prompt caching for every role worker.
- Build a per-pipeline-run project context block once; re-use it
  across every sibling task in the run.
- Surface cache-hit ratio as a first-class metric on `/metrics`.
- Ship behind `settings.prompt_caching_enabled` with metric capture
  on during the shadow soak.

**Non-goals**
- Re-architect the dispatcher (0028's `DispatcherQueue` stays as is).
- Output caching.
- Cross-pipeline sharing of the context block — keyed per-run only.
- Model tier routing (0030 chains on this).

## Design

```mermaid
flowchart TB
  subgraph core [coder-core]
    pr[(pipeline_runs)]
    prc[(pipeline_run_contexts)]
    orch[orchestrator]
    ctx[context.build_project_context]
    dispatch[role dispatcher]
    worker[role worker]
    metrics[/metrics API]
    tasks[(tasks)]
  end

  subgraph anthropic [Anthropic API]
    msgs[messages.create]
  end

  subgraph admin [coder-admin]
    dash[/metrics dashboard — cache-hit card]
  end

  orch -->|on pipeline_run create| ctx
  ctx -->|persist materialised block| prc
  orch --> dispatch
  dispatch -->|fetch block| prc
  dispatch -->|build prompt| worker
  worker -->|cache_control: ephemeral on prefix| msgs
  msgs -->|response with cache_*_input_tokens| worker
  worker -->|update| tasks
  tasks --> metrics
  metrics --> dash
```

### Parts

- **Migration: `pipeline_run_contexts`** — one row per
  `pipeline_run`. Columns: `pipeline_run_id PRIMARY KEY`,
  `project_id`, `context_block TEXT NOT NULL` (the
  materialised prefix — AGENTS.md + ordered `active/` subgraph),
  `block_hash TEXT NOT NULL` (sha256 of `context_block`, for
  observability + cheap equality checks), `created_at`.
  Written once at pipeline-run creation; read by every sibling
  task dispatch. Deleted when the pipeline_run row is.
- **`coder_core.workers.context.build_project_context()`** — new
  helper. Inputs: `project_id`, the initiating spec id (needed
  to resolve `affects_*` → an `active/` subgraph). Output:
  `(context_block: str, block_hash: str)`. Uses the Knowledge
  API `min_freshness=40` floor to drop stale artifacts (ADR 0014
  says freshness gates reads; this is one of those reads). Does
  not include the role system prompt — role prompts stay
  per-role.
- **Role prompt split** — every role worker's prompt builder
  changes from:

  ```python
  # before
  messages = [{"role": "user", "content": full_prompt}]
  ```

  to:

  ```python
  # after
  messages = [
      {"role": "user", "content": [
          {"type": "text", "text": role_system_prefix,
           "cache_control": {"type": "ephemeral"}},
          {"type": "text", "text": project_context_block,
           "cache_control": {"type": "ephemeral"}},
          {"type": "text", "text": task_specific_suffix},
      ]},
  ]
  ```

  Two cache breakpoints: role prefix (shared across all tasks
  of this role, fleet-wide) + project context block (shared
  across sibling tasks of this run). The flag
  `settings.prompt_caching_enabled` controls whether the
  `cache_control` keys are emitted; the content structure is
  unchanged either way so the shadow soak is a clean A/B.
- **TaskRow fields** — migration adds
  `cache_read_input_tokens INT NOT NULL DEFAULT 0` and
  `cache_creation_input_tokens INT NOT NULL DEFAULT 0`.
  `parse_claude_json_envelope()` already has the fields in the
  response — just needs to be plumbed to the row write.
- **Metrics API** — `GET /v1/projects/{id}/metrics` gains a
  `cache_hit_ratio: {over_window: 0.0–1.0, by_role: {...}}`.
  Computed as
  `sum(cache_read) / sum(cache_read + regular_input)` over the
  `period` window, with a per-role breakdown. The existing
  `daily_cost` already sums input tokens — same scan, extra
  aggregate.
- **Admin `/metrics` card** — Recharts pie or gauge showing the
  fleet / per-project cache-hit ratio with a 7-day sparkline.
  Lives next to the daily-cost chart (same design system, same
  data source).
- **Slack alert** — new env-var
  `SLACK_CACHE_HIT_FLOOR=0.3` (default). Checked on the same
  post-task hook that already fires
  `SLACK_COST_ALERT_THRESHOLD`. Per-project rolling-24h
  cache-hit ratio below floor → alert. Same in-memory 1-per-hour
  rate-limit as the cost alert.

### Data flow

**Pipeline-run creation (happy path):**

1. `POST /v1/projects/{id}/pipeline-runs` — orchestrator
   creates the `pipeline_run` row (existing).
2. Orchestrator calls
   `build_project_context(project_id, spec_id)`. That:
   a. Reads AGENTS.md from the project repo (cached in-memory
      on the coder-core process, revalidated by git SHA per
      poll).
   b. Resolves the spec's `affects_specs`/`affects_designs` to
      an `active/` subgraph via the Knowledge API with
      `min_freshness=40`.
   c. Concatenates in a stable order: AGENTS.md, then specs in
      alpha order by slug, then designs in alpha order.
   d. Returns `(block, sha256(block))`.
3. Orchestrator inserts the block into `pipeline_run_contexts`.
4. Orchestrator emits the usual `pipeline_run.changed` SSE
   event (existing).

**Role task dispatch:**

1. Pipeline chain creates a task for role R (existing).
2. Role R's worker loader reads the `pipeline_run_contexts`
   row by `pipeline_run_id` (new, one extra query per task
   start).
3. Worker calls `anthropic.messages.create` with the two
   `cache_control`-marked blocks (role prefix + project context)
   then the task-specific suffix.
4. Anthropic response envelope carries
   `cache_read_input_tokens`, `cache_creation_input_tokens`,
   `input_tokens`, `output_tokens`. Worker writes all four to
   the `tasks` row on completion.
5. Post-task hook runs existing cost threshold check plus
   new cache-hit-floor check.

### Invariants

- **Byte-identical prefix across siblings.** Two tasks in the
  same `pipeline_run_id` always send the same
  `project_context_block` bytes. Without this the cache is
  useless. Enforced by storing the materialised block in
  `pipeline_run_contexts` instead of recomputing.
- **Role prefix is per-role, not per-project.** The role system
  prompt is the same across every project — so cache hits
  amortise across tenants. No project-specific content in the
  role prefix.
- **Metric capture runs unconditionally.** The
  `prompt_caching_enabled` flag gates `cache_control`
  emission but not the response-envelope parsing; both
  `cache_read_input_tokens` and `cache_creation_input_tokens`
  are recorded whether or not caching is on. Shadow soak
  establishes the baseline.
- **`min_freshness=40` floor is a request parameter, not a
  hard rule.** A future freshness-audit task might need to read
  a stale artifact to fix it — the per-run context builder
  accepts a per-pipeline-run freshness-floor override
  (`freshness_floor_override: int | None`) that the
  pipeline-chain dispatcher can set when initiating an
  explicit rewrite run.
- **Cache expiry is OK.** Anthropic's ~5 min TTL is shorter
  than a typical pipeline run (spec → design → plan can span
  hours). Each task still gets a hit against the immediately-
  prior sibling's write, and in aggregate the hit ratio stays
  high because sibling tasks dispatch within the TTL of each
  other. We do not try to pre-warm or keep-alive.

## Open questions

- Should role prefixes go through a versioning field so a
  deliberate prompt change doesn't produce a silent cache miss
  without a metric? Cheap option: include a
  `ROLE_PROMPT_VERSION` constant per role that's just a bump
  discipline; the ratio-drop still shows on the metric, it's
  just labelled.
- `pipeline_run_contexts.context_block` can be large (30–80 KB
  typical). Storing this verbatim per run is fine storage-wise
  but noisy in backups. Worth an evaluation: per-block
  deduplication via `block_hash` (a separate
  `project_context_blocks` table keyed by hash, the run row
  points to it). Leaning "not yet" — simpler first, dedupe
  later if the storage footprint actually hurts.
- Per-role cache-hit-ratio breakdown on the admin card: nice
  to have, but might be noise during the shadow soak.
  Ship the aggregate first, add per-role breakdown after the
  baseline is readable.

## Rollout

Four phases, each gated on the prior holding for 48 h.

**Phase 1 — schema + metric capture (flag off, `cache_control`
off). LANDED.** Migration 0022 added
`tasks.{cache_read,cache_creation}_input_tokens`, migration
0032 added `pipeline_run_contexts`. Worker already writes cache
counters from the response envelope; `/metrics` exposes per-role
`cache_stats` with `cache_hit_rate`.

**Phase 2 — context builder on, `cache_control` off. LANDED.**
Orchestrator calls `build_project_context` at pipeline-run
creation and persists the block. Migration 0033 added
`tasks.pipeline_run_id`; dispatcher stamps `WorkerInput.project_context_block`
+ `_block_hash` and logs the hash so sibling byte-identity is
grep-able. `coder_core.workers.context.apply_cache_prefix` is
wired into all 5 role workers but no-ops while the effective
flag is False.

**Phase 3 — canary enable. DONE (2026-04-19).** Migration 0034
added `projects.prompt_caching_enabled` (nullable tri-state).
Canary flipped on the `coder` project via one-shot Cloud Run Job
(`UPDATE projects SET prompt_caching_enabled=true WHERE id='coder'`).
`coder`'s `/metrics` cache_stats started registering cache_read
tokens immediately — verdict deferred to the fleet measurement
window below.

**Phase 4 — fleet enable. DONE (2026-04-19).**
`PROMPT_CACHING_ENABLED=true` landed on `coder-core-00115-vhp`
along with `REGRESSION_ALERTS_ENABLED=true`. Every project now
prepends the shared context block. `SLACK_CACHE_HIT_FLOOR` still
0 — operators should set it to 0.3 once the first week of data
defines the fleet-median hit rate and the natural invalidation
cadence (AGENTS.md edits, role-prompt rewrites). The alert
resolves per-project override before firing so a canary carve-out
and a fleet project don't silence each other. Runbook
[cache-hit-drop](../../runbooks/cache-hit-drop.md) documents
triage.

**Backout plan.** Set `prompt_caching_enabled = False` — the
`cache_control` keys drop out, Anthropic returns the same
responses at higher cost. No migration, no data rewrite; the
context block stays persisted (benign) and `cache_*_input_tokens`
return to 0. Expected backout time: one config flip, <1 min.

## Links

- Specs: [0029 — prompt caching](../../product-specs/wip/0029-prompt-caching.md),
  [observability](../../product-specs/active/observability.md),
  [task-orchestration](../../product-specs/active/task-orchestration.md).
- ADRs: [0014 — freshness from declared affects](../../adrs/0014-freshness-from-declared-affects.md)
  (the context block reads through the freshness floor).
- Services: coder-core (worker prompt builders, orchestrator,
  migration, metrics API), coder-admin (metrics card).
- Related designs: [observability-and-cost-tracking](../active/observability-and-cost-tracking.md)
  (the `tasks` row + metrics rollup it extends),
  [worker-roles](../active/worker-roles.md),
  [worker-communication](../active/worker-communication.md)
  (dispatch path that reads `pipeline_run_contexts`),
  [pm-worker](../active/pm-worker.md),
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md).
