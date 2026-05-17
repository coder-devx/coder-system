---
id: "0072"
title: Task replay and diagnostic surface
type: spec
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: ~
served_by_designs: ["0072"]
related_specs:
  - admin-panel
  - task-orchestration
  - observability
parent: ~
---

# Task replay and diagnostic surface

## Problem

The TaskDetail page already stores everything needed to answer "why
did this fail?" — schema validation errors, held raw output, the
turn-by-turn Claude conversation, tool calls, knowledge lookups, the
transcript. On 2026-05-09 a live walk found the data is there but
buried:

- All the diagnostic sections (`Turns`, `Tool uses`, `Knowledge
  lookups`, `Transcript`) are collapsed by default with no preview.
- The expanded `Turns` table shows token counts but **no actual
  content** — only `INPUT 3, OUTPUT 142, CACHE READ 11,007, TOOLS 0,
  CHARS 0`. The operator cannot see what was sent or received without
  going to logs.
- A finished task displays `Logs: No logs yet. They appear once the
  worker finishes.`
- There is no stage-by-stage timeline to anchor "what happened
  between queued and failed?".
- The existing `Replay gate` button (per spec 0064) replays only the
  held output through the schema gate. There is no replay-with-edit
  flow.

The operator opens Cloud Run logs to do basic post-mortem. The page
that should answer the question already has the data.

## Users / personas

- **Operator triaging a failed task from Now.** Today: clicks into
  TaskDetail, expands four collapsed cards, finds token counts but
  not content, opens Cloud Run. After: sees the failed stage at the
  top, clicks the failed segment, reads the prompt and the output
  inline, decides retry-as-is / replay-with-edit / escalate.
- **PM worker debugging architect output failures.** Today: cannot
  see the architect's prompt without dispatching its own diagnostic
  task. After: reads it directly from TaskDetail.
- **Architect worker reviewing transient retries.** Today: the
  `transient_retry_history` chip exists but the per-attempt diff is
  invisible. After: a small attempt switcher pill row shows attempt
  N's prompt vs N-1's, inline.

## Goals

When this ships:

- TaskDetail leads with a stage timeline (queued → enriching →
  executing → testing → fixing → reviewing → terminal). The failed
  stage is rose; click any stage to inspect inputs at that point.
- The diagnostic sections render *content* by default for the
  failed-stage path: prompt body, claude turn bodies (collapsed
  snippet, click to expand), tool call inputs/outputs, knowledge
  lookup results.
- A `[replay with edit]` button opens a modal showing the original
  prompt as an editable mono textarea, the input artifacts as
  removable chips with `+ add artifact` search, and a confirm that
  re-dispatches a new task and jumps to its page.
- A `[retry as-is]` button re-dispatches without edit. Both actions
  preserve `correlation_id` linkage to the original task for audit.
- The "No logs yet" string never shows on a terminal-state task.
- For tasks with multiple attempts (transient retries, schema
  retries), an attempt switcher pill row above the inputs lets the
  operator compare attempt N's prompt to attempt N-1's as a unified
  diff.

## Non-goals

- Re-architecting the task orchestrator. Replay-with-edit creates a
  new task with `parent_task_id` and a `replay_of` reference; it does
  not mutate the original task or its history.
- Streaming live tool calls into TaskDetail. SSE for the in-flight
  case is out of scope; replay-with-edit may stream as a pleasant
  side effect of the existing pipeline-events SSE.
- Replacing the Claude transcript persistence layer.

## Scope

In:

- `GET /v1/projects/{id}/tasks/{task_id}/timeline` returning the
  ordered stage transitions with `entered_at`, `left_at`,
  `duration_ms`, `outcome`, `model_used`, `cost_tokens`, plus the
  prompt and input-artifact snapshot at the start of each stage.
- `GET /v1/projects/{id}/tasks/{task_id}/turns` returning the full
  Claude turn-by-turn content (role, content, tool_use, tool_result,
  per-turn token counts, per-turn duration). The page already has
  schema for this row table; the endpoint surfaces it.
- `POST /v1/projects/{id}/tasks/{task_id}/replay` with body
  `{prompt?: string, input_artifacts?: [string], rationale?: string}`
  creating a new task that references the original via `replay_of`.
  Empty body == retry-as-is; non-empty fields == replay-with-edit.
- `audit_event` rows for both replay shapes; `correlation_id` chains
  back to the original task and forward to the new one.
- TaskDetail redesign per WIP 0072 design: always-expanded stage
  timeline at top, content-bearing turns/tools/lookups, attempt
  switcher with diff, replay-with-edit modal.
- Removal of the misleading "No logs yet" string on a finished task;
  replaced with either captured logs or a link out to Cloud Run with
  a pre-filled query.

Out:

- Editing tasks in place (we always create a new task on replay).
- Re-running an entire pipeline run from a single task (run-level
  replay is a separate concern, not in this WIP).
- Automatic root-cause classification of failures.

## Acceptance criteria

- **AC1.** TaskDetail's stage timeline renders without scroll on a
  laptop viewport. Each stage is clickable; clicking pins that
  stage's inputs (prompt + input artifacts) into the left column.
- **AC2.** The `Turns` section renders actual content (collapsed
  snippet, click-to-expand) on a finished task. Tool uses render
  their `input` and `output` JSON inline; knowledge lookups render
  the artifact path with a click-through link.
- **AC3.** `[replay with edit]` opens a modal pre-filled with the
  original prompt and input-artifact chips. Submitting creates a new
  task whose `replay_of` and `correlation_id` link to the original.
- **AC4.** `[retry as-is]` re-dispatches without modal; same audit
  linkage as AC3.
- **AC5.** For a task with `attempt_count > 1`, an attempt switcher
  is present above the inputs and renders a unified diff of attempt
  N vs N-1's prompt and input-artifact set.
- **AC6.** No finished task displays the literal string `Logs: No
  logs yet. They appear once the worker finishes.` Either logs are
  captured and shown, or the section is replaced with a deep link to
  the relevant Cloud Run query.
- **AC7.** Median operator time from "open failed task" to "decide
  what to do" drops measurably (target ≤ 30s) on a representative
  set of 10 stuck-task drilldowns; pre-ship and post-ship times are
  recorded.

## Metrics

- Cloud Run log queries originating from `coder@vibedevx.com` per
  failed-task triage: drops by ≥ 70% post-ship.
- Replay-with-edit usage rate: emerges from zero (today, the
  feature does not exist) to a steady-state ≥ 5/week as operators
  adopt it.
- TaskDetail "expand all" click rate: drops to zero (the diagnostic
  sections render expanded by default for failed tasks).

## Open questions

- Storage cost of capturing per-stage prompts and input-artifact
  snapshots in the timeline endpoint. Prompts are already stored;
  artifact snapshot is the new write. Defer to design (WIP 0072) for
  the precise schema.
- Whether the attempt-N-vs-N-1 diff is computed server-side or
  client-side. Defer to design.

## Links

- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Design: [0072](../../designs/wip/0072-task-replay-and-diagnostics.md)
- Depends on: [0069](./0069-canonical-project-state.md)
- Related: [admin-panel](../active/knowledge/admin-panel.md), [task-orchestration](../active/pipeline/task-orchestration.md), [observability](../active/pipeline/observability.md)
