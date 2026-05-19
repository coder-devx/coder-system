---
id: 0099
title: Worker Knowledge-Read Transparency
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
- knowledge-api
- observability
parent: knowledge-and-admin
---

# Worker Knowledge-Read Transparency

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

Operators reviewing a completed worker run have no quick way to verify that the worker fetched the right knowledge artifacts before emitting its output. The PM task contract requires at least one source-repo PR query and at least one knowledge-repo path fetch before a draft is valid — the `consultant evaluate` loop checks this signal and marks zero-fetch drafts as `bad`. Today the only way to see what a worker fetched is to download the raw transcript JSONL and scan for `gh api repos/.../contents/...` Bash calls by hand. For a PM or Architect task with 20+ turns that is several minutes of archaeology per task.

The consequence: operators cannot quickly flag ungrounded worker output for retry, and the consultant evaluate loop can see grounding quality while operators using the admin panel cannot.

## Users / personas

Operators watching the pipeline and task views — specifically when reviewing completed PM, Architect, and Reviewer tasks where grounding quality determines output validity.

## Goals

- Knowledge-repo artifact reads made by a worker are visible on the task detail page — path, HTTP status, byte size, and timestamp — without downloading the transcript.
- Tasks where the worker made zero knowledge-repo reads are surfaced explicitly so the operator knows grounding did not happen, not that the panel failed to load.
- The fetch count is visible at task-summary level so operators can triage across pipeline tasks without opening each one.

## Non-goals

- Real-time streaming of knowledge reads during an in-flight task.
- Showing the full content of fetched artifacts inline.
- Role-specific required-fetch-count rules or automated grounding-quality scoring in the admin panel (that belongs in the consultant evaluate loop).
- Capturing reads made outside a task context (admin panel reads, cron jobs).

## Scope

Two surfaces in `coder-admin` change:

1. **Task detail page** (`/projects/:id/pipeline/:taskId`) — a new collapsible "Knowledge reads" panel, placed below existing task metadata and above the transcript download link. Lists each `gh api repos/.../contents/...` call the worker made: path, HTTP status, byte size, and timestamp. Zero-read state shows an explicit "No knowledge reads recorded" message.
2. **Task list row** — a knowledge-read count badge (e.g., "3 reads") visible per row in the pipeline task list without opening the detail page.

The backend already records these in `task_tool_uses` (Bash tool calls with `gh api` in `input_args`). No new backend endpoints are required for the first version; `coder-admin` queries the existing `GET /tasks/{task_id}/tool-uses` endpoint and filters client-side for `gh api repos/.../contents/...` calls.

## Acceptance criteria

- **AC1.** On the task detail page for any completed PM, Architect, or Reviewer task, a "Knowledge reads" section lists every `gh api repos/.../contents/...` call the worker made during the run, showing path, HTTP status, and timestamp — visible without downloading the transcript.
- **AC2.** When a completed task has zero `gh api repos/.../contents/...` calls recorded, the "Knowledge reads" section displays an explicit "No knowledge reads recorded" message rather than an empty or missing section.
- **AC3.** Each row in the pipeline task list shows a knowledge-read count badge (e.g., "3 reads" or "0 reads") for PM, Architect, and Reviewer tasks, visible without opening the detail page.
- **AC4.** The "Knowledge reads" section is collapsible — it defaults to expanded and collapses on user interaction; the collapsed/expanded state persists for the browser session.
- **AC5.** The feature is covered by at least one Playwright or React Testing Library test asserting the section renders correctly for a mocked task with multiple reads and for a mocked zero-read task.

## Metrics

- Share of PM/Architect/Reviewer task detail views that have at least one knowledge-read entry visible within 60 days of ship — baseline: 0 (feature does not exist today).

## Open questions

- Should the badge appear on Developer and Team Manager task rows too? Those roles are not grounding-constrained but a non-zero badge may still aid debugging. Defaulting to all roles unless the admin-panel spec imposes a hard UI constraint.
- Does `GET /tasks/{task_id}/tool-uses` paginate? If tool-use counts are large enough to hit a page limit, client-side filtering may miss reads from later transcript turns — confirm with backend before shipping.

## Links

- Parent category design: knowledge-and-admin
- Related spec: admin-panel (task detail page shape)
- Related spec: knowledge-api (read-through layer the feature queries)
- Related spec: observability (per-task telemetry; grounding-fetch count is a natural extension)
