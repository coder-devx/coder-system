---
id: team-manager-worker
title: Team Manager worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: Team Manager worker — decomposes specs into developer tasks.
served_by_designs: [team-manager-worker]
related_specs: [architect-worker, developer-worker, knowledge-api, pm-worker, service-accounts, task-orchestration]
parent: worker-roles
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
- Assembles plan context via a single graph fetch rooted at the
  approved design (`depth=2,
  edge_types=decided_by,related_designs,affects_services`), replacing
  the prior "load design + walk decided_by" serial pattern. Falls back
  to spec-only with a warning when no designs exist (coarser tasks,
  acceptable for simple specs). Falls back to serial walk when
  `CODER_KNOWLEDGE_GRAPH_ENABLED` is off. Initial conversion ships
  with `min_freshness` omitted.
- Writes a draft row to `task_plans` (Postgres, not a knowledge
  artifact) — `spec_id`, `plan_json`, `status`
  (draft/approved/rejected), `feedback`, `created_by_task_id`.
- On approval, creates tasks with `blocked` stage for dependents; the
  orchestrator's `_unblock_dependents` promotes `blocked` → `queued`
  as each dependency reaches `accepted`.
- Submitted tasks link back to the spec and the originating plan.
- Admin plan-review UI supports inline per-task edits (prompt,
  complexity, role, order) before approve/reject.
- **Output compliance gate.** The `plan_json` envelope is validated
  against the `team_manager` JSON schema (ordered tasks, valid
  `role`, no dependency cycles, S/M/L complexity) before the draft
  row lands in `task_plans`. Schema failures re-prompt Claude; on
  exhaustion the task lands `failed` with `failure_kind="schema"` —
  no orphan plan rows.
- **Transient-failure retry.** The claude spawn is wrapped in
  `run_with_transient_retry` (spec 0027); composes with the schema
  gate above.
- **Close-cycle ship backstop.** The `on_all_dev_tasks_accepted`
  close-cycle hook queries the Knowledge API's orphan-WIP endpoint
  (`/knowledge/wips?shipped=true`) and refuses to close the cycle
  when the result is non-empty. The block lands as a structured
  `wips_pending_merge` stamp on the pipeline run with a
  `blocked_since` timestamp, a SSE `pipeline_run.close_cycle_blocked`
  event, and an optional auto-dispatched `knowledge-ship-draft`
  architect task (behind `settings.ship_draft_dispatch_enabled`) so
  the admin ship-gate panel opens pre-populated. The hook fails open
  on GitHub errors so an API outage never traps a cycle.

## Interfaces

- **Consumes:** `role=team-manager` tasks referencing a spec ID.
- **Produces:** `task_plans` row (draft); on approve, a dependency-
  ordered set of developer tasks.
- **REST:** 6 endpoints for plan CRUD + approve/reject.
- **Code:** `src/coder_core/workers/team_manager.py`; admin views
  under `coder-admin/src/routes/plans/`.

## Dependencies

- Knowledge read API (spec + designs; via graph endpoint when
  `CODER_KNOWLEDGE_GRAPH_ENABLED`, serial walk otherwise).
- Task orchestration (blocked/queued stage machine, unblock hook).
- Admin auth + mutations for the approval UI.
- Pipeline chaining (design approved → TM task auto-creation; plan
  approved → developer tasks dispatched).
- Team-manager-role service account + Anthropic key broker.

## Evolution

- 2026-04 — v1 TM with `task_plans` table, plan CRUD + approve/reject,
  `blocked` stage + dependency unblock, admin plan-review UI; plus
  output compliance gate, transient-failure retry, close-cycle
  backstop (specs 0013, 0025, 0027, 0044).
- 2026-04 — `GH_TOKEN` unified via `_github_env`; plan-authoring
  context load converted to single graph fetch behind
  `CODER_KNOWLEDGE_GRAPH_ENABLED` (specs 0046, 0055).

## Links

- Designs: [team-manager-worker](../../../designs/active/workers/team-manager-worker.md),
  [worker-roles](../../../designs/active/worker-roles.md)
- Related components: [pm-worker](./pm-worker.md),
  [architect-worker](./architect-worker.md),
  [developer-worker](./developer-worker.md),
  [task-orchestration](../pipeline/task-orchestration.md),
  [knowledge-api](../knowledge/knowledge-api.md),
  [service-accounts](../tenancy/service-accounts.md)
