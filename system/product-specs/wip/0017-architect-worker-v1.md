---
id: "0017"
title: Architect worker v1
type: spec
status: wip
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0014"]
---

# Architect worker v1

**Phase:** Later — full self-hosting
**Progress:** 0 / 7 acceptance criteria

## Problem

Design documents and ADRs are written by the human. After a spec is
approved, someone must decide how to build it — components, data flow,
API contracts, storage schema, rollout approach — before the Team
Manager can plan tasks. Without an automated Architect, the human
remains a bottleneck between spec approval and task planning.

## Users / personas

- **Human operator** — reviews and approves the design before task
  planning begins.
- **Team Manager worker** — uses the design to produce better-scoped
  tasks with clearer context.

## Goals

- Given an approved spec, produce a design document covering components,
  data flow, Mermaid diagrams, and rollout plan.
- Draft ADRs for non-obvious architectural decisions.
- Maintain consistency with existing designs and ADRs already in the
  knowledge repo.

## Non-goals

- Producing implementation code (that's the developer's job).
- Autonomous design approval (human review always required in v1).
- Generating Terraform or infra configs.

## Scope

An `architect` worker that:

1. Receives a spec ID and loads the spec plus existing designs and ADRs.
2. Calls Claude to produce a design document following the design
   `_TEMPLATE.md` schema with inline Mermaid diagrams.
3. Identifies decisions that warrant an ADR and drafts them.
4. Stores the design and any ADRs via the knowledge write API.
5. Notifies the human for review.

## Acceptance criteria

- [ ] AC1: `role=architect` tasks run the Architect worker.
- [ ] AC2: The worker loads the target spec and all existing active
  designs and ADRs before generating the new design.
- [ ] AC3: The output design document follows the design `_TEMPLATE.md`
  schema with all required frontmatter fields.
- [ ] AC4: The design includes at least one inline Mermaid diagram
  (component diagram or data flow).
- [ ] AC5: Non-obvious decisions are captured as draft ADRs linked from
  the design.
- [ ] AC6: The design and any ADRs are committed to the knowledge repo
  via the knowledge write API with proper registry entries.
- [ ] AC7: The human is notified for review before the Team Manager
  picks up the spec for task planning.

## Open questions

- How does the Architect ensure consistency with existing designs — load
  all active designs as context, or just the ones linked by the spec's
  `served_by_designs` field?
- Should design documents go directly to `active/` or start in `wip/`
  pending human approval?
- How does the Architect decide which decisions need an ADR vs. which
  are just implementation details?

## Links

- Related specs: [`0014`](./0014-knowledge-write-api.md)
