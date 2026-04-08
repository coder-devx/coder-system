---
id: "0003"
title: Mermaid for all diagrams
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: ["0003"]
---

# ADR 0003 — Mermaid for all diagrams

## Context

Designs need diagrams. We can use Mermaid (text in MD), `.drawio`,
`.excalidraw`, or static images.

## Options considered

1. **Mermaid inline** — text in source, renders on GitHub, diffable, no
   tooling. Limited expressiveness for complex diagrams.
2. **drawio / excalidraw** — richer diagrams but binary-ish files, awkward
   diffs, requires a tool.
3. **Static images** — universal but opaque to diffs and editing.

## Decision

Mermaid, inline in MD files.

## Rationale

Knowledge repos live and die by ease of editing. Text-based diagrams are
diffable, agent-editable, and render natively on GitHub. Mermaid covers
flowcharts, sequence diagrams, and ERDs — enough for >90% of what we'll draw.

## Consequences

- Positive: zero tooling. Anyone (and any agent) can edit.
- Positive: diagrams travel in PRs as real diffs.
- Negative: complex diagrams may strain Mermaid. Escape hatch: commit a PNG
  + its source file alongside, but only when Mermaid genuinely won't work.
