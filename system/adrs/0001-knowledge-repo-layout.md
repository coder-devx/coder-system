---
id: "0001"
title: Knowledge repo layout — system + template
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: [knowledge-repo-model]
---

# ADR 0001 — Knowledge repo layout: system + template

## Context

Coder will manage many projects. Each project needs its own knowledge
repo with the same shape. We also need a place to describe Coder *itself*.
We can put both in one repo or split them.

## Options considered

1. **One repo, two top-level folders (`system/`, `template/`)** — single
   source of truth, easy to keep them in sync, the template literally
   mirrors the live structure.
2. **Two separate repos (`coder-system`, `coder-template`)** — clean
   separation but drift risk and double the maintenance.
3. **Only `system/`, generate template on demand** — minimal but the
   template stops being a first-class artifact people can copy.

## Decision

Option 1. Single repo, two top-level folders. `system/` describes the
real Coder system. `template/` is the blueprint that per-project knowledge
repos instantiate.

## Rationale

Keeps the template visibly aligned with the live system. When the model
shape changes (new artifact type, new frontmatter field), the same change
touches both folders in one commit.

## Consequences

- Positive: zero drift between live system and template.
- Positive: contributors see both side-by-side.
- Negative: per-project repos must remember they're cloning from `template/`,
  not the whole repo.
- Follow-up: add a CI check that `template/` only contains placeholders
  and `_TEMPLATE.md` files (no real project content leaks in).
