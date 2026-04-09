---
id: "0006"
title: Pipeline UI in admin
type: spec
status: wip
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0003", "0004", "0008"]
---

# Pipeline UI in admin

**Phase:** Next (first real work gets done)
**Progress:** 0 / 6 acceptance criteria

## Problem

Once the developer worker (spec `0004`) is producing runs, those runs
are only observable via `psql` and log grep. That's enough for the
person building Core, but it's not enough for anyone to *use* the
system — Ro can't answer "what is my project doing right now?" without
SSHing into a box. The read-only admin panel from spec `0003` already
exists; this spec extends it with a pipeline view so humans and local
agents can watch and inspect runs.

## Users / personas

- **Ro (human owner)** — needs to see in-flight work, open specific
  task logs, and know when something is stuck without being the
  on-call operator.
- **Software Architect** — uses the pipeline view to validate that the
  enrich/execute/fix/test loop is actually isolated per project.
- **Local agent** impersonating a role — eventually reads the same
  pipeline view to pick up context before acting (spec `0007`).
- **Future Reviewer / QA roles** — the pipeline view is where their
  output will appear alongside the developer's.

## Goals

- A "Pipeline" section in `coder-admin` scoped to the selected project.
- Live list of tasks with status (`pending`, `running`, `succeeded`,
  `failed`, `timed_out`), age, and assigned role.
- Task detail view with streamed logs, result payload, and linked
  repo/branch/commit.
- Filter by role and by status.
- A "test environments" sub-view listing any ephemeral environments the
  pipeline created for a run (empty initially, ready for later specs).

## Non-goals

- Triggering new runs from the UI (still read-only in this pass;
  enqueue remains API-only until a mutation story is defined).
- Editing or cancelling in-flight tasks.
- Cross-project pipeline views.
- Alerting / paging on failures.

## Scope

- New `coder-core` endpoints: `GET /projects/{id}/tasks` (filtered),
  `GET /projects/{id}/tasks/{task_id}`, and a log streaming endpoint
  (SSE or websocket).
- New `coder-admin` routes: `/projects/:id/pipeline`,
  `/projects/:id/pipeline/:task_id`.
- Live updates: the task list refreshes without manual reload.
- Log viewer with follow mode and jump-to-end.
- Status chip + timestamp components reused across views.

## Acceptance criteria

- [ ] The pipeline tab shows all tasks for the currently selected
      project and nothing from other projects.
- [ ] A task moving from `running` to `succeeded` is reflected in the
      UI within 2 seconds without a manual refresh.
- [ ] Opening a task shows its streamed logs with newest lines
      appearing as they're written.
- [ ] Filtering by `role=developer` and `status=failed` narrows the
      list correctly.
- [ ] A failed task's error is visible without opening the database.
- [ ] Clicking a task's linked commit opens the correct GitHub URL for
      that project's repo.

## Metrics

- **Observability coverage:** 100% of task states are surfaced in the
  UI — no "hidden" states that only appear in SQL.
- **Live-update latency:** median end-to-end (DB write → UI render)
  under 2 seconds.
- **Adoption:** Ro stops using `psql` to check task status day-to-day.

## Open questions

- Log streaming transport — SSE (simpler, one-way) vs. websocket
  (bidirectional, richer)?
- Log retention — how far back does the UI let you scroll? Does Core
  page logs from object storage for older runs?
- How do we render very large log outputs without killing the browser
  (virtualisation strategy)?

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 6)
- Services: [`coder-admin`](../../services/coder-admin.md), [`coder-core`](../../services/coder-core.md)
- Related specs: [`0003`](./0003-admin-panel-read-only.md), [`0004`](./0004-developer-worker-v1.md), [`0008`](./0008-onboard-first-two-projects.md)
