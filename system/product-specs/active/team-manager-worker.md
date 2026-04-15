---
id: team-manager-worker
title: Team Manager worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-15
served_by_designs: [team-manager-worker]
related_specs: []
---

# Team Manager worker

## What it is

The Team Manager (TM) worker is the planning role in `coder-core`. It
takes an approved spec plus its designs and decomposes them into a
sequenced list of developer tasks — each with role, repo, prompt,
dependency edges, and a complexity estimate. The plan is a reviewable
artifact: a human can edit prompts, reorder, or drop tasks before
approving, at which point TM submits the tasks to the orchestrator in
dependency order.

## Capabilities

- Runs as a `claude` subprocess with a built-in TM system prompt that
  emits plan JSON: ordered tasks with `role`, `repo`, `prompt`,
  `depends_on`, `complexity` (S/M/L).
- Loads the target spec and linked designs from the knowledge API
  before planning; falls back to spec-only with a warning when no
  designs exist (coarser tasks, acceptable for simple specs).
- Writes a draft row to `task_plans` (Postgres, not a knowledge
  artifact) — `spec_id`, `plan_json`, `status`
  (draft/approved/rejected), `feedback`, `created_by_task_id`.
- On approval, creates tasks with `blocked` stage for dependents; the
  orchestrator's `_unblock_dependents` promotes `blocked` → `queued`
  as each dependency reaches `accepted`.
- Submitted tasks link back to the spec and the originating plan.
- Admin plan-review UI supports inline per-task edits (prompt,
  complexity, role, order) before approve/reject.

## Interfaces

- **Consumes:** `role=team-manager` tasks referencing a spec ID.
- **Produces:** `task_plans` row (draft); on approve, a dependency-
  ordered set of developer tasks.
- **REST:** 6 endpoints for plan CRUD + approve/reject.
- **Code:** `src/coder_core/workers/team_manager.py`; admin views
  under `coder-admin/src/routes/plans/`.

## Dependencies

- Knowledge read API (spec + designs).
- Task orchestration (blocked/queued stage machine, unblock hook).
- Admin auth + mutations for the approval UI.
- Pipeline chaining (design approved → TM task auto-creation; plan
  approved → developer tasks dispatched).
- Team-manager-role service account + Anthropic key broker.

## Evolution

- 0013 — `team-manager` role, `task_plans` table (migration 0012),
  plan CRUD + approve/reject endpoints, `blocked` stage with
  `_unblock_dependents`, admin plan-review UI with inline editing.

## Links

- Designs:
- Related components:
