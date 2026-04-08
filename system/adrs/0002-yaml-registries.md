---
id: "0002"
title: YAML registries with generated Markdown views
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: ["0003"]
---

# ADR 0002 — YAML registries with generated Markdown views

## Context

Each artifact folder needs an index. Humans want a Markdown table. The
future Coder API (goal #5) wants a machine-readable structure to serve.

## Options considered

1. **Hand-maintained `REGISTRY.md` only** — simple, but fragile to parse.
2. **`registry.yaml` only** — machine-readable but hostile on GitHub.
3. **Both: `registry.yaml` is source of truth, `REGISTRY.md` is generated** —
   best of both, requires a tiny generator.

## Decision

Option 3. `registry.yaml` is the source of truth. `REGISTRY.md` is a
generated human view. Both are committed.

## Rationale

The Coder API will need structured registries to traverse the knowledge
graph. Markdown tables are not a stable interface. YAML is. Generating
the MD view is cheap.

## Consequences

- Positive: machine-readable from day one.
- Positive: humans still get a clean Markdown table.
- Negative: two files per registry to keep in sync.
- Follow-up: write a generator (likely a small script in `scripts/` once
  needed). Until then, both files are hand-edited together — see
  [`AGENTS.md`](../../AGENTS.md) rule 2.
