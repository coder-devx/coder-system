---
id: 0097
title: Worker knowledge-pull visibility on task detail
type: spec
status: deprecated
owner: ro
created: '2026-05-18'
updated: '2026-05-19'
last_verified_at: '2026-05-19'
deprecated_at: '2026-05-19'
reason: >-
  Superseded by canonical spec 0099 (Worker Knowledge-Read
  Transparency). This was one of seven near-duplicate specs the
  founder/PM calibration loop emitted on 2026-05-18 for the same idea
  (surface worker knowledge-repo fetches on the task detail page).
  Consolidated 2026-05-19; distinct contributions folded into 0099.
served_by_designs: []
related_specs:
- observability
- admin-panel
- task-orchestration
- knowledge-api
parent: pipeline-operations
---

# Worker knowledge-pull visibility on task detail

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

Workers (PM, Architect, TM, Reviewer, Developer) use `gh api` to pull knowledge-repo artifacts during every task — the spec template, parent-category body, sibling specs, design rollups. Today the only record of *which* artifacts a worker actually fetched is the task transcript, which requires a full download and a manual read to audit. An operator investigating why a PM drafted ACs against the wrong surface, or why an architect produced a design that ignored an existing component, has no faster path than scrolling through kilobytes of tool-call logs. Grounding audits are therefore rare in practice, not because operators don't care, but because the cost is too high.

## Users / personas

- **Pipeline operators** on the admin panel task detail page who want to understand why a task output was low quality, without a full transcript read.
- **Automated grounding-quality tooling** (future spec) that would score fetch coverage against a role's required-reading map.

## Goals

- Surface the list of knowledge-repo artifact fetches inline on the task detail page — no transcript download required.
- Make each fetch entry a navigable link to the artifact's detail view in the knowledge browser.
- Expose the fetch list via the task API response so programmatic audit tooling can consume it.

## Non-goals

- Real-time streaming of fetches as they happen (list is populated on completion).
- Retroactive backfill for tasks that completed before this feature ships.
- Tracking non-knowledge-repo `gh api` calls (PR listing, `search/code`, source-file reads in project repos).
- Scoring grounding quality or emitting alerts — that is a follow-on spec.
- Blocking or failing a task when fetch capture errors.

## Scope

- After a task completes or fails, the task record includes a structured list of knowledge-repo content fetches made during execution — artifact type, ID, and path.
- The admin panel task detail page renders a **"Knowledge pulls"** panel below the existing stage timeline; entries that resolve to known artifacts link to their detail view in the knowledge browser.
- The task API response (`GET /v1/projects/{id}/tasks/{task_id}`) includes the fetch list so grounding audits need no transcript download.

## Acceptance criteria

- **AC1.** The admin panel task detail page shows a "Knowledge pulls" section for any completed or failed task, listing every knowledge-repo content fetch made during execution with artifact type and ID visible — accessible without downloading the transcript.
- **AC2.** Each entry that resolves to a known artifact in the knowledge browser is a clickable link to that artifact's detail page; entries that do not resolve render as plain text paths.
- **AC3.** A task that made zero knowledge-repo fetches shows a "None fetched" notice in the section so operators can distinguish an intentionally fetch-free run from a capture failure.
- **AC4.** `GET /v1/projects/{id}/tasks/{task_id}` includes a `knowledge_pulls` array in the response body — each element carrying at minimum the artifact path and fetch timestamp — so automated tooling can audit grounding without the transcript.
- **AC5.** When fetch capture fails for a task (e.g. transcript parse error), the task completes normally with its existing outcome; the "Knowledge pulls" section shows "Capture unavailable for this task" rather than a gap or a task failure.

## Metrics

- `knowledge_pulls` populated on ≥ 90% of completed tasks for PM, Architect, and TM roles within 30 days of ship (the three roles with the most structured knowledge-fetch patterns).
- Task failure rate attributable to fetch-capture errors: zero (fail-open contract, AC5).

## Open questions

- Which capture strategy does the architect choose? Options: parse the Claude CLI transcript at task completion (reusing the envelope-parse hook that already reads `transient_retry_history` per spec 0088); wrap `gh` in the worker subprocess env; or add a structured fetch-log path to the worker runner. Architect to decide.
- Should the fetch list land in the existing `task_metadata` JSON column (spec 0088 AC3, zero schema change) or a dedicated `task_knowledge_pulls` table (enables per-artifact cross-task queries)?
- Should entries be deduplicated by path (some workers fetch the same file twice — grounding pass then cross-link verify) or preserve all calls with timestamps?

## Links

- Related specs: [observability](../active/pipeline/observability.md), [admin-panel](../active/knowledge/admin-panel.md), [task-orchestration](../active/pipeline/task-orchestration.md), [knowledge-api](../active/knowledge/knowledge-api.md)
