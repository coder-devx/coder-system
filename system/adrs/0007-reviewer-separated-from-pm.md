---
id: "0007"
title: Reviewer is a separate role from Product Manager
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: ["0002"]
---

# ADR 0007 — Reviewer is a separate role from Product Manager

## Context

In the original role list, the Product Manager owned task acceptance.
The question was whether code review should also live with PM, or be a
separate role.

## Options considered

1. **PM owns both code review and product acceptance** — fewer roles,
   faster path from "developer says done" to "ready to ship". But it
   bundles two judgments (technical correctness vs. product fit) in one
   reviewer who's optimized for the second.
2. **Separate Reviewer role for code quality, PM for product fit** —
   one more role to manage, but each reviewer makes a single, focused
   judgment.
3. **Developers peer-review each other** — works for human teams; less
   meaningful when developers are agents in the same fleet.

## Decision

Separate `reviewer` role. Reviewer signs off on technical quality
(correctness, security, idiom, design conformance). PM signs off on
product fit (does this match the spec, does it solve the user problem).
A task only reaches PM after Reviewer approval.

## Rationale

The two judgments are different kinds of work and bias each other when
combined. PM looking at code drifts toward style nits; Reviewer looking
at product flow drifts away from technical issues. Splitting them lets
each role get sharper at one thing.

## Consequences

- Positive: code quality has a dedicated owner that isn't also juggling
  the roadmap.
- Positive: PM reviews are purely product — faster and more focused.
- Negative: one more handoff in the pipeline (Developer → Reviewer → PM).
  Mitigation: Reviewer is in the loop early via "draft" PRs, not just at
  the end.
- Follow-up: update the pipeline (`enrich → execute → fix → review → test → pm-accept → ready`).
