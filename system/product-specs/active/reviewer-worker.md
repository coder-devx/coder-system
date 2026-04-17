---
id: reviewer-worker
title: Reviewer worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-15
last_verified_at: 2026-04-17
served_by_designs: [worker-roles]
related_specs: []
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
- Knowledge read API (conventions, ADRs, designs).
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

## Links

- Designs:
- Related components:
