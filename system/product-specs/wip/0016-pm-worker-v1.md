---
id: "0016"
title: PM worker v1 (spec and acceptance)
type: spec
status: wip
owner: ro
created: 2026-04-11
updated: 2026-04-11
deprecated_at:
reason:
served_by_designs: []
related_specs: ["0013", "0014", "0015"]
---

# PM worker v1 (spec and acceptance)

**Phase:** Later — full self-hosting
**Progress:** 0 / 7 acceptance criteria

## Problem

Product specs are written manually by the human. Acceptance testing is
also manual — the human checks each AC by hand after the developer
delivers. Both activities are time-consuming and are the primary
bottleneck in the autonomous product lifecycle. Without an automated PM,
Coder cannot close the full loop: spec → plan → build → review → accept.

## Users / personas

- **Human operator** — provides a problem statement; approves or rejects
  the drafted spec; receives an acceptance report instead of running
  checks manually.
- **Team Manager worker** — receives the approved spec and designs to
  plan task execution.

## Goals

- PM drafts product specs from natural-language problem statements.
- Specs require explicit human approval before entering the pipeline.
- After delivery, PM runs acceptance testing against each AC and
  produces a per-AC verdict with evidence.

## Non-goals

- Autonomous spec approval (human approval is always required in v1).
- Acceptance for non-spec deliverables (infra changes, runbooks).
- Multi-stakeholder review workflows.

## Scope

Two modes for the PM worker:

1. **Draft mode** — given a problem statement, produce a spec document
   (using the knowledge write API) following the `_TEMPLATE.md` schema.
   Store in `wip/`. Notify the human for review.

2. **Acceptance mode** — given an active spec and a delivery (PR or
   task set), evaluate each AC, produce a verdict (pass | fail | partial)
   with evidence, and write an acceptance report. Move the spec to
   `active/` if all ACs pass.

## Acceptance criteria

- [ ] AC1: `role=pm` tasks run the PM worker in draft or acceptance mode
  (distinguished by task prompt).
- [ ] AC2: In draft mode, the PM produces a valid spec document with all
  required frontmatter fields, stored in `wip/` via the knowledge write
  API.
- [ ] AC3: The drafted spec is surfaced to the human for review before
  any pipeline execution.
- [ ] AC4: Human approval is required before the spec enters the pipeline
  (Team Manager picks it up only after approval).
- [ ] AC5: In acceptance mode, the PM evaluates each AC against the
  delivery and produces a verdict (pass | fail | partial) with evidence.
- [ ] AC6: The acceptance report is stored as a knowledge artifact linked
  to the spec.
- [ ] AC7: A spec where all ACs pass is promoted to `active/` by the PM
  (moving file, updating frontmatter and registry).

## Open questions

- How does the PM communicate with the Team Manager to signal that a
  spec is approved? Via the task message system (spec 0015) or by
  creating a new TM task directly?
- How does acceptance mode know which delivery to test against — the
  latest merged PR, or a specific commit reference?

## Links

- Related specs: [`0013`](./0013-team-manager-worker-v1.md), [`0014`](./0014-knowledge-write-api.md), [`0015`](./0015-worker-communication.md)
