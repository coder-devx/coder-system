---
id: architect-worker
title: Architect worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-12
last_verified_at: 2026-05-12
summary: Software Architect worker — designs, ADRs, and system shape.
served_by_designs: [architect-worker]
related_specs: []
parent: worker-roles
---

# Architect worker

## What it is

The architect worker is the design-authoring role in `coder-core`.
Given an approved spec, it produces a design document — components,
data flow, Mermaid diagrams, rollout plan — plus any ADRs warranted by
non-obvious decisions. Output lands in `wip/` for human review,
sitting between PM-drafted specs and Team Manager task planning so the
planner gets a concrete architecture to decompose.

## Capabilities

- Loads the target spec and all currently-active designs and ADRs
  before generating, so the new design is consistent with existing
  architectural decisions.
- Runs `claude` with a built-in architect prompt that emits structured
  JSON: frontmatter, body (with at least one inline Mermaid diagram —
  component or data-flow), and an optional ADR list.
- Drafts ADRs for decisions that span multiple components, introduce
  new dependencies, or deviate from existing patterns; ADRs are linked
  from the design body.
- Dispatcher Phase 4 writes the design and any ADRs to `wip/` via the
  knowledge write API with proper registry entries.
- Output gates on human approval before the Team Manager picks the
  spec up for planning.
- **Output compliance gate.** Architect output is validated against
  the `architect` JSON schema (frontmatter shape + at least one
  Mermaid fence in the body) before any Phase 4 write. Schema
  failures re-prompt Claude with the validator errors up to the
  configured budget; on exhaustion the task lands in `failed` with
  `failure_kind="schema"` — no partial design files, no half-written
  ADRs.
- **ADR-collision tagging.** When Phase 4 iterates the architect's
  ADR batch and any `commit_artifact` call returns `collision`, the
  dispatcher accumulates the colliding IDs. After the loop, if any
  collisions occurred, it sets `task.failure_kind = "adr_collision"`
  and `task.failure_detail = {"collided_adr_ids": [...],
  "committed_adr_ids": [...]}` on the task row. The task's audit
  event carries the same payload. Non-colliding ADRs and the design
  commit normally — partial success is preserved, not rolled back.
  Mirrors the `spec_collision` pattern
  (PR [coder-core#202](https://github.com/coder-devx/coder-core/pull/202)).
- **Transient-failure retry.** The claude spawn is wrapped in
  `run_with_transient_retry` (spec 0027). Composes with 0025 —
  transient wraps the spawn, schema wraps a successful spawn's
  output. Architect's task deadline is distinct from transient:
  a deadline hit surfaces as `TaskStatus.TIMED_OUT`, not retried.
- **Knowledge-ship-draft mode.** When a task's prompt begins with the
  `# Knowledge ship draft` header, the architect worker swaps its
  output schema for `architect_ship_draft.json` and emits a
  `merges[]` array (one entry per touched `active/` file, with
  `artifact_type`, `artifact_id`, `action`, and full post-merge
  `body`) instead of a design envelope. The close-cycle backstop
  auto-dispatches these tasks (behind
  `settings.ship_draft_dispatch_enabled`), seeding the left column of
  the admin ship-gate panel so operators don't hand-craft the
  `merges[]` payload.

## Interfaces

- **Consumes:** `role=architect` tasks referencing an approved spec ID.
- **Produces:** design markdown + optional ADR markdown in `wip/`,
  with registry updates and structured commit messages.
- **Code:** `src/coder_core/workers/architect.py`.

## Dependencies

- Knowledge read API (target spec + active designs/ADRs).
- Knowledge write API (design + ADR creation).
- Spec/design approval gates for the human handoff.
- Pipeline chaining (spec approved → architect task; design approved
  → TM task).
- Architect-role service account + Anthropic key broker.

## Evolution

- 0017 — `workers/architect.py` with built-in system prompt, Mermaid
  requirement, ADR drafting, dispatcher Phase 4 write-through to the
  knowledge API.
- 0025 — worker output compliance: `architect` JSON schema gates
  Phase 4 via `validate_and_retry`. Schema exhaustion writes
  `failure_kind="schema"` with the validator errors and truncated
  raw snippet in `failure_detail`; ADR 0012 for the re-prompt-only
  rationale.
- 0027 — transient-failure retry around the claude spawn. ADR 0013.
- 0044 — knowledge-ship-draft mode: the worker detects the
  `# Knowledge ship draft` prompt header, swaps in
  `architect_ship_draft.json`, and emits `merges[]` instead of a
  design envelope. Close-cycle backstop auto-dispatches ship-draft
  tasks (idempotent via task-existence query) when
  `ship_draft_dispatch_enabled` is on.
- 0055 — `GH_TOKEN` injection for non-workspace roles. Architect
  worker now calls the shared `_github_env.apply_github_token_env`
  helper before spawning `claude`, populated from the
  dispatcher-resolved `WorkerInput.github_token`. Closes the
  manual-dispatch failure mode where architect tasks ran
  productively but exited with `gh is unauthenticated`. Realised
  pain: task `62e0c95e` (2026-04-27).
- [coder-core#51](https://github.com/coder-devx/coder-core/pull/51)
  (2026-04-29, surfaced by spec 0056 Phase 2 soak) — architect task
  deadline aligned with all other role workers. The hardcoded
  `architect_timeout = 900` (15 min) was never exercised before
  spec 0056 Phase 2 because Cloud Run service eviction killed worker
  subprocesses first. With Job-mode workers durable, real architect
  runs exploring the codebase for sealed-spec design refinements ran
  25–46 min empirically and hit the 900 s ceiling cleanly. Fix:
  reads `settings.coder_developer_task_timeout_seconds` (2400 s =
  40 min in prod), matching `pm.py` / `team_manager.py` /
  `reviewer.py` / `developer.py`. The hardcoded constant is removed;
  the setting name is shared across all roles as a fleet-wide
  default.
- 0086 — ADR-collision `failure_kind` tagging. When any ADR in an
  architect batch collides at commit time, Phase 4 tags the task row
  with `failure_kind="adr_collision"` and `failure_detail` listing
  `collided_adr_ids` / `committed_adr_ids`. Partial success
  preserved: non-colliding ADRs and the design still commit. The
  audit event records the same payload. Mirrors the `spec_collision`
  pattern (PR [coder-core#202](https://github.com/coder-devx/coder-core/pull/202))
  and the design-collision pattern
  (PR [coder-core#166](https://github.com/coder-devx/coder-core/pull/166)).
  Realised pain: spec 0075 architect batch (2026-05-10) — four ADRs
  emitted, three silently dropped, recovered by hand from preserved
  task output.

## Links

- Designs: [architect-worker](../../designs/active/workers/architect-worker.md),
  [worker-roles](../../designs/active/worker-roles.md)
- Related components: [pm-worker](./pm-worker.md),
  [team-manager-worker](./team-manager-worker.md),
  [knowledge-api](../knowledge/knowledge-api.md),
  [task-orchestration](../pipeline/task-orchestration.md),
  [service-accounts](../tenancy/service-accounts.md)
