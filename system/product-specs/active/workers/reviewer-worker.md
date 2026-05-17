---
id: reviewer-worker
title: Reviewer worker
type: spec
status: active
owner: ro
created: '2026-04-11'
updated: '2026-05-14'
last_verified_at: '2026-05-14'
summary: Reviewer worker — technical-quality gate before PM acceptance.
served_by_designs:
- worker-roles
related_specs: []
parent: worker-roles
---
# Reviewer worker

## What it is

The reviewer worker is the automated code-review role in `coder-core`.
Given a `role=reviewer` task carrying a PR URL from the developer, it
fetches the diff, loads the target project's conventions, ADRs, and
designs from the knowledge API, and submits a grounded approve or
request-changes verdict on GitHub. It is the first gate between a
developer-produced PR and a human-facing merge decision.

## Capabilities

- Runs as a `claude` subprocess following the developer worker's
  pattern, with a built-in system prompt that instructs it to
  `gh pr diff <url>`, load conventions/ADRs/designs, analyze the diff
  against them, and submit via `gh pr review <url>`.
- When the developer task references a spec, loads the spec's subgraph
  via a single graph fetch (`depth=1, edge_types=served_by_designs`)
  to ground the review in the designs the spec is served by. Falls
  back to direct spec fetch when `CODER_KNOWLEDGE_GRAPH_ENABLED` is
  off. Initial conversion ships with `min_freshness` omitted.
- Review is grounded: comments cite specific conventions or ADR
  decisions rather than generic style notes.
- Posts structured inline comments on the PR and submits a formal
  verdict (not just comments) — approve or request-changes.
- Persists `review_verdict` and `review_url` onto the task row so the
  orchestrator can branch on the outcome.
- Verdict messages feed the orchestrator's stage transitions and
  surface as `feedback` in the developer's fix-loop prompt when
  changes are requested.
- **Transient-failure retry.** The claude spawn is wrapped in the
  shared `run_with_transient_retry` helper (spec 0027); Anthropic
  transport blips retry inside the worker up to the configured
  budget before surfacing as `failure_kind="transient"`.
- **Ship attestation (ship-mode).** On `role=reviewer` tasks run in
  ship-mode, the worker swaps its JSON schema for `reviewer_ship.json`
  and must emit a `ship_attestation` block that pairs every acceptance
  criterion of the shipping WIP with either a target `active/` artifact
  + section or an explicit drop reason. Shape errors re-prompt through
  the spec 0025 `validate_and_retry` gate; an `approve` verdict without
  a compliant attestation is rejected by the schema. The attestation
  is the left-hand half of the admin ship-gate panel and the payload
  the orchestrator POSTs to `/knowledge/ship`.
- **Security analysis pass.** Every reviewer run executes a structured
  security analysis pass over the PR diff, aligned to OWASP Top 10
  categories plus credential-exposure patterns (hardcoded secrets,
  logging of sensitive values). Findings are emitted as
  `security_findings` in the structured output — each entry carries
  `severity` (`critical` | `high` | `medium` | `low`), `category`,
  `file`, `line`, and `description`. `critical`-severity findings
  unconditionally escalate the verdict to `request-changes`; the
  `approve` path requires `security_findings` to contain no `critical`
  entries (schema-enforced). Findings surface as `[security][severity]`
  inline PR comments on the offending lines, distinct from convention
  comments. The role prompt at `system/roles/reviewer/tasks/review.md`
  contains an explicit "Security analysis" section listing OWASP-aligned
  check categories.
- **Performance analysis pass.** Every reviewer run executes a
  structured performance analysis pass covering N+1 query patterns,
  missing index hints on hot paths, unbounded pagination, and
  algorithmic complexity regressions (Python/SQL scope). Findings are
  emitted as `performance_findings` with the same per-entry shape as
  security findings. Performance findings post `[performance]` inline
  PR comments but do not change an `approve` verdict to
  `request-changes`. The role prompt at
  `system/roles/reviewer/tasks/review.md` contains a "Performance
  analysis" section listing query, pagination, and complexity patterns.
