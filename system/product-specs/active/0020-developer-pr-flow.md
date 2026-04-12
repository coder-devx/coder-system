---
id: "0020"
title: "Developer PR flow"
type: spec
status: active
owner: ro
created: "2026-04-12"
updated: "2026-04-12"
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0004", "0009", "0010", "0012"]
---

# Developer PR flow

**Phase:** active
**Progress:** 7 / 7 acceptance criteria

## Problem

The developer worker writes code in a temporary workspace clone that gets cleaned
up after the task finishes. No branch is created, no PR is opened, no code
persists. The `result` field contains a text description of what was done but the
actual code changes are lost. This means the entire pipeline is a simulation —
developer tasks "succeed" but produce no shippable artifact.

The reviewer worker has nothing real to review (no PR diff to fetch, no GitHub
review to post). The merge endpoint (spec 0012) has nothing to merge. The CD
pipeline (spec 0011) has nothing to deploy.

## Users / personas

- **Pipeline orchestrator** — needs developer tasks to produce a mergeable PR
  so the reviewing and acceptance stages have a concrete artifact.
- **Operators** — need to see the PR URL in the admin panel and click through
  to GitHub to inspect the diff.
- **Reviewer worker** — needs a real PR to `gh pr diff` and `gh pr review`.

## Goals

- Developer worker creates a feature branch, commits changes, pushes, and opens
  a PR via `gh pr create` — all within the existing workspace clone.
- The PR URL is captured from the worker output and stored on the task row
  (new `pr_url` column) so the admin UI and reviewer can reference it.
- The reviewer worker receives the PR URL in its prompt and reviews the actual
  PR on GitHub.
- On reviewer approve, the existing merge endpoint (spec 0012) merges the PR.
- Failed/abandoned branches are cleaned up (or left for manual inspection).

## Non-goals

- Multi-PR tasks (one task = one PR).
- Draft PRs or PR templates — keep it simple.
- Automatic merge on approve (the merge endpoint already handles this; chaining
  is spec 0021's scope).
- Rebasing or conflict resolution — if the branch can't be pushed, the task
  fails and the operator retries.

## Scope

**Branch naming:** `task/{task_id}` (short enough for GitHub, unique per task).

**Developer system prompt changes:** instruct Claude to create a branch, commit
with a descriptive message, push, and open a PR. The PR title should include the
task prompt summary. The PR body should summarize what changed and reference the
spec/task.

**Worker result parsing:** after the developer run, extract the PR URL from the
claude output. Store it on a new `pr_url` column on the task row.

**Reviewer prompt enhancement:** when dispatching the reviewing stage, include
the PR URL in the reviewer's prompt so it can `gh pr diff <url>` and
`gh pr review <url>`.

**Workspace module:** the clone already has push access via the GitHub App
installation token. Verify that `gh` CLI auth works in the workspace (set
`GH_TOKEN` — already done for reviewer).

**New column:** `pr_url` (String 500, nullable) on tasks, migration 0016.

## Acceptance criteria

- [x] AC1: Developer worker creates a branch named `task/{task_id}`, commits
  all changes, and pushes to the remote. The branch is visible on GitHub after
  the task completes.
- [x] AC2: Developer worker opens a PR via `gh pr create` with a structured
  title and body. The PR URL appears in the worker's result text.
- [x] AC3: The dispatcher extracts the PR URL from the developer result and
  stores it in `tasks.pr_url`. The field appears in `TaskRead` responses.
- [x] AC4: When the orchestrator dispatches the reviewing stage, the reviewer's
  prompt includes the PR URL so the reviewer can `gh pr diff` and
  `gh pr review` against the real PR.
- [x] AC5: When the reviewer approves, the PR is ready to merge via the
  existing `POST /tasks/{id}/merge` endpoint (spec 0012 AC5).
- [x] AC6: If the developer worker fails to push or create a PR (e.g. auth
  error, conflict), the task fails with a clear error message rather than
  silently succeeding with no artifact.
- [x] AC7: Migration 0016 adds `pr_url` (nullable String 500) to the tasks
  table and the column appears in `TaskRead` responses.

## Open questions

- Branch cleanup on failure: delete remote branch, or leave for debugging?
  Proposed: leave for 24h, then GC via a scheduled job (future spec).
- PR labels: add a `coder-bot` label? Proposed: yes, easy to filter in GitHub.

## Links

- Developer worker: spec 0004
- Reviewer worker: spec 0009
- Task orchestration: spec 0010
- Merge endpoint: spec 0012 AC5
- Workspace module: `src/coder_core/workers/workspace.py`
- Developer worker: `src/coder_core/workers/developer.py`
- Developer system prompt: `system/roles/developer.md`
