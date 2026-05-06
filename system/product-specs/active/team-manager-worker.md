---
id: team-manager-worker
title: Team Manager worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: [team-manager-worker]
related_specs: []
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
- **Output compliance gate.** The `plan_json` envelope is validated
  against the `team_manager` JSON schema (ordered tasks, valid
  `role`, no dependency cycles, S/M/L complexity, and a required
  `self_confidence` block: `{score: integer 0–100, justification:
  string ≤500 chars, risk_flags: array of enum strings}`) before the
  draft row lands in `task_plans`. Schema version bump on
  `team_manager` lands alongside 0040. Schema failures re-prompt
  Claude; on exhaustion the task lands `failed` with
  `failure_kind="schema"` — no orphan plan rows.
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
- 0025 — worker output compliance: `team_manager` JSON schema gates
  the draft-row write. Cycle checks and role validation move from
  the Phase 4 handler into the schema itself; ADR 0012 explains why
  auto-repair is out.
- 0027 — transient-failure retry around the claude spawn. ADR 0013.
- 0044 — close-cycle backstop: `on_all_dev_tasks_accepted` consults
  the orphan-WIP query, stamps `wips_pending_merge` +
  `blocked_since` on the pipeline run, publishes
  `pipeline_run.close_cycle_blocked`, and optionally auto-dispatches
  a `knowledge-ship-draft` architect task (behind
  `ship_draft_dispatch_enabled`). Fails open on GitHub errors.
  ADR 0015 explains why the gate lives in the Coder pipeline rather
  than GitHub branch protection.
- 0055 — `GH_TOKEN` injection for non-workspace roles. TM worker
  calls the shared `_github_env.apply_github_token_env` helper from
  the dispatcher-resolved `WorkerInput.github_token` so `gh`
  commands inside the `claude` subprocess authenticate without a
  workspace clone.
- 0040 — `team_manager` schema extended with a required
  `self_confidence` block (`score`, `justification`, `risk_flags`).
  Schema version bump; `validate_and_retry` enforces presence so the
  auto-approval evaluator (task-orchestration 0040) always has a
  score to evaluate. The static `large_blast_radius` risk-flag check
  (> 5 tasks OR > 3 services touched) is also computed from the
  `plan_json` task list by the gate handler and ORed with the
  worker's self-reported flags before evaluation.

## Links

- Designs: [team-manager-worker](../../designs/active/team-manager-worker.md),
  [worker-roles](../../designs/active/worker-roles.md)
- Related components: [pm-worker](./pm-worker.md),
  [architect-worker](./architect-worker.md),
  [developer-worker](./developer-worker.md),
  [task-orchestration](./task-orchestration.md),
  [knowledge-api](./knowledge-api.md),
  [service-accounts](./service-accounts.md)
