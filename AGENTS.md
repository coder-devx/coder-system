# AGENTS.md

> Cross-agent contract for working with the `coder-system` knowledge repo.
> `CLAUDE.md` and `.cursor/rules/coder-system.mdc` both reference this file.
> Any AI agent that opens this repo MUST read this file first.

## What this repo is

A structured knowledge base about the Coder project. It is **not** code.
Every artifact is a Markdown file with YAML frontmatter. Registries are YAML
with a generated Markdown view.

See [`README.md`](./README.md) for the layout.

## Hard rules for agents

1. **Frontmatter is mandatory.** Every knowledge MD file (under `system/` or
   `template/`, excluding `README.md` / `REGISTRY.md` / `_TEMPLATE.md`) must
   begin with YAML frontmatter matching the type's `_TEMPLATE.md` schema.
   Do not invent new fields silently — propose them in an ADR first.

2. **YAML registry is the source of truth.** When you add, rename, move, or
   remove a knowledge file, update the matching `registry.yaml` in the same
   folder in the same change. `REGISTRY.md` is generated from the YAML — do
   not hand-edit it without also updating the YAML.

3. **Cross-links must resolve.** Frontmatter fields like `implements`,
   `depends_on`, `serves_spec`, `decided_by` reference IDs that must exist in
   the relevant `registry.yaml`. Broken links are bugs.

4. **ADRs are append-only.** Never edit a merged ADR's decision or rationale.
   To change a decision, write a new ADR that supersedes the old one and set
   the old one's `status` to `superseded` with `superseded_by:` pointing at
   the new ID.

5. **Designs move, they don't get deleted.** A WIP design that ships moves
   into `active/` (or its content is merged into existing active design
   files). An active design that's removed moves to `deprecated/` with a
   `deprecated_at` date and `reason`. Files don't disappear — history matters.

6. **Numbering.** ADRs and designs use zero-padded 4-digit IDs
   (`0001-short-kebab-title.md`). Look at the highest existing ID in the
   registry before assigning a new one. IDs are never reused.

7. **Diagrams are Mermaid, inline.** No `.drawio`, no `.excalidraw`, no
   image attachments unless absolutely necessary (and then commit the source
   alongside the rendered image).

8. **Don't duplicate code-derivable knowledge.** If `git log` or reading the
   source answers it, don't write it down here. This repo holds the *why*
   and the *connections* — not the *what* (which lives in code).

9. **Two sections, two purposes.**
   - `system/` describes the **real, current** Coder system. Update it when
     reality changes.
   - `template/` is the **blueprint** new projects copy. Update it only when
     the *shape* of the knowledge model itself changes — never with
     project-specific content.

## How to add a new artifact

1. Find the relevant folder under `system/` (or `template/` if updating the blueprint).
2. Copy `_TEMPLATE.md` to a new filename matching the folder's naming convention.
3. Fill in the frontmatter completely. Leave no required field blank.
4. Write the body. Diagrams go inline as Mermaid.
5. Add an entry to `registry.yaml` in the same folder.
6. Regenerate or update `REGISTRY.md` to match.
7. If the new artifact links to others, make sure those IDs exist.

## How to update an existing artifact

- Most fields can be edited in place.
- Changing a file's **ID** is a rename + registry update + cross-link sweep.
  Avoid it unless necessary.
- For ADRs, see rule 4 above (append-only).
- For designs, prefer editing in place over creating new files — until the
  edit is large enough to warrant a new ADR or a new design ID.

## Discovery order for an agent loading context

1. `README.md` — what the repo is.
2. `AGENTS.md` — this file, the rules.
3. `system/glossary.md` — vocabulary.
4. `system/designs/active/0001-system-overview.md` — the big picture.
5. `system/services/REGISTRY.md` and `system/roles/REGISTRY.md` — the moving parts.
6. Specific files relevant to the task at hand.

## Other agent surfaces

- **Claude Code** loads `CLAUDE.md` at the repo root, which delegates here.
- **Cursor** loads `.cursor/rules/coder-system.mdc`, which delegates here.
- **Other agents** — add a thin pointer file in your tool's expected location
  that references this `AGENTS.md`. Do not duplicate the rules.
