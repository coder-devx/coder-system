# designs/

Design docs for the Coder system — the technical **how**. Each active
design describes a logical component as it currently works, with
diagrams and the rationale linking back to ADRs and product specs.

## Two lifecycles

`wip/` and `active/` are different kinds of knowledge, not two stages
of the same file. See [`../../AGENTS.md`](../../AGENTS.md) rule 5 for
the canonical statement.

| Folder | Kind | Naming | Purpose |
|---|---|---|---|
| [`wip/`](./wip/) | Temporal, roadmap-aligned | `00NN-kebab-title.md` | Design work in flight for a planned spec. |
| [`active/`](./active/) | Atemporal, subject-named | `component-slug.md` | Logical components of the system as it exists today. |
| [`deprecated/`](./deprecated/) | Historical | Whatever name it had when deprecated | Removed components; kept with `deprecated_at` and `reason`. |

## Ship = merge, not move

When a WIP design ships, its content is **merged into `active/`**:

- **Update** one or more existing subject-named files when the WIP
  extends or refines components that already exist.
- **Add** a new subject-named file when the WIP introduces a genuinely
  new logical component.
- Both are valid; many WIPs do both.

The numbered WIP file is **deleted** once its content lands in
`active/`. History lives in git, not in filenames.

## Naming

- `wip/` — zero-padded 4-digit numeric ID aligned with the spec it
  serves: `0023-branch-cleanup-gc.md`. Numeric IDs are never reused.
- `active/` — short subject-kebab slug naming the component:
  `system-overview.md`, `worker-roles.md`, `task-orchestration.md`.
  Slugs are stable identifiers; renaming requires a cross-link sweep.

## Entry points

- `active/system-overview.md` — start here for the big picture.
- `active/<component>.md` — drill into a specific component.
