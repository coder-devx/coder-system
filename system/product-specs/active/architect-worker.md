---
id: architect-worker
title: Architect worker
type: spec
status: active
owner: ro
created: 2026-04-11
updated: 2026-04-15
served_by_designs: [architect-worker]
related_specs: []
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

## Links

- Designs:
- Related components:
