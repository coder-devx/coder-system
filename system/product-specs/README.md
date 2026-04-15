# product-specs/

Product features of the Coder system. The product side — the **what**
and the **why for users**, separate from the technical **how** that
lives under [`../designs/`](../designs/).

A spec is owned by the **Product Manager** role. A design is owned by
the **Software Architect** role. They cross-link.

## Two lifecycles

`wip/` and `active/` are different kinds of knowledge, not two stages
of the same file. See [`../../AGENTS.md`](../../AGENTS.md) rule 5 for
the canonical statement.

| Folder | Kind | Naming | Purpose |
|---|---|---|---|
| [`wip/`](./wip/) | Temporal, roadmap-aligned | `00NN-kebab-title.md` | Planned features in flight. One file per roadmap item. |
| [`active/`](./active/) | Atemporal, subject-named | `component-slug.md` | Logical product components of the system as it exists today. |
| [`deprecated/`](./deprecated/) | Historical | Whatever name it had when deprecated | Removed components; kept with `deprecated_at` and `reason`. |

## Ship = merge, not move

When a WIP spec ships, its content is **merged into `active/`**:

- **Update** one or more existing subject-named files if the WIP
  extends or refines components that already exist.
- **Add** a new subject-named file if the WIP introduces a genuinely
  new logical component.
- Both are valid; many WIPs do both.

The numbered WIP file is **deleted** once its content lands in
`active/`. History lives in git, not in filenames.

## Naming

- `wip/` — zero-padded 4-digit numeric ID matching the roadmap entry:
  `0023-branch-cleanup-gc.md`. Numeric IDs are never reused.
- `active/` — short subject-kebab slug naming the component:
  `multi-tenancy.md`, `task-orchestration.md`, `developer-worker.md`.
  Slugs are stable identifiers; renaming requires a cross-link sweep.

## Roadmap

[`ROADMAP.md`](./ROADMAP.md) is the human-readable progress view. It
links WIP entries to their roadmap phase and active components to the
WIPs that delivered them.
