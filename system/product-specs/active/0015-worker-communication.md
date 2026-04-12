---
id: "0015"
title: Worker-to-worker communication
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-12
deprecated_at:
reason:
served_by_designs: ["0008"]
related_specs: ["0010", "0016"]
---

# Worker-to-worker communication

**Phase:** Next — autonomous planning
**Progress:** 6 / 6 acceptance criteria

## Problem

Workers operate in isolation: the developer produces a PR, the reviewer
reviews it, but they cannot communicate directly. Review feedback
doesn't flow back to the developer as a structured message. Clarification
requests, acceptance decisions, and human overrides have no shared
conversation thread visible in one place.

## Users / personas

- **Human operator** — needs to see the full conversation between
  workers on a task (what the reviewer said, how the developer responded)
  in the admin panel.
- **Developer worker** — needs reviewer feedback as a structured
  message, not just GitHub PR comments.
- **Reviewer worker** — needs to signal approve/request-changes with
  structured reasoning that the orchestrator can act on.

## Goals

- Structured message passing between workers on a task: review feedback,
  clarification requests, acceptance decisions, human overrides.
- Full conversation visible in the admin panel.
- Orchestrator acts on worker messages (e.g., routes reviewer
  request-changes back to the developer fix loop).

## Non-goals

- Real-time chat or bidirectional streaming.
- Cross-task message threads.
- Worker-to-worker communication outside a task context.

## Scope

A `task_messages` table and API:

- `POST /v1/projects/{id}/tasks/{id}/messages` — worker or human sends
  a message.
- `GET /v1/projects/{id}/tasks/{id}/messages` — list all messages on a
  task.
- Messages have: `from_role`, `to_role`, `type` (feedback | question |
  decision | override), `body`, `timestamp`.
- Orchestrator reads messages to decide next stage transition.
- Admin panel shows a message thread per task alongside the pipeline
  stage view.

## Acceptance criteria

- [x] AC1: A `task_messages` table stores structured messages between
  workers on a task.
- [x] AC2: Workers can post messages via `POST /tasks/{id}/messages` and
  read them in their next prompt.
- [x] AC3: The reviewer's request-changes message causes the orchestrator
  to route the task back to the developer fix loop.
- [x] AC4: Human overrides posted via the admin panel appear as messages
  in the task thread.
- [x] AC5: The admin panel shows the full message thread for a task.
- [x] AC6: Messages are included in SSE events so the thread updates in
  real-time without polling.

## Decisions

- **Same SSE stream.** Messages use the existing `PipelineEvent` bus
  with `event_type="message_created"`. One subscription per project in
  the admin panel — no new channel needed.
- **Separate verdict field.** Messages carry an optional `verdict`
  field (approve/request_changes/reject) alongside the free-form
  `body`. The orchestrator reads the structured verdict; the developer
  reads the body for context. Mirrors the existing `review_verdict` +
  `fix_context` pattern.

## Links

- Related specs: [`0010`](./0010-task-orchestration-v1.md), [`0016`](../wip/0016-pm-worker-v1.md)
