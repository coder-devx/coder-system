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

5. **Two lifecycles for specs and designs.** `wip/` and `active/` are
   different kinds of knowledge, not two stages of the same file.
   - `wip/` is **temporal and numbered**. Files align with the roadmap
     and describe *planned* work (`00NN-kebab-title.md`).
   - `active/` is **atemporal and subject-named**. Files describe the
     system's real logical components as they exist today
     (`multi-tenancy.md`, `developer-worker.md`, …). Active is the
     current truth of how the system works, not a ledger of past specs.
   - When a WIP spec/design ships, its content is **merged into
     `active/`** by updating one or more existing component files,
     creating a new component file for a genuinely new logical unit,
     or both. The numbered WIP file is then **deleted**. History lives
     in git, not in filenames.
   - **Shipped-but-soaking.** A WIP whose code is live in production
     stays in `wip/` until the team's chosen soak window closes
     (typically ≥ 30 days for behaviour-changing flags, longer for
     auth / audit / billing surfaces). The `status:` field stays
     `wip`; the roadmap entry annotates `shipped, soaking through
     <date>`. On fold, the file is deleted and content merges into
     `active/` per the previous bullet. The soak-then-fold cadence is
     a project convention to absorb post-ship calibration without
     rewriting `active/` mid-flight.
   - An active component that's removed from the system moves to
     `deprecated/` with `status: deprecated`, `deprecated_at:`, and
     `reason:`. Do not delete.

6. **Numbering vs. subject-naming.**
   - **ADRs** use zero-padded 4-digit IDs (`00NN-kebab-title.md`) and
     are append-only (rule 4).
   - **WIP** specs and designs use zero-padded 4-digit IDs aligned
     with the roadmap. Specs and designs share **one** numeric pool,
     not two — a single ID names one roadmap item, which may have
     a spec, a design, or both (same number on both files). Look at
     the highest existing ID across both folders plus both
     `deprecated/` folders before assigning a new one. Numeric IDs
     are never reused. See [ADR 0026](system/adrs/0026-shared-numeric-id-pool-for-wip-specs-and-designs.md).
   - **Active** specs and designs are **not** numbered. Filename is a
     subject-kebab slug naming the logical component
     (`task-orchestration.md`, not `0010-task-orchestration-v1.md`).
     Slugs are stable identifiers — renaming one is a rename + registry
     update + cross-link sweep.
   - **Deprecated** specs/designs keep whatever name they had when
     deprecated (numeric if deprecated from `wip/`, slug if deprecated
     from `active/`).

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
- When you re-verify a file against current reality, bump its
  `last_verified_at` to today's date. Use `python3 scripts/freshness.py
  --top 20` to see what's drifting and `--over 90` for a focused
  staleness sweep.
- Changing a file's **ID or slug** is a rename + registry update +
  cross-link sweep. Avoid it unless necessary.
- For ADRs, see rule 4 above (append-only).
- For **active** designs and specs, prefer editing the relevant
  subject-named component file in place. Create a new component file
  only when the change introduces a genuinely new logical unit.
- For **WIP** designs and specs, edit in place while in flight. On ship,
  fold the content into `active/` per rule 5 and delete the WIP file.

## Discovery order for an agent loading context

1. `README.md` — what the repo is.
2. `AGENTS.md` — this file, the rules.
3. `system/glossary.md` — vocabulary.
4. `system/INDEX.md` — unified category tree across product specs and
   designs (ADR 0029). Pick the right entry point from here before
   reading bodies. One file for every role; cross-cutting work needs
   no second fetch.
5. `system/HOWTO.md` — "how do I X?" pointers for common tasks
   (authoring, shipping, navigating, validating). Use after INDEX.md
   when you know *what* you want and need *how*.
6. `system/designs/active/system-overview.md` — the big picture, when
   you need engineering framing rather than just navigation.
7. `system/services/REGISTRY.md` and `system/roles/REGISTRY.md` — the moving parts.
8. Specific files relevant to the task at hand.

## Other agent surfaces

- **Claude Code** loads `CLAUDE.md` at the repo root, which delegates here.
- **Cursor** loads `.cursor/rules/coder-system.mdc`, which delegates here.
- **Other agents** — add a thin pointer file in your tool's expected location
  that references this `AGENTS.md`. Do not duplicate the rules.
