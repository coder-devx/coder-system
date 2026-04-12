---
id: "0013"
title: Team Manager worker v1
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-12
deprecated_at:
reason:
served_by_designs: ["0006"]
related_specs: ["0010", "0012", "0016"]
---

# Team Manager worker v1

**Phase:** Next — autonomous planning
**Progress:** 7 / 7 acceptance criteria ✅

## Problem

Breaking a spec into developer tasks is done manually. The human reads
a spec, decides what tasks to create, writes prompts, and sequences
them. This is time-consuming, error-prone, and not scalable — it's the
bottleneck that prevents Coder from planning its own work.

## Users / personas

- **Human operator** — approves the task plan before execution starts,
  but shouldn't have to author it.
- **Developer worker** — receives better-scoped tasks with clearer
  prompts and explicit dependencies.

## Goals

- Given a spec and its designs, produce a sequenced list of developer
  tasks with prompts, dependency ordering, and complexity estimates.
- Plans are reviewable and editable by the human before execution.
- Task plans are stored and linked to the originating spec.

## Non-goals

- Fully autonomous execution without human plan review (v1 requires
  approval).
- Estimating wall-clock time (complexity estimate only).
- Cross-spec planning or multi-spec coordination.

## Scope

A `team-manager` worker that:

1. Receives a spec ID and loads the spec + relevant designs from the
   knowledge API.
2. Calls Claude to decompose the spec into ordered tasks.
3. Each task has: role, repo, prompt, depends_on list, complexity
   (S/M/L).
4. Produces a plan document for human review.
5. On approval, submits tasks to the orchestrator in dependency order.

## Acceptance criteria

- [x] AC1: `role=team-manager` tasks run the Team Manager worker.
- [x] AC2: The worker loads the target spec and its linked designs from
  the knowledge API before planning.
- [x] AC3: The output plan includes ordered tasks with role, repo,
  prompt, depends_on, and complexity fields.
- [x] AC4: The plan is stored as a reviewable artifact before any tasks
  are submitted.
- [x] AC5: Human approval is required before tasks are submitted to the
  orchestrator.
- [x] AC6: Tasks are submitted in dependency order (blocking tasks before
  dependent tasks).
- [x] AC7: The submitted tasks link back to the originating spec and plan.

## Decisions

- **Plan storage:** Postgres `task_plans` table (operational state, not
  a knowledge artifact). Columns: `spec_id`, `plan_json` (ordered task
  list), `status` (draft/approved/rejected), `created_by_task_id`.
  Avoids dependency on spec 0014 (knowledge write API).
- **Approval UI:** Admin panel — new Plan Review view. Human can view,
  edit individual task prompts, reorder, remove tasks, then approve or
  reject. Follows the existing mutation pattern from spec 0012.
- **No-designs fallback:** Worker plans from spec body only, logs a
  warning. Less context → coarser tasks, acceptable for simple specs.
- **Task submission:** The Team Manager worker itself submits approved
  tasks in dependency order (not the orchestrator). TM creates tasks
  sequentially — each blocking task before its dependents.
- **Edit granularity:** Human can edit individual tasks (prompt, order,
  complexity, role) before approving the plan.

## Links

- Related specs: [`0010`](./0010-task-orchestration-v1.md), [`0012`](./0012-admin-auth-and-mutations.md), [`0016`](../wip/0016-pm-worker-v1.md)
