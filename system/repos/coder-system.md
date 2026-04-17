---
id: coder-system
name: coder-system
type: repo
status: active
owner: ro
github: coder-devx/coder-system
default_branch: main
hosts_services: []
language: markdown
ci:
  provider: none
  workflows: []
cd:
  target: none
  trigger: none
decided_by: ["0001", "0002", "0003", "0004", "0008"]
last_verified_at: 2026-04-08
---

# coder-system

## What it holds

This knowledge repository — the structured Markdown + YAML description of
the Coder system, plus the per-project template.

## Layout

```
README.md
AGENTS.md            cross-agent contract
CLAUDE.md            → AGENTS.md
.cursor/rules/       → AGENTS.md
system/              knowledge of Coder itself
template/            blueprint for per-project knowledge repos
```

## CI / CD

- **CI**: (planned) lint registries, validate frontmatter, check cross-link
  integrity. Not yet wired.
- **CD**: none — this is a knowledge repo, not code.

## Branching

- `main` is canonical. Treat edits like docs PRs.

## Linked services

None directly. The future Coder API will *read* this repo to serve knowledge
to workers (goal #5).

## Notes

- See [`AGENTS.md`](../../AGENTS.md) for the agent contract.
