---
id: "0021"
title: "Pipeline chaining"
type: spec
status: active
owner: ro
created: "2026-04-12"
updated: "2026-04-12"
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0010", "0013", "0016", "0017", "0020", "0022"]
---

# Pipeline chaining

**Phase:** active
**Progress:** 6 / 6 acceptance criteria

## Problem

Running the full pipeline (PM → Architect → Team Manager → Developer → Reviewer
→ CD → PM acceptance) requires a human to manually create each subsequent task
after the previous one completes. PM finishes drafting a spec, then someone must
manually create an Architect task. Architect finishes, then someone must manually
create a TM task. This manual glue defeats the purpose of an autonomous pipeline
and was the primary friction point during dog-fooding of spec 0019.

## Users / personas

- **Operators** — want to type a problem statement and have it flow through the
  entire pipeline with approval gates, not manually create 6+ tasks.
- **The system itself** — needs to chain its own pipeline steps to be truly
  self-hosting.

## Goals

- When a PM draft task succeeds AND the resulting spec is approved (via spec
  0022), automatically create an Architect task for that spec.
- When an Architect task succeeds AND the resulting design is approved,
  automatically create a Team Manager task.
- TM plan approval already creates developer tasks (spec 0013) — no change
  needed.
- When all developer tasks for a spec reach the `accepted` stage, automatically
  create a PM acceptance task for that spec.
- Each automatic transition is logged and visible in the admin panel.
- The chain can be paused/cancelled by an operator at any point.

## Non-goals

- Changing the approval gate logic (that's spec 0022).
- Automatic approval (humans must explicitly approve at each gate).
- Customizable chain definitions per project (hardcoded flow for v1).
- Parallel spec pipelines (one spec flows through one chain at a time).

## Scope

**Chain definition (hardcoded v1):**

```
pm_draft → [spec_approval_gate] → architect → [design_approval_gate] →
team_manager → [plan_approval_gate] → developer_tasks → [all_accepted] →
pm_acceptance
```

**Trigger points:**
1. Spec approved (via 0022 endpoint) → create Architect task with spec context.
2. Design approved (via 0022 endpoint) → create TM task with spec + design
   context.
3. All developer tasks for a spec reach `accepted` → create PM acceptance task.

**New table:** `pipeline_runs` tracks a single end-to-end run through the chain
for a spec. Columns: `id`, `project_id`, `spec_id`, `current_step`, `status`
(running/paused/completed/failed), `created_at`, `updated_at`. Each step links
to its task_id.

**Trigger mechanism:** hook into the approval gate endpoints (spec 0022) and the
orchestrator's stage transition logic (spec 0010). When a relevant event occurs,
check if a pipeline_run exists and advance it.

## Acceptance criteria

- [x] AC1: Approving a wip spec that has an associated `pipeline_run`
  automatically creates an Architect task for that spec. The task prompt includes
  the full spec content.
- [x] AC2: Approving a wip design that has an associated `pipeline_run`
  automatically creates a Team Manager task. The task prompt includes both the
  spec and design content.
- [x] AC3: When all developer tasks created from a TM plan reach `accepted`
  stage, the system automatically creates a PM acceptance task (`accept:
  {spec_id}`).
- [x] AC4: `pipeline_runs` table tracks the current step, status, and linked
  task IDs for each spec's pipeline run. Visible via
  `GET /v1/projects/{id}/pipeline-runs`.
- [x] AC5: An operator can pause or cancel a pipeline run via
  `POST /v1/projects/{id}/pipeline-runs/{id}/override`. Paused runs do not
  create new tasks until resumed.
- [x] AC6: Each automatic task creation is logged as a `task_log` entry with
  `triggered_by=pipeline_chain` and the `pipeline_run_id`.

## Open questions

- Should `POST /tasks` with role=pm automatically create a pipeline_run?
  Proposed: yes, if the prompt starts with `draft:`.
- Retry semantics: if an auto-created task fails, does the pipeline_run stall
  or auto-retry? Proposed: stall + alert, operator uses retry endpoint (0019).

## Links

- Task orchestration: spec 0010
- Team Manager (plan approval creates tasks): spec 0013
- PM worker (acceptance mode): spec 0016
- Architect worker: spec 0017
- Task retry: spec 0019
- Developer PR flow: spec 0020
- Approval gates: spec 0022
