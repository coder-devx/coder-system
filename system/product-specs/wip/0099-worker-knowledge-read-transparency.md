---
id: 0099
title: Worker Knowledge-Read Transparency
type: spec
status: wip
owner: ro
created: '2026-05-18'
updated: '2026-05-19'
last_verified_at: '2026-05-19'
deprecated_at: null
reason: null
served_by_designs:
- '0099'
related_specs:
- admin-panel
- knowledge-api
- observability
- task-orchestration
parent: knowledge-and-admin
---

# Worker Knowledge-Read Transparency

**Phase:** wip
**Progress:** 0 / 7 acceptance criteria

> Consolidated 2026-05-19 from a cluster of seven near-duplicate WIP specs (0097–0103)
> that the founder/PM calibration loop emitted over 2026-05-18. 0097, 0098, 0100, 0101,
> 0102, 0103 are deprecated; 0099 is the canonical spec. The merged AC set below
> preserves the distinct contributions of each: dual-source capture (0098, 0100),
> deep-link to artifact page (0100, 0102), tenant isolation (0101), pipeline-row
> badge (0099, 0103), and explicit empty state (all seven).

## Problem

Operators reviewing a completed worker run have no quick way to verify that the worker fetched the right knowledge artifacts before emitting its output. The PM task contract requires at least one source-repo PR query and at least one knowledge-repo path fetch before a draft is valid — the `consultant evaluate` loop checks this signal and marks zero-fetch drafts as `bad`. Today the only way to see what a worker fetched is to download the raw transcript JSONL and scan for `gh api repos/.../contents/...` Bash calls by hand. For a PM or Architect task with 20+ turns that is several minutes of archaeology per task.

The consequence: operators cannot quickly flag ungrounded worker output for retry, and the consultant evaluate loop can see grounding quality while operators using the admin panel cannot.

## Users / personas

- **Pipeline operators** on the admin panel task detail page reviewing completed PM, Architect, and Reviewer tasks where grounding quality determines output validity.
- **Automated grounding-quality tooling** (future spec) and the existing `consultant evaluate` loop, which currently re-parse the full transcript and could read from a structured surface instead.

## Goals

- Knowledge-repo artifact reads made by a worker are visible on the task detail page — path, HTTP status, byte size, and timestamp — without downloading the transcript.
- Tasks where the worker made zero knowledge-repo reads are surfaced explicitly so the operator knows grounding did not happen, not that the panel failed to load.
- The fetch count is visible at task-summary level so operators can triage across pipeline tasks without opening each one.
- Each fetched artifact path is navigable to its detail view in the knowledge browser so operators can verify the artifact body in one click.

## Non-goals

- Real-time streaming of knowledge reads during an in-flight task.
- Showing the full content of fetched artifacts inline.
- Role-specific required-fetch-count rules or automated grounding-quality scoring in the admin panel (that belongs in the consultant evaluate loop).
- Capturing reads made outside a task context (admin panel reads, cron jobs).
- Retroactive backfill for tasks that completed before this feature ships.
- Tracking non-knowledge `gh api` calls (PR listing, `search/code`, source-repo file reads).

## Scope

Two surfaces in `coder-admin` change:

1. **Task detail page** (`/projects/:id/pipeline/:taskId`) — a new collapsible "Knowledge reads" panel, placed below existing task metadata and above the transcript download link. Lists each `gh api repos/.../contents/...` call the worker made: path, HTTP status, byte size, and timestamp. Each path that resolves to a known artifact (`{type, id}`) is a clickable deep-link to that artifact's page in the project's admin knowledge browser. Zero-read state shows an explicit "No knowledge reads recorded" message.
2. **Task list row** — a knowledge-read count badge (e.g., "3 reads") visible per row in the pipeline task list without opening the detail page.

