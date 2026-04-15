---
id: task-orchestration
title: Task orchestration
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-15
served_by_designs: [worker-communication]
related_specs: []
---

# Task orchestration

## What it is

The state machine and control plane that moves a task from `queued` all
the way to `accepted` — through enrich, execute, test, review, and
acceptance — with automatic fix loops on failure, structured messages
between workers, human approval gates on the knowledge artifacts that
feed the pipeline, one-click retries on terminal failures, and automatic
chaining between pipeline steps so a single problem statement flows from
PM draft to shipped code without a human creating each subsequent task.
Everything in this component runs out of `workers/orchestrator.py` and
the surrounding `/tasks`, `/messages`, `/retry`, `/approve`/`/reject`,
and `/pipeline-runs` endpoints in `coder-core`.

## Capabilities

- **Stage machine.** Tasks advance through `queued → enriched →
  executing → testing → reviewing → accepted | rejected | failed`.
  Every transition is logged with `task_id`, `from_stage`, `to_stage`,
  and timestamp.
- **Fix loops.** On failure, the orchestrator prepends `fix_context`
  (error + failing output + recent worker messages) to the prompt and
  retries from `executing`, up to 3 attempts before moving to `failed`.
- **Worker messages.** Workers and humans exchange structured messages
  on a task (`from_role`, `to_role`, `msg_type` of feedback / question /
  decision / override, optional `verdict` of approve / request_changes
  / reject, free-form `body`). The reviewer's `request_changes` verdict
  routes the task back into the developer fix loop.
- **Human override.** At any stage, operators can pause, resume, retry,
  skip to a stage, or reject a task. Overrides land in the message
  thread for audit.
- **One-click retry.** Failed, timed-out, or stuck tasks can be cloned
  into a fresh queued task that preserves `role`, `prompt`, `repo`, and
  `spec_id`, resets execution state, and links back via
  `original_task_id`. Non-terminal tasks are refused with `422`.
- **Approval gates.** Specs and designs drafted in `wip/` have formal
  approve/reject endpoints. Approve promotes the artifact to `active/`
  (frontmatter, file move, registry update) and publishes
  `knowledge_approved`. Reject records feedback and can spawn a PM or
  Architect revision task.
- **Stage-run archive.** Every dispatch snapshot lands in
  `task_stage_runs` before the next handler resets the live `TaskRow`
  (migration 0018). The archive is queryable per task via
  `GET /v1/projects/{id}/tasks/{task_id}/stage-runs`, chronologically
  ordered, with `stage` / `status` filters — the replay trail for
  debugging a task without reading Cloud Run logs.
- **Pipeline chaining.** A `pipeline_run` row tracks an end-to-end flow
  for one spec. Approving a spec auto-creates an Architect task;
  approving a design auto-creates a TM task; all developer tasks for a
  spec reaching `accepted` auto-creates a PM acceptance task. Paused
  runs stop chaining until resumed.

## Interfaces

- `POST /v1/projects/{id}/tasks` — create; new tasks start at `queued`.
  PM `draft:` prompts auto-create a `pipeline_run`.
- `GET /v1/projects/{id}/tasks?stage=&status=&role=` — list with filters.
- `POST /v1/projects/{id}/tasks/{task_id}/override` — pause / resume /
  retry / skip_to_stage / reject.
- `POST /v1/projects/{id}/tasks/{task_id}/retry` — clone a terminal
  task into a fresh queued one.
- `POST|GET /v1/projects/{id}/tasks/{task_id}/messages` — structured
  worker conversation; SSE `message_created` events.
- `GET /v1/projects/{id}/tasks/{task_id}/stage-runs?stage=&status=&limit=`
  — archived per-dispatch snapshots, oldest-first.
- `POST /v1/projects/{id}/knowledge/{specs|designs}/{id}/approve|reject`
  — gate endpoints; SSE `knowledge_approved` / `knowledge_rejected`.
- `GET /v1/projects/{id}/pipeline-runs` and
  `POST /v1/projects/{id}/pipeline-runs/{id}/override` — end-to-end run
  visibility and pause/resume/cancel.

## Dependencies

- Postgres (`tasks`, `task_messages`, `task_logs`, `pipeline_runs`,
  `knowledge_reviews`) — state of record. Migrations 0010, 0013, 0015,
  0017 own the schema.
- Developer, Reviewer, PM, Architect, Team Manager workers — the stages
  the orchestrator drives.
- Knowledge write API — file moves and registry updates for approvals.
- SSE event bus — real-time admin updates for message and gate events.
- GitHub Contents API — backs the approve flow's file move.

## Evolution

- `0010-task-orchestration-v1` — state machine, fix loop, `/override`,
  stage filter. Migration 0010.
- `0015-worker-communication` — `task_messages`, verdicts, SSE
  `message_created`, fix-context includes recent messages. Migration 0013.
- `0019-task-retry-endpoint` — `/retry`, `original_task_id`, terminal-
  state gate, retry audit log. Migration 0015.
- `0022-spec-design-approval-gates` — `/approve` and `/reject` for specs
  and designs, revision-task spawn, `knowledge_approved|rejected` SSE.
- `0021-pipeline-chaining` — `pipeline_runs`, chain hooks on approvals
  and on all-dev-accepted, PM-draft auto-run, pause/resume/cancel.
  Migration 0017. Proved end-to-end on 2026-04-13.
- `0024` — `GET /tasks/{task_id}/stage-runs` read endpoint over the
  `task_stage_runs` archive (migration 0018). Ordered by `recorded_at`
  ascending; filters on `stage` and `status`; 1–500 limit. No new
  schema.

## Links

- Designs: —
- Related components: —
