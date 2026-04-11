---
id: "0009"
title: Reviewer worker v1
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0004", "0010"]
---

# Reviewer worker v1

**Phase:** Shipped
**Progress:** 7 / 7 acceptance criteria ✅

## Problem

The developer worker produces code and opens PRs, but no automated
review catches convention violations or quality issues before the human
sees the PR. Review is entirely manual, which slows the loop and lets
bad patterns slip through.

## Users / personas

- **Human operator** — needs high-quality PRs that already pass a
  convention and ADR check before requiring their attention.
- **Developer worker** — benefits from fast feedback so fix loops can
  close before the human is involved.

## Goals

- Automated review on every developer PR: fetch diff, load project
  knowledge, post structured comments, submit approve or request-changes.
- Review grounded in the project's own conventions and ADRs, not just
  general style.

## Non-goals

- Replacing human review for security-sensitive changes.
- Running tests or linting (separate from review).
- Reviewing PRs from sources other than the developer worker.

## Scope

A `reviewer` worker that:

1. Receives a task with `role=reviewer` and a PR reference.
2. Fetches the PR diff via `gh pr diff`.
3. Loads the project's conventions, ADRs, and designs from the knowledge API.
4. Calls Claude to produce structured review comments.
5. Posts comments and submits approve or request-changes via `gh pr review`.
6. Stores `review_verdict` and `review_url` on the task row.

## Acceptance criteria

- [x] AC1: A task with `role=reviewer` runs the reviewer worker instead
  of the developer worker.
- [x] AC2: The reviewer fetches the full PR diff and loads project
  knowledge (conventions, ADRs, designs) before calling Claude.
- [x] AC3: Claude's review is grounded in the loaded knowledge — comments
  reference specific conventions or ADR decisions.
- [x] AC4: The reviewer posts structured inline comments on the PR via
  the GitHub API.
- [x] AC5: The reviewer submits an approve or request-changes verdict
  (not just comments) on the PR.
- [x] AC6: `review_verdict` and `review_url` are stored on the task row
  after the review completes.
- [x] AC7: At least one live review on a real PR catches a real
  convention violation.

## What shipped

`workers/reviewer.py` following the developer subprocess pattern.
System prompt instructs Claude to `gh pr diff`, load conventions via
the knowledge API, analyze against ADRs and designs, and submit via
`gh pr review`. Migration 0009 adds `review_verdict` and `review_url`
columns to the tasks table. Live review on
[coder-devx/coder-core#2](https://github.com/coder-devx/coder-core/pull/2)
caught a real convention violation. 12 new tests.

## Links

- Related specs: [`0004`](./0004-developer-worker-v1.md), [`0010`](./0010-task-orchestration-v1.md)