The backend already records these in `task_tool_uses` (Bash tool calls with `gh api` in `input_args`). No new backend endpoints are required for the first version; `coder-admin` queries the existing `GET /tasks/{task_id}/tool-uses` endpoint and filters client-side for `gh api repos/.../contents/...` calls. The endpoint is project-scoped (`/v1/projects/{id}/tasks/...`), giving tenant isolation by construction.

## Acceptance criteria

- **AC1.** On the task detail page for any completed PM, Architect, or Reviewer task, a "Knowledge reads" section lists every `gh api repos/.../contents/...` call the worker made during the run, showing path, HTTP status, byte size, and timestamp — visible without downloading the transcript.
- **AC2.** When a completed task has zero `gh api repos/.../contents/...` calls recorded, the "Knowledge reads" section displays an explicit "No knowledge reads recorded" message rather than an empty or missing section.
- **AC3.** Each row in the pipeline task list shows a knowledge-read count badge (e.g., "3 reads" or "0 reads") for PM, Architect, and Reviewer tasks, visible without opening the detail page. The badge is suppressed for legacy tasks predating capture (badge value `null`).
- **AC4.** The "Knowledge reads" section is collapsible — defaults to expanded; collapsed/expanded state persists per task in the browser session under `sessionStorage` key `kr-expanded-{taskId}`.
- **AC5.** Each entry whose path resolves to a known artifact (`{type, id}` parseable from the path against the project's knowledge browser routes) renders as a clickable deep-link to `/projects/{project_id}/{type}/{artifact_id}`; paths that don't resolve render as plain text.
- **AC6.** A task that belongs to project A is not visible from project B's task detail URL — `GET /v1/projects/{B}/tasks/{taskA_id}/tool-uses` returns 404 (tenant isolation, asserted by an integration test).
- **AC7.** The feature is covered by at least one Playwright or React Testing Library test asserting the section renders correctly for a mocked task with multiple reads and for a mocked zero-read task.

## Metrics

- Share of PM/Architect/Reviewer task detail views that have at least one knowledge-read entry visible within 60 days of ship — baseline: 0 (feature does not exist today).
- Operator transcript downloads (`GET /tasks/{id}/transcript`) correlated with tasks that have ≥ 1 recorded knowledge read drop measurably within two weeks of ship.

## Open questions

- Should the badge appear on Developer and Team Manager task rows too? Those roles are not grounding-constrained but a non-zero badge may still aid debugging. Defaulting to all roles unless the admin-panel spec imposes a hard UI constraint.
- Does `GET /tasks/{task_id}/tool-uses` paginate? If tool-use counts are large enough to hit a page limit, client-side filtering may miss reads from later transcript turns — confirm with backend before shipping.
- For tasks predating `task_tool_uses` capture (gh api parsing was added on a specific date), should the panel render a "Capture unavailable for this task" notice rather than the zero-read empty state? AC3 suppresses the badge for `null` counts; AC2's empty state assumes capture was attempted.

## Links

- Parent category design: knowledge-and-admin
- Design: [0099 — Worker Knowledge-Read Transparency](../../designs/wip/0099-worker-knowledge-read-transparency.md)
- Related spec: [admin-panel](../active/knowledge/admin-panel.md) (task detail page shape)
- Related spec: [knowledge-api](../active/knowledge/knowledge-api.md) (read-through layer the feature queries)
- Related spec: [observability](../active/pipeline/observability.md) (per-task telemetry; grounding-fetch count is a natural extension)
- Related spec: [task-orchestration](../active/pipeline/task-orchestration.md) (`task_tool_uses` write path)
- Superseded specs: [0097](../deprecated/0097-worker-knowledge-pull-visibility-on-task-detail.md), [0098](../deprecated/0098-worker-knowledge-read-log-in-task-detail.md), [0100](../deprecated/0100-worker-knowledge-reads-inline-on-task-detail.md), [0101](../deprecated/0101-task-knowledge-read-trace.md), [0102](../deprecated/0102-knowledge-read-trace-on-task-detail.md), [0103](../deprecated/0103-knowledge-reads-panel-on-task-detail.md)
