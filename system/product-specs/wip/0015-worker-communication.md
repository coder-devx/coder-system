---
id: "0015"
title: Worker-to-worker communication
type: spec
status: wip
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0010", "0016"]
---

# Worker-to-worker communication

**Phase:** Next — autonomous planning
**Progress:** 0 / 6 acceptance criteria

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

- [ ] AC1: A `task_messages` table stores structured messages between
  workers on a task.
- [ ] AC2: Workers can post messages via `POST /tasks/{id}/messages` and
  read them in their next prompt.
- [ ] AC3: The reviewer's request-changes message causes the orchestrator
  to route the task back to the developer fix loop.
- [ ] AC4: Human overrides posted via the admin panel appear as messages
  in the task thread.
- [ ] AC5: The admin panel shows the full message thread for a task.
- [ ] AC6: Messages are included in SSE events so the thread updates in
  real-time without polling.

## Open questions

- Should messages be in the same SSE stream as stage transitions, or a
  separate channel?
- How does the reviewer communicate a structured verdict vs. free-form
  feedback — separate `verdict` field or parsed from body?

## Links

- Related specs: [`0010`](../active/0010-task-orchestration-v1.md), [`0016`](./0016-pm-worker-v1.md)
