---
id: '0100'
title: Worker knowledge reads inline on task detail
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

# Worker knowledge reads inline on task detail

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

Operators auditing grounding quality need to know which knowledge artifacts a worker actually fetched during a task run — the spec bodies, design files, and role docs the worker pulled via `gh api` before producing its output. Today the only signal is the full task transcript, buried behind a GCS download and requiring manual scanning for `gh api` invocations. On a 150-turn PM draft run this takes minutes and does not scale as fleet size grows. The backend already records knowledge reads in the `knowledge_lookups` table (path, cache vs. live, byte count per artifact) and exposes them at `GET /v1/projects/{id}/tasks/{task_id}/knowledge-lookups`, but the admin panel task detail page does not consume this endpoint — operators cannot see the read list inline.

## Users / personas

Operators using the admin panel to audit grounding quality — specifically when a spec comes back `needs_rewrite` from the audit pipeline or a developer PR misses the spec's scope, and the operator wants to confirm in seconds whether the worker read the right artifacts before acting.

## Goals

- The admin panel task detail page shows which artifact paths the worker pulled, with a cache vs. live indicator and byte count, without requiring a transcript download.
- Operators can verify in under 30 seconds whether a worker read its expected grounding artifacts (parent-category spec, routed siblings).
- The read order is chronological so operators can follow the worker's context-building sequence.

## Non-goals

- Changing how reads are captured — the `knowledge_lookups` table and its write path are out of scope.
- Surfacing all tool calls — the existing tool-uses tab covers the raw transcript view.
- Scoring or alerting on grounding quality — that is a separate feature.
- Reads that occur outside a task context (admin panel reads, cron jobs).

## Scope

- A "Knowledge reads" panel on the admin panel task detail page (`/projects/:id/pipeline/:taskId`) that calls `GET /v1/projects/{id}/tasks/{task_id}/knowledge-lookups` and renders the results inline.
- A reads-count summary chip on the task row in the project Pipeline list (`/projects/:id/pipeline`) showing total read count and live-fetch count at a glance.

## Acceptance criteria

- **AC1.** The admin panel task detail page (`/projects/:id/pipeline/:taskId`) shows a "Knowledge reads" panel; each row displays the artifact path, a "cached" or "live" badge, and the byte count; rows are ordered by `looked_up_at` ascending.
- **AC2.** The Knowledge reads panel is accessible to operators without downloading the task transcript; it loads from the existing `/knowledge-lookups` endpoint and renders within the page without a separate navigation step.
- **AC3.** When a task has zero recorded lookups, the panel renders a "No knowledge reads recorded" empty state rather than hiding the section, so operators can distinguish a zero-read task from a task detail page that does not support the feature.
- **AC4.** Each artifact path in the panel is a clickable link that navigates to that artifact in the project knowledge browser (`/projects/:id/:type/:artifactId`), letting operators open the artifact body to verify it was the right version.
- **AC5.** Each task row in the project Pipeline list (`/projects/:id/pipeline`) shows a reads-count chip (e.g. "12 reads · 3 live") derived from the lookup data; the chip is suppressed for tasks with zero lookups to avoid noise on non-grounding roles.

## Metrics

- Operator transcript downloads (`GET /tasks/{id}/transcript`) correlated to tasks with ≥ 1 knowledge lookup drop measurably within two weeks of ship.
- Task detail page P95 load time does not regress against the pre-ship baseline.

## Open questions

- Does `knowledge_lookups` capture the worker's direct `gh api` calls made inside the Claude CLI subprocess, or only reads that flow through the Python `KnowledgeService` (assembler preloads and in-process cache hits)? If only the latter, the architect should assess whether Bash tool-use rows matching `gh api repos/{org}/{repo}/contents/...` in `task_tool_uses` need to be joined or parsed into the knowledge-reads panel separately.
- Should artifact paths be rendered as relative slugs (e.g. `system/product-specs/active/knowledge/admin-panel.md`) or resolved to their human-readable titles using a knowledge API call? Title resolution adds a network round-trip per unique path.

## Links

- Related specs: [admin-panel](../knowledge/admin-panel.md), [knowledge-api](../knowledge/knowledge-api.md), [observability](../pipeline/observability.md)
- Backend surfaces: `src/coder_core/domain/knowledge_lookup.py`, `src/coder_core/api/tasks.py` lines 322–349 (`GET /{task_id}/knowledge-lookups`), migration `0025_knowledge_lookups.py`
