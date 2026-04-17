---
id: pm-worker
title: PM worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-15
served_by_designs: [pm-worker]
related_specs: []
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
- **Accept mode:** loads the target spec and the delivery context
  (task results by `spec_id` in the prompt), evaluates each AC, and
  emits a per-AC verdict — `pass | fail | partial` — with cited
  evidence.
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

## Links

- Designs:
- Related components:
