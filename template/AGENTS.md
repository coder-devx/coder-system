# AGENTS.md

> Cross-agent contract for this project's knowledge repo.

This file is the entrypoint for any AI agent (Claude Code, Cursor, …)
that opens this repository. Read it before doing anything.

## What this repo is

A structured knowledge base for **{PROJECT_NAME}**. Every artifact is a
Markdown file with YAML frontmatter. Registries are YAML with a generated
Markdown view.

The structure was instantiated from the
[Coder `coder-system` template](https://github.com/coder-devx/coder-system/tree/main/template).
It follows the same rules as the upstream template — copy them in here
when instantiating, do **not** rely on the upstream link at runtime.

## Hard rules for agents

> Copy these from the upstream `coder-system/AGENTS.md` when instantiating
> this repo. They are the canonical agent contract. Keep them in sync.

1. Frontmatter is mandatory.
2. YAML registry is the source of truth.
3. Cross-links must resolve.
4. ADRs are append-only.
5. Specs and designs have **two lifecycles**:
   - `wip/` is temporal and numbered (`00NN-kebab-title.md`) — planned work.
   - `active/` is atemporal and subject-named (`component-slug.md`) — current system components.
   - On ship, WIP content merges into `active/` (update existing and/or add new component files); the WIP file is deleted.
   - `deprecated/` keeps removed components with `deprecated_at` and `reason`.
6. Numbering: ADRs and WIP specs/designs use zero-padded 4-digit IDs, never reused. Active specs/designs use subject-kebab slugs as stable IDs.
7. Diagrams are Mermaid, inline.
8. Don't duplicate code-derivable knowledge.
9. This repo is project-specific. Don't put Coder-system rules here.

See the upstream `AGENTS.md` for the full text of each rule.

## Discovery order

1. `README.md`
2. `AGENTS.md` (this file)
3. `glossary.md`
4. `designs/active/system-overview.md` (write this first when starting a project)
5. `services/REGISTRY.md` and `roles/REGISTRY.md`
