---
id: architect-worker
title: Architect worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-06
last_verified_at: 2026-05-06
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
- **Transient-failure retry.** The claude spawn is wrapped in
  `run_with_transient_retry` (spec 0027). Composes with 0025 —
  transient wraps the spawn, schema wraps a successful spawn's
  output. Architect's 900 s task deadline is distinct from transient:
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
- **Cold-start mode.** When a task's prompt begins with
  `# Knowledge cold start`, the architect worker swaps its output
  schema for `architect_cold_start.json` and emits an `artifacts[]`
  array (one entry per knowledge file proposed) instead of a design
  envelope. Each entry carries `artifact_type` ∈ {`service`, `design`,
  `adr`, `glossary_entry`}, `artifact_id`, `body`,
  `ingestion_provenance`, and `confidence ∈ [0, 100]`. Schema
  failures re-prompt via `validate_and_retry`; exhaustion lands
  `failure_kind="schema"` with per-batch detail. Dispatched exclusively
  by the `coder-core-cold-start-ingest` Cloud Run Job; see
  [cold-start-ingestion](./cold-start-ingestion.md).

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
- 0045 — cold-start mode: the worker detects the
  `# Knowledge cold start` prompt header, swaps in
  `architect_cold_start.json`, and emits `artifacts[]` (one entry per
  inferred knowledge file with `ingestion_provenance` and
  `confidence`) instead of a design envelope. Dispatched exclusively
  by the `coder-core-cold-start-ingest` Cloud Run Job.

## Links

- Designs: [architect-worker](../../designs/active/architect-worker.md),
  [worker-roles](../../designs/active/worker-roles.md)
- Related components: [pm-worker](./pm-worker.md),
  [team-manager-worker](./team-manager-worker.md),
  [knowledge-api](./knowledge-api.md),
  [task-orchestration](./task-orchestration.md),
  [service-accounts](./service-accounts.md)
