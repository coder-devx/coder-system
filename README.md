# coder-system

Knowledge repository for the **Coder** project — the end-to-end system for developing
and managing software products with autonomous agent teams.

This repo contains **two top-level sections**:

| Section | Purpose |
|---|---|
| [`system/`](./system/) | Knowledge of the Coder system itself — its services, repos, designs, ADRs, roles, specs. The single source of truth for how Coder works. |
| [`template/`](./template/) | The blueprint that every project managed by Coder instantiates as its own knowledge repo. Same shape as `system/`, empty content. |

## How knowledge is organized

Each knowledge type lives in its own folder under `system/` (and mirrored under `template/`):

| Folder | What it holds | Lifecycle |
|---|---|---|
| `services/` | One file per running service. Ownership, tech, deps, API surface. | Live |
| `repos/` | One file per code repo. CI/CD, branches, linked services. | Live |
| `designs/` | Logical design docs with diagrams. | `active/` · `wip/` · `deprecated/` |
| `adrs/` | Numbered architectural decisions with context + rationale. | Append-only |
| `product-specs/` | Product features and roadmap items. | `active/` · `wip/` · `deprecated/` |
| `roles/` | Worker roles (Architect, PM, Developer…) — capabilities and permissions. | Live |
| `integrations/` | External systems (GitHub, GCP, Slack, …) and their auth model. | Live |
| `runbooks/` | Operational procedures (incident, secret rotation, onboarding). | Live |
| `glossary.md` | Shared vocabulary so agents and humans use terms consistently. | Live |

## Conventions

- **Registries** — every folder that lists items has both a machine-readable
  `registry.yaml` and a human-readable `REGISTRY.md`. The YAML is the source of
  truth; the MD should be regenerated from it (the API in goal #5 reads YAML).
- **Diagrams** — Mermaid, inline in MD. No external diagram tooling.
- **Cross-links** — every doc has YAML frontmatter with typed link fields
  (`implements`, `depends_on`, `serves_spec`, `decided_by`, etc.) so the graph
  can be traversed by tools.
- **Numbering** — ADRs and designs use zero-padded 4-digit IDs (`0001-…`).
  IDs are never reused, even after deprecation.
- **Agents** — see [`AGENTS.md`](./AGENTS.md) for how any AI agent (Claude Code,
  Cursor, etc.) should read and update this repo. `CLAUDE.md` and
  `.cursor/rules/coder-system.mdc` both reference it.

## Where to start

- New to Coder? → [`system/designs/active/0001-system-overview.md`](./system/designs/active/0001-system-overview.md)
- Looking for a service? → [`system/services/REGISTRY.md`](./system/services/REGISTRY.md)
- Want to know why we did X? → [`system/adrs/REGISTRY.md`](./system/adrs/REGISTRY.md)
- Setting up a new project under Coder? → copy [`template/`](./template/) into the project's own `coder-system` repo.
