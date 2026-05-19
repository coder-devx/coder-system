---
id: '0101'
title: Task Knowledge-Read Trace
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
- observability
- knowledge-api
- knowledge-freshness
parent: knowledge-and-admin
---

# Task Knowledge-Read Trace

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

Operators reviewing a completed or failed task in the admin panel cannot see which knowledge artifacts the worker pulled during that run without downloading the raw transcript from GCS and searching it manually. When a worker produces a poor spec or bad design, the first diagnostic question is "did it read the right grounding artifacts?" — but today answering that requires 30+ seconds of transcript archaeology. Without an inline signal, operators building quality intuition have no lightweight way to check grounding without that detour, and PM-drafted audits of grounding quality (per the PM draft-mode contract) have no observable surface to verify against.

## Users / personas

- **Operators** using the admin panel task detail page to triage completed or failed pipeline tasks.
- **Project owners** investigating why a spec or design required immediate rewrite who want to verify grounding without downloading the full transcript.

## Goals

- Workers' `gh api` knowledge reads are captured per task and queryable via a dedicated endpoint.
- The admin panel task detail page surfaces the knowledge-read list inline — no transcript download needed.
- Operators can answer "which artifacts did this worker read?" in under 10 seconds.

## Non-goals

- Tracking non-knowledge `gh api` calls (PR status, CI, GitHub issue lookups, search endpoints).
- Correlating reads against freshness scores or verdict quality — that remains the knowledge-freshness audit pipeline's concern.
- Full inline transcript rendering (spec 0072, already shipped).
- Reads from local filesystem tools (Read / Glob / Grep).

## Scope

- A backend store for per-task knowledge reads: artifact path and fetch timestamp, populated from task execution.
- `GET /v1/projects/{id}/tasks/{task_id}/knowledge-reads` returning the ordered, deduplicated list.
- A "Knowledge reads" section on the admin panel task detail page, visible on completed and failed tasks, empty (not errored) when the task made zero reads.
- MCP `get_knowledge` calls are captured by the same mechanism when the call carries a valid task-context binding.

## Acceptance criteria

- **AC1.** After a knowledge-reading role task (PM, Architect, or Reviewer) completes, `GET /v1/projects/{id}/tasks/{task_id}/knowledge-reads` returns a non-empty list of artifact paths in fetch order, deduplicated by path.
- **AC2.** The admin panel task detail page shows an inline "Knowledge reads" section listing artifact paths on completed and failed tasks; the list renders without requiring a transcript download and appears within normal page-load time.
- **AC3.** A task that made zero knowledge reads shows an empty "Knowledge reads" section — no error state, no missing section, no spinner.
- **AC4.** An operator browsing project A's task detail cannot see knowledge reads from project B's tasks; the endpoint returns 404 when the task does not belong to the requested project.
- **AC5.** Knowledge reads captured via MCP `get_knowledge` are included in the list for the task the MCP call is bound to, alongside reads from direct `gh api` calls.

## Metrics

- Percentage of completed PM and Architect tasks with at least one knowledge read recorded (capture fidelity proxy); target ≥ 95% within one sprint of ship.
- P90 time from task-detail page open to knowledge-reads list visible, measured in browser: target ≤ 2 seconds on a completed task.

## Open questions

- **Capture mechanism**: reads can be extracted by parsing the task transcript post-run (no in-flight changes to worker subprocess) or by having the worker emit a structured read-list as a side-channel. The Architect should evaluate which is more robust given the GCS transcript write path and the transcript parser already in use (see `src/coder_core/workers/transcript_parser`).
- **Pattern stability for Bash calls**: the `Bash` tool wraps all shell calls; a transcript-based extractor must detect `gh api repos/…/contents/system/…` patterns. Is the pattern stable and narrow enough to rely on, or does a structured side-channel produce cleaner signal with fewer false positives?
- **MCP task binding**: today MCP `get_knowledge` calls may not carry a task id. The Architect should confirm whether a task-context binding already exists or needs to be introduced before AC5 is satisfiable.

## Links

- Related specs: [admin-panel](../active/knowledge/admin-panel.md), [observability](../active/pipeline/observability.md), [knowledge-api](../active/knowledge/knowledge-api.md), [knowledge-freshness](../active/knowledge/knowledge-freshness.md)
