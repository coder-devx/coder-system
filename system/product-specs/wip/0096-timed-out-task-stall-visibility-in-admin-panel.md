---
id: 0096
title: Timed-out task stall visibility in admin panel
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
- task-orchestration
- admin-panel
- self-healing
- observability
parent: pipeline-operations
---

# Timed-out task stall visibility in admin panel

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

When a worker task times out mid-execution, the admin panel renders a `timed_out` status chip with no further context. Operators must open the raw transcript, scan the full message log, and mentally reconstruct which pipeline stage the worker was in and how long it had been running before the timeout — a multi-minute investigation for what should be a 10-second triage.

The underlying data already exists: `TaskStatus` and `TaskStage` are orthogonal columns, so `tasks.stage` reflects where the task was when it timed out; `task_stage_runs` holds per-dispatch timestamps; `tasks.started_at` anchors elapsed time. None of this is surfaced in the task-detail page or the pipeline list today.

## Users / personas

Operators monitoring the admin panel Pipeline list and task-detail pages. They need to answer two questions within seconds of spotting a `timed_out` task: where did it stall (which stage?) and for how long — so they can decide whether to retry, skip to a stage, or escalate.

## Goals

- Surface last-seen stage and elapsed time at timeout on the task-detail page so operators skip the full log dive.
- Provide a one-click path from the timeout callout to the final pre-timeout message in the transcript.
- Annotate `timed_out` rows in the pipeline task list with the stall stage so operators can spot systemic per-stage failure patterns without opening each task.

## Non-goals

- Automatic remediation or retry based on the stall stage — owned by [self-healing](../pipeline/self-healing.md).
- Root-cause analysis or failure classification — this spec surfaces observable state; diagnosis stays with the operator.
- Changes to timeout thresholds or the `zombie_executing` remediator.
- Changes to the RunTimeline (`task_stage_runs` bars already render there; this spec scopes to task-detail and task list only).

## Scope

- **Backend:** Stamp `timeout_stage` and `timeout_elapsed_s` on the `tasks` row when status transitions to `timed_out`, sourced from `tasks.stage` (already orthogonal) and derived from `tasks.started_at`. Expose both on `GET /v1/projects/{id}/tasks/{tid}`.
- **Task-detail page (`TaskDetail.tsx`):** Render a "Timed out" callout for `status = timed_out` tasks showing stage name and elapsed time; include a "Jump to transcript" button.
- **Pipeline task list:** Render a stage annotation on `timed_out` task rows.

## Acceptance criteria

- **AC1.** The task-detail page for any `timed_out` task shows a "Timed out" callout above the message log naming the last pipeline stage and total elapsed time at timeout (e.g., "Timed out in `executing` after 8m 23s"). The callout is visible on initial page load without scrolling.
- **AC2.** The callout includes a "Jump to transcript" button; clicking it scrolls the message-log panel to the final message emitted before the timeout and highlights that message.
- **AC3.** The pipeline task list renders a secondary stage label on `timed_out` rows (e.g., "timed out · executing") so the stall stage is visible without navigating to the task-detail page.
- **AC4.** `GET /v1/projects/{id}/tasks/{tid}` includes `timeout_stage` and `timeout_elapsed_s` (integer seconds) in its response when `status = timed_out`, enabling downstream consumers (MCP agent interface, command palette) to surface this data without a secondary `stage-runs` fetch.
- **AC5.** The callout and stage annotation render regardless of which system path transitioned the task to `timed_out` — worker subprocess timeout, self-healing `zombie_executing` remediator, or platform error — so no code path produces a `timed_out` task without stall-stage visibility.

## Metrics

- Median operator time-to-identify stall stage for a `timed_out` task, measured from task-detail page open (target: under 30 seconds, versus the current several-minute log scan).
- Rate of `timed_out` tasks that receive a retry or skip-to-stage action within 5 minutes of task completion (proxy for faster operator response).

## Open questions

- Should `timeout_elapsed_s` count from `tasks.started_at` (total task elapsed) or from the `task_stage_runs` entry for the final stage (stage-only elapsed)? Total elapsed is simpler and operator-SLA-aligned; stage-elapsed is more precise for root-cause. Proposal: expose both (`timeout_total_elapsed_s`, `timeout_stage_elapsed_s`) and render the total in the callout with the stage-elapsed available for future tooltip detail.
- Does `TaskDetail.tsx` currently render message rows with stable DOM anchor IDs (e.g., `id="msg-{message_id}"`)? The "Jump to transcript" scroll target requires a stable anchor. If not, adding them is in-scope for the Developer task.

## Links

- Designs: [task-lifecycle](../../../designs/active/pipeline/task-lifecycle.md), [admin-panel](../../../designs/active/knowledge/admin-panel.md)
- Related specs: [task-orchestration](./task-orchestration.md), [admin-panel](../knowledge/admin-panel.md), [self-healing](./self-healing.md), [observability](./observability.md)
