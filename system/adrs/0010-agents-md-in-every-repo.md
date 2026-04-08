---
id: "0010"
title: Every repo (code and knowledge) contains an AGENTS.md
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: ["0001"]
supersedes:
superseded_by:
---

# ADR 0010 — Every repo (code and knowledge) contains an AGENTS.md

## Context

[ADR 0004](./0004-agents-md-cross-agent-contract.md) decided that the
**knowledge repo** (`coder-system`) uses `AGENTS.md` as the single
source of truth for agent behavior, with `CLAUDE.md` and
`.cursor/rules/*.mdc` as thin pointers.

We're now starting code repos (`coder-core`, `coder-admin`, and future
per-project repos). Each code repo has its own agent-relevant context
that is NOT code-derivable: how to run tests, how to add a feature,
naming conventions, error-handling style, links to the relevant
designs and ADRs in `coder-system`. Where should that live?

## Options considered

1. **Code repos put their rules in `CLAUDE.md` directly; Cursor gets
   a separate `.cursor/rules/*.mdc` copy.** Drift between tools,
   duplication, no common convention.
2. **Code repos have no agent docs; everything lives in `coder-system`.**
   Wrong layer. Commands like `uv run pytest` and directory layout
   belong with the code, not in the cross-project knowledge repo.
3. **Extend the ADR 0004 pattern: every repo — knowledge AND code —
   has `AGENTS.md` at root, with `CLAUDE.md` and `.cursor/rules/*.mdc`
   as thin pointers.** One convention everywhere.

## Decision

Option 3. Every repo in the Coder ecosystem contains `AGENTS.md` at
its root. `CLAUDE.md` and `.cursor/rules/*.mdc` are thin pointer files
that say "read AGENTS.md". This applies to:

- `coder-system` (already follows this — see ADR 0004).
- `coder-core`, `coder-admin`, and any future Coder infrastructure repo.
- Every per-project repo that Coder operates on, including the
  project's own `coder-system`-shaped knowledge repo (the template
  already bakes this in).

New agent surfaces are added as additional thin pointers. Rules are
never duplicated.

## What AGENTS.md contains in a **code repo**

Different from a knowledge repo — a code repo's `AGENTS.md` should be
concise and pragmatic. Recommended sections:

- **What this repo is** — one sentence + links to the repo's and
  service's entries in `coder-system/system/repos/` and `services/`.
- **Discovery order** — "if you don't know the project, read
  `coder-system/AGENTS.md` first, then the relevant design".
- **Layout** — directory map and what each dir is for.
- **Commands** — install, test, lint, typecheck, run, build, deploy.
- **Conventions** — style rules that aren't code-derivable (error
  handling, naming, pydantic at boundaries, etc.).
- **Adding things** — "to add an endpoint / migration / env var, do X".
- **Hard rules** — things that are bugs if violated (e.g. multi-tenancy
  invariants per ADR 0005, secret handling).
- **Where rules evolve** — cross-cutting rules live in `coder-system`;
  repo-specific rules live here.

## What AGENTS.md contains in a **knowledge repo**

Per ADR 0004: the hard rules for frontmatter, registries, ADR
append-only semantics, design lifecycle, numbering, and cross-link
integrity.

## Consequences

- Every new repo scaffold MUST include `AGENTS.md` + `CLAUDE.md` +
  `.cursor/rules/<repo-id>.mdc`.
- Rule updates happen in one file per repo.
- Adding a new agent surface (e.g. a future `Amp`, `Aider`, `Codex`
  config) means adding one thin pointer file; never duplicating rules.
- Extends and broadens ADR 0004 (which covered only the knowledge repo).
- Follow-up: as `coder-core` and `coder-admin` are scaffolded, verify
  they ship `AGENTS.md` in their first commit. The repo review checklist
  should include "does this repo have `AGENTS.md` at root".