- **Finding counts persisted.** The orchestrator writes
  `security_finding_count` and `performance_finding_count` to task
  metadata on reviewer-task completion so the admin panel task detail
  can display them.

## Interfaces

- **Consumes:** tasks with `role=reviewer`, a PR URL in the prompt,
  and `project_id` for knowledge scoping.
- **Produces:** GitHub PR review (approve | request-changes) with
  inline comments; writes `review_verdict`, `review_url`,
  `security_finding_count`, and `performance_finding_count` back to
  the task.
- **Schema:** `reviewer.json` — includes `security_findings` and
  `performance_findings` arrays with severity-tagged finding objects;
  schema enforces that `approve` requires `security_findings` to
  contain no `critical` entries.
- **Code:** `src/coder_core/workers/reviewer.py`; prompt at
  `system/roles/reviewer.md`.

## Dependencies

- Developer worker (source of the PR URL).
- Knowledge read API (conventions, ADRs, designs; via graph endpoint
  when `CODER_KNOWLEDGE_GRAPH_ENABLED`, direct fetch otherwise).
- GitHub App token for `gh pr diff` / `gh pr review`.
- Reviewer-role service account + Anthropic key broker.
- Orchestrator for stage routing and fix-loop triggering.

## Evolution

- 0009 — `workers/reviewer.py`, `review_verdict` and `review_url`
  columns (migration 0009), knowledge-grounded reviews, first live
  review caught a real convention violation on
  `coder-devx/coder-core#2`.
- 0027 — transient-failure retry around the claude spawn via the
  shared classifier + retry wrapper.
- 0044 — ship-mode reviewer schema (`reviewer_ship.json`) with
  required `ship_attestation`; the worker loads the ship schema when
  the task carries the ship-mode flag and enforces AC coverage via
  the 0025 `validate_and_retry` gate. Non-ship reviews keep the
  existing schema unchanged.
- 0055 — `GH_TOKEN` injection routed through the shared
  `_github_env.apply_github_token_env` helper. Reviewer worker
  prefers `task.workspace.github_token` when a workspace is
  prepared and falls back to the dispatcher-resolved
  `WorkerInput.github_token` otherwise — `gh pr diff` /
  `gh pr review` keep working when reviewer tasks dispatch without
  a workspace.
- 0046 — spec-context load converted from direct spec fetch to a
  single graph fetch when a developer task references a spec:
  `depth=1, edge_types=served_by_designs`; `min_freshness` omitted
  on initial conversion. Falls back to direct fetch when
  `CODER_KNOWLEDGE_GRAPH_ENABLED` is off.
- 0065 — reviewer scope cut + turn cap. ``--max-turns 30`` enforced via ``worker_max_turns_reviewer`` (coder-core#160); ``failure_kind=turn_cap_exceeded`` written by the dispatcher and rendered as a distinct chip in the admin panel (coder-admin#17). Reviewer task contract in ``system/roles/reviewer/tasks/review.md`` rewritten to constrain scope to pre-loaded diff + ACs + edge-cases + CI report (no free-form repo browsing). 7-day reviewer turn-count and cost metrics are tracked on the observability dashboard for post-soak verification.
- 0094 — security and performance analysis passes. `reviewer.json`
  schema gains `security_findings` and `performance_findings` arrays
  with severity-tagged finding objects; `approve` path schema-enforces
  no `critical` security findings. `critical` findings escalate to
  `request-changes`; findings post tagged inline PR comments
  (`[security][severity]`, `[performance]`). Role prompt at
  `system/roles/reviewer/tasks/review.md` gains explicit "Security
  analysis" (OWASP-aligned categories) and "Performance analysis"
  (query/pagination/complexity patterns) sections. Orchestrator
  persists `security_finding_count` and `performance_finding_count`
  to task metadata.

## Links

- Designs: [worker-roles](../../../designs/active/worker-roles.md)
- Related components: [developer-worker](./developer-worker.md),
  [pm-worker](./pm-worker.md), [knowledge-api](../knowledge/knowledge-api.md),
  [task-orchestration](../pipeline/task-orchestration.md),
  [service-accounts](../tenancy/service-accounts.md)
