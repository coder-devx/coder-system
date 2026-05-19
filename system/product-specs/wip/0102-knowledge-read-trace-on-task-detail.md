---
id: '0102'
title: Knowledge-read trace on task detail
type: spec
status: wip
owner: ro
created: '2026-05-18'
updated: '2026-05-18'
last_verified_at: '2026-05-18'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- admin-panel
- task-orchestration
- observability
- knowledge-api
parent: knowledge-and-admin
---

# Knowledge-read trace on task detail

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

Operators auditing whether a worker was properly grounded for a task have no in-app signal. The only source of truth is the raw JSONL transcript in GCS — a file download plus a manual grep. Grounding audits are ad hoc as a result.

The `task_tool_uses` table already captures every Bash invocation (including `gh api` knowledge-repo reads) from the session JSONL — `transcript_parser.py` writes a row per call with `tool_name`, `input_args` (JSON, 4 KiB), `result_bytes`, `is_error`, and `called_at`. The gap is downstream: no API endpoint exposes these rows in a filtered, interpretable form, and the admin panel task detail page renders nothing from them.

## Users / personas

- **System operators** watching the admin panel who want to spot under-grounded tasks (zero reads on a PM draft) or over-reading ones without leaving the browser.
- **The Consultant evaluate loop**, which currently re-parses the full transcript to build a tool-call log — this spec creates the structured surface it should read instead.

## Goals

- Knowledge artifact reads are visible inline on the task detail page for every completed task.
- Operators can confirm which knowledge-repo paths a worker fetched, with response size and error status, without a transcript download.
- A new `tool-uses` API endpoint exposes the filtered rows for programmatic consumers.

## Non-goals

- Not changing what gets captured — `transcript_parser` already writes all Bash calls to `task_tool_uses`. No schema changes to that table.
- Not surfacing source-repo file reads or `gh api search/code` calls — scope is limited to the project's knowledge-repo `system/` paths.
- Not backfilling historical tasks — the card appears only for tasks completed after the feature ships.
- Not replacing the raw transcript download link.

## Scope

- A new `GET /v1/projects/{id}/tasks/{task_id}/tool-uses?kind=knowledge_read` endpoint that filters `task_tool_uses` rows for Bash calls whose `input_args` command matches `gh api repos/.*/coder-system/contents/system/` and returns the extracted path, `result_bytes`, `is_error`, and `called_at` per row.
- A "Knowledge reads" collapsible card on the admin panel task detail page, rendered for all role types, that calls the new endpoint and lists each fetched path with response size and a success/error indicator.
- Per-row deep-link: paths that parse to a known artifact type and id link to the artifact's knowledge browser page within the same project.

## Acceptance criteria

- **AC1.** On any task detail page for a task completed after the feature ships, a "Knowledge reads" card lists every `gh api .../coder-system/contents/system/...` fetch made during the run, showing the artifact path, response size in bytes, and a success/error badge.
- **AC2.** The "Knowledge reads" card renders on task detail pages for all five role types: PM, Architect, Team Manager, Developer, and Reviewer.
- **AC3.** `GET /v1/projects/{id}/tasks/{task_id}/tool-uses?kind=knowledge_read` returns a JSON array of `{path, result_bytes, is_error, called_at}` rows; empty array when none were recorded.
- **AC4.** When a completed task has zero knowledge reads, the card shows a "No reads recorded" empty state rather than being hidden.
- **AC5.** Each path row that resolves to a known artifact type and id deep-links to that artifact's page in the admin knowledge browser (`/projects/{project_id}/{type}/{artifact_id}`).

## Metrics

- Fraction of tasks per role with zero knowledge reads — a lagging grounding-quality indicator, queryable via the new endpoint.

## Open questions

- Should source-repo reads (`gh api` on `coder-core` / `coder-admin`) appear in a second card on the same page? Deferred — this spec establishes the pattern; a follow-on spec can extend `kind=`.
- Should the Consultant evaluate loop switch from transcript re-parse to the new endpoint? The evaluate loop currently reads from a local `critic_input.json` file; migration is outside this spec's scope but the design should note it as the intended path.

## Links

- Related specs: [admin-panel](../knowledge/admin-panel.md), [task-orchestration](../pipeline/task-orchestration.md), [observability](../pipeline/observability.md), [knowledge-api](../knowledge/knowledge-api.md)
