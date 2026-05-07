---
id: "0027"
title: Uniform folder shape for every role
type: adr
status: accepted
date: 2026-05-07
deciders: [ro]
supersedes:
superseded_by:
relates_to_designs: [role-prompt-knowledge-layout]
---

# ADR 0027 — Uniform folder shape for every role

## Context

Design 0057 ([role-prompt-knowledge-layout](../designs/active/role-prompt-knowledge-layout.md))
introduced a folder shape for **worker** roles —
`<role-id>/role.md` plus `<role-id>/tasks/<mode>.md` — so the
`coder-core` dispatcher could fetch the per-role identity and the
per-mode contract independently and assemble worker prompts as
`_common.md + role.md + tasks/<mode>.md`.

It explicitly kept **non-worker** roles (Consultant, SRE, QA Engineer,
Security Officer, Release Manager, System Admin, Doc Writer, Data
Engineer) as flat single-file `<role-id>.md`. The reasoning was that
non-worker roles aren't dispatched, so they don't need the split.

In practice that decision created friction:

- The `roles/` folder has two layouts side by side. New contributors
  (human and agent) routinely have to look up which roles are which
  before deciding where a new file goes.
- The roles `_TEMPLATE.md` carries a conditional ("worker roles do
  this; non-worker roles do that") that has to be re-explained in
  every onboarding.
- `roles/REGISTRY.md` carries a "Layout" column whose only purpose is
  to discriminate between the two shapes.
- Promoting a non-worker role to a worker role requires a rename
  *plus* a folder restructure, not just adding a `tasks/` subfolder.
- The split is unrelated to the dispatcher contract: the dispatcher
  only ever assembles prompts for roles it dispatches, regardless of
  what shape the *non-dispatched* roles use.

## Options considered

1. **Keep the split, document it more loudly.** Cheapest. Doesn't
   remove the conditional from the template or the special-case
   column from the registry. Doesn't make promotion easier.
2. **Normalize to flat for everyone.** Loses the `tasks/` subfolder
   that the dispatcher needs. Non-starter for worker roles.
3. **Normalize to folder for everyone.** Every role lives at
   `<role-id>/role.md`. Non-worker roles simply omit `tasks/` (or
   carry an empty `tasks/` directory). Uniform layout, uniform
   template, no conditional in onboarding text, friction-free
   promotion path.

## Decision

Adopt option 3. Every role under `system/roles/` uses the folder
shape `<role-id>/role.md`. A `tasks/` subfolder is present only when
the role has dispatchable modes; absence means "not dispatched."

## Rationale

The split design 0057 introduced was a runtime concern leaking into
filesystem layout. The dispatcher reads `tasks/` for the roles it
dispatches and ignores everything else. Whether *non-dispatched*
roles also live in folders has no effect on the dispatcher and
removes a permanent special case from the contributor experience.

This ADR refines design 0057 rather than superseding it. The worker
prompt assembly contract (`_common.md + <role>/role.md +
<role>/tasks/<mode>.md`) is unchanged. What changes is that
non-worker roles also adopt the `<role>/role.md` form, with no
`tasks/` to read.

## Consequences

- **Filesystem**: 8 single-file roles renamed via `git mv`:
  `consultant.md` → `consultant/role.md`, plus `data-engineer`,
  `doc-writer`, `qa-engineer`, `release-manager`, `security-officer`,
  `sre`, `system-admin`. History is preserved.
- **Registry**: each entry gains a `dir:` field and changes `file:`
  from `<id>.md` to `<id>/role.md`. The `tasks:` field stays
  optional — its absence (or empty list) signals "non-dispatched."
- **Templates**: `roles/_TEMPLATE.md` loses the worker-vs-non-worker
  conditional and instructs all new role docs to land at
  `<role-id>/role.md`. The same simplification applies to
  `template/system/roles/_TEMPLATE.md`.
- **Registry view**: `roles/REGISTRY.md` drops the "Layout" column.
  All rows have the same shape; the only signal is whether the
  Modes column is populated.
- **Validator**: no change. `scripts/validate.py` already skips
  `roles/<role>/tasks/*.md` files (they're prompt fragments, not
  artifacts). The frontmatter requirements for `type: role` are
  unchanged.
- **Dispatcher**: no behavior change. `coder-core` already only
  reads `tasks/` for roles whose `tasks:` is populated.
- **Future-proofing**: promoting a non-worker role to a worker role
  becomes "add a `tasks/` subfolder and list modes in
  `registry.yaml`" — no rename, no template switch.
- **Follow-ups**: the existing reference to design 0057 from
  `roles/README.md` linked to its old `wip/` path; that link is
  corrected to the now-active `designs/active/role-prompt-knowledge-layout.md`
  as part of this change.
