---
id: "0004"
title: AGENTS.md as the cross-agent contract
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: ["0003"]
---

# ADR 0004 — AGENTS.md as the cross-agent contract

## Context

Multiple agent surfaces will read and edit this repo: Claude Code (reads
`CLAUDE.md`), Cursor (reads `.cursor/rules/*.mdc`), and others to come.
Each surface has its own conventions for where it looks. We need one set
of rules every agent obeys, without rewriting them in each tool's format.

## Options considered

1. **Duplicate the rules in each tool's expected file** — DRY violation,
   guaranteed drift.
2. **Single `AGENTS.md` at the repo root, thin pointer files for each tool** —
   one source of truth, each tool's file just says "read AGENTS.md".
3. **Custom MCP server that serves rules to all agents** — over-engineered
   for a knowledge repo with no runtime.

## Decision

Option 2. `AGENTS.md` at the repo root holds the contract. `CLAUDE.md` and
`.cursor/rules/coder-system.mdc` are thin pointer files. Future agent
surfaces add another pointer; never duplicate.

## Rationale

DRY. Any rule change happens in one file. Agents that don't yet know
about `AGENTS.md` will still find the contract via their tool-native entry
point.

## Consequences

- Positive: one place to evolve agent rules.
- Positive: easy to onboard a new agent surface — just add a pointer.
- Negative: agents must follow the pointer. Most do.
- Follow-up: when Coder Core API exists, it should also surface
  `AGENTS.md` as a system-prompt fragment for all worker roles.
