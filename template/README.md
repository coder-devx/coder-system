# template/

The blueprint that every project managed by Coder instantiates as its
own `coder-system`-shaped knowledge repo.

## How to use this

When a new project starts under Coder:

1. Create a new repo for the project's knowledge (e.g. `acme-coder-system`).
2. Copy the **contents of this folder** (not the folder itself) into the new repo's root.
3. Fill in the registries and start adding artifacts.

## What's in here

The same shape as [`../system/`](../system/), but:

- Registries are **empty** (no real entries).
- Only `_TEMPLATE.md` files exist in each artifact folder.
- `README.md` files are kept so future contributors know what each folder is for.
- No project-specific content. Ever.

If you find yourself adding real project content here, stop — it belongs
in `../system/` (for Coder itself) or in a project's own knowledge repo
(for that project).

## What syncs with `system/`

The **shape** of this folder is kept in lockstep with `system/`. When the
knowledge model changes (new artifact type, new frontmatter field, new
folder), update both `system/` and `template/` in the same commit, and
write an ADR if the change is non-trivial. See
[`../AGENTS.md`](../AGENTS.md) rule 9.
