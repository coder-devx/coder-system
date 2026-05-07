---
id: reviewer-worker
title: Reviewer worker
type: spec
status: active
owner: ro
created: '2026-04-11'
updated: '2026-05-07'
last_verified_at: '2026-05-07'
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

## Interfaces

- **Consumes:** tasks with `role=reviewer`, a PR URL in the prompt,
  and `project_id` for knowledge scoping.
- **Produces:** GitHub PR review (approve | request-changes) with
  inline comments; writes `review_verdict` and `review_url` back to
  the task.
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
- 0065 — reviewer scope cut + turn cap. ``--max-turns 30`` enforced via ``worker_max_turns_reviewer`` (coder-core#160); ``failure_kind=turn_cap_exceeded`` written by the dispatcher and rendered as a distinct chip in the admin panel (coder-core#163, coder-admin#17). Reviewer task contract in ``system/roles/reviewer/tasks/review.md`` rewritten to constrain scope to pre-loaded diff + ACs + edge-cases + CI report (no free-form repo browsing). 7-day reviewer turn-count and cost metrics are tracked on the observability dashboard for post-soak verification.


## Links

- Designs: [worker-roles](../../designs/active/worker-roles.md)
- Related components: [developer-worker](./developer-worker.md),
  [pm-worker](./pm-worker.md), [knowledge-api](./knowledge-api.md),
  [task-orchestration](./task-orchestration.md),
  [service-accounts](./service-accounts.md)
