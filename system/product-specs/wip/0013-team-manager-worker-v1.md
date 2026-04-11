---
id: "0013"
title: Team Manager worker v1
type: spec
status: wip
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0010", "0012", "0016"]
---

# Team Manager worker v1

**Phase:** Next — autonomous planning
**Progress:** 0 / 7 acceptance criteria

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

- [ ] AC1: `role=team-manager` tasks run the Team Manager worker.
- [ ] AC2: The worker loads the target spec and its linked designs from
  the knowledge API before planning.
- [ ] AC3: The output plan includes ordered tasks with role, repo,
  prompt, depends_on, and complexity fields.
- [ ] AC4: The plan is stored as a reviewable artifact before any tasks
  are submitted.
- [ ] AC5: Human approval is required before tasks are submitted to the
  orchestrator.
- [ ] AC6: Tasks are submitted in dependency order (blocking tasks before
  dependent tasks).
- [ ] AC7: The submitted tasks link back to the originating spec and plan.

## Open questions

- Where is the plan stored? In the knowledge repo as a task-plan
  artifact, or as a new task-plan table in Postgres?
- What's the approval UI? A new admin panel action, or a CLI command?
- How does the worker handle specs with no linked designs — fall back
  to spec body only?

## Links

- Related specs: [`0010`](../active/0010-task-orchestration-v1.md), [`0012`](../active/0012-admin-auth-and-mutations.md), [`0016`](./0016-pm-worker-v1.md)
