---
id: pm-worker
title: PM worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-05-06
last_verified_at: 2026-05-06
served_by_designs: [pm-worker]
related_specs: []
parent: worker-roles
---

# PM worker

## What it is

The PM worker is the product-management role in `coder-core`. It
operates in two modes: **draft**, where it turns a natural-language
problem statement into a product spec in `wip/`, and **accept**,
where it evaluates a delivered spec's acceptance criteria and produces
a verdict report. Human approval gates sit on both sides: a drafted
spec cannot enter the pipeline until approved, and acceptance
verdicts surface as structured messages for operator review before a
spec is promoted.

## Capabilities

- **Draft mode:** runs `claude` with a built-in PM prompt, produces a
  spec following `_TEMPLATE.md` (required frontmatter, Problem / Users
  / Goals / Scope / ACs / Metrics sections), and writes it to `wip/`
  via the knowledge write API with a structured commit.
- **Accept mode:** loads the target spec's subgraph via a single graph
  fetch (`depth=1, edge_types=related_specs`) to gather the spec and
  its related specs in one call, evaluates each AC, and emits a per-AC
  verdict — `pass | fail | partial` — with cited evidence. Falls back
  to direct spec fetch when `CODER_KNOWLEDGE_GRAPH_ENABLED` is off.
  Initial conversion ships with `min_freshness` omitted.
- Acceptance reports are stored as knowledge artifacts linked to the
  spec and posted as verdict messages via worker-to-worker messaging.
- Mode is selected by the task prompt prefix (`draft:` vs `accept:`)
  handled by the dispatcher's Phase 4 writeback.
- Auto-creates a pipeline run for `draft:` tasks so downstream
  chaining (architect → TM → developer → PM-accept) is wired from
  the start.
- **Output compliance gate.** Draft and accept outputs are validated
  against the per-mode JSON schemas (`pm_draft`, `pm_accept`) before
  any Phase 4 side effect. On schema failure the worker re-prompts
  Claude with the validator errors and last raw output, up to the
  configured retry budget; on exhaustion the task exits with
  `failure_kind="schema"` and `failure_detail` holding the errors and
  a truncated raw snippet — zero partial knowledge writes, zero
  orphan DB rows.
- **Transient-failure retry.** The claude spawn is wrapped in
  `run_with_transient_retry` (spec 0027); 429/529/timeout/DNS blips
  re-spawn with exponential backoff. Budget exhaustion lands
  `failure_kind="transient"`; composes with the schema gate above
  (transient wraps the spawn; schema wraps the output of a
  successful spawn).

## Interfaces

- **Consumes:** `role=pm` tasks with either a `draft:` problem
  statement or `accept:` spec reference.
- **Produces:** spec markdown in `wip/` (draft); acceptance report
  artifact + verdict messages (accept); file moves on full-pass
  promotion.
- **Code:** `src/coder_core/workers/pm.py`.

## Dependencies

- Knowledge write API for spec creation, acceptance reports, and
  status-change file moves.
- Knowledge read API (accept mode: spec + related_specs; via graph
  endpoint when `CODER_KNOWLEDGE_GRAPH_ENABLED`, direct fetch
  otherwise).
- Worker-to-worker messaging for verdict delivery.
- Spec/design approval gates for the human-approval handoff.
- Pipeline chaining for `draft:` → architect auto-creation.
- PM-role service account + Anthropic key broker.

## Evolution

- 0016 — `workers/pm.py` with draft and accept modes, dispatcher
  Phase 4 wires both modes to the knowledge write API and messaging.
  First self-hosted spec drafted by the PM and shipped end-to-end
  (0019).
- 0025 — worker output compliance: `pm_draft` and `pm_accept` JSON
  schemas, shared `validate_and_retry` gate in front of Phase 4.
  Schema exhaustion lands `failure_kind="schema"` on the task row and
  leaves no side effect; ADR 0012 explains the re-prompt-only choice.
- 0027 — transient-failure retry around the claude spawn; composes
  with 0025's schema loop. ADR 0013.
- 0055 — `GH_TOKEN` injection for non-workspace roles. PM worker
  calls the shared `_github_env.apply_github_token_env` helper from
  the dispatcher-resolved `WorkerInput.github_token` so `gh`
  commands inside the `claude` subprocess authenticate without a
  workspace clone.
- 0046 — accept-mode context load converted from direct spec fetch to
  a single graph fetch: `depth=1, edge_types=related_specs`;
  `min_freshness` omitted on initial conversion. Falls back to direct
  fetch when `CODER_KNOWLEDGE_GRAPH_ENABLED` is off.

## Links

- Designs: [pm-worker](../../designs/active/pm-worker.md),
  [worker-roles](../../designs/active/worker-roles.md)
- Related components: [architect-worker](./architect-worker.md),
  [team-manager-worker](./team-manager-worker.md),
  [knowledge-api](./knowledge-api.md),
  [task-orchestration](./task-orchestration.md),
  [service-accounts](./service-accounts.md)
