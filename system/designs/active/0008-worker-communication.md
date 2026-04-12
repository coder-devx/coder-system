---
id: "0008"
title: Worker-to-Worker Communication
type: design
status: active
owner: ro
created: 2026-04-12
updated: 2026-04-12
deprecated_at:
reason:
implements_specs: ["0015"]
decided_by: []
related_designs: ["0001"]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin]
---

# Worker-to-Worker Communication

## Context

Workers communicate indirectly today: the reviewer writes `review_verdict`
on the task row, the orchestrator reads it and builds `fix_context` for
the developer's next attempt. This works but is opaque — the human can't
see the conversation, and there's no structured thread.

Spec 0015 adds a `task_messages` table that makes all inter-worker
communication explicit, auditable, and visible in the admin panel.

## Data model

### `task_messages` table

| Column | Type | Notes |
|--------|------|-------|
| `id` | `VARCHAR(36)` PK | UUID |
| `task_id` | `VARCHAR(36)` FK → tasks | The task this message belongs to |
| `project_id` | `VARCHAR(40)` FK → projects | Denormalized for query efficiency |
| `from_role` | `VARCHAR(40)` | Sender: `developer`, `reviewer`, `admin`, `orchestrator` |
| `to_role` | `VARCHAR(40)` NULL | Target role (NULL = broadcast to all) |
| `msg_type` | `VARCHAR(20)` | `feedback`, `question`, `decision`, `override` |
| `verdict` | `VARCHAR(20)` NULL | `approve`, `request_changes`, `reject` (decisions only) |
| `body` | `TEXT` | Free-form content |
| `created_at` | `TIMESTAMPTZ` | Immutable |

Index: `ix_task_messages_task_id` on `(task_id, created_at)`.

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/projects/{id}/tasks/{task_id}/messages` | Post a message |
| `GET` | `/v1/projects/{id}/tasks/{task_id}/messages` | List messages |

### POST body

```json
{
  "from_role": "reviewer",
  "to_role": "developer",
  "msg_type": "feedback",
  "verdict": "request_changes",
  "body": "The migration is missing a NOT NULL constraint on plan_id."
}
```

### GET response

```json
[
  {
    "id": "...",
    "task_id": "...",
    "from_role": "reviewer",
    "to_role": "developer",
    "msg_type": "feedback",
    "verdict": "request_changes",
    "body": "...",
    "created_at": "2026-04-12T..."
  }
]
```

## Integration points

### Orchestrator

The orchestrator already builds `fix_context` from the task row. With
messages, it also reads the latest `verdict` message to decide the next
stage:

- `verdict=approve` → ACCEPTED
- `verdict=request_changes` → FIXING (prepend message body to fix_context)
- `verdict=reject` → REJECTED

This replaces reading `review_verdict` from the task row for new tasks.
The old field stays for backward compatibility.

### Worker prompts

When the dispatcher prepends `fix_context`, it also appends the latest
messages from the task thread so the developer sees reviewer feedback
inline.

### Admin panel

The task detail page gains a message thread panel showing all messages
chronologically. Human overrides posted via the override endpoint are
also recorded as messages (msg_type=override).

### SSE

Message creation publishes a `PipelineEvent` with
`event_type="message_created"` carrying `{task_id, from_role, msg_type}`.

## Rollout

1. Migration: add `task_messages` table.
2. Domain model: `TaskMessageRow` ORM + pydantic schemas.
3. API: POST + GET endpoints.
4. Orchestrator: read messages for verdict, include in fix_context.
5. Admin panel: message thread component on task detail page.
6. SSE: publish on message creation.
