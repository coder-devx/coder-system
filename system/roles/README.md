# roles/

Roles in a Coder team. Each role is a **contract**: capabilities,
permissions, prompts, tools, and escalation paths. A **worker** is an
instance of a role for a specific project.

A worker can be a backend service in the Coder fleet **or** a local agent
(Claude Code, Cursor) impersonating that role. Both obey the same contract
defined here. See [`../designs/active/worker-roles.md`](../designs/active/worker-roles.md).

## Layout

Every role uses the same folder shape (ADR
[0027](../adrs/0027-uniform-role-folder-shape.md), refining design
[role-prompt-knowledge-layout](../designs/active/role-prompt-knowledge-layout.md)):

```
<role-id>/
  role.md            ← identity, scope, permissions
  tasks/             ← present only for dispatched (worker) roles
    <mode>.md        ← per-mode task contract (output format, instructions)
```

The presence of `tasks/` is the only signal of whether a role is
dispatched. Worker roles populate `tasks:` in `registry.yaml`;
non-worker (advisory) roles omit it.

At task pickup the dispatcher fetches three files and assembles the
worker's system prompt:

```
[_common.md] + [<role>/role.md] + [<role>/tasks/<mode>.md]
```

Non-worker roles are never dispatched, so the dispatcher never reads
their `role.md` — but they still live in the same folder shape so the
contributor experience is uniform and promoting a non-worker role to
a worker role is a matter of adding `tasks/`, not restructuring files.

## Files

- [`_common.md`](./_common.md) — preamble prepended to every worker
  prompt. Establishes the Coder System mission and where the role sits
  on the project's team.
- [`_TEMPLATE.md`](./_TEMPLATE.md) — shape for new role docs. Use it
  as the starting point for `<role-id>/role.md`.
- [`registry.yaml`](./registry.yaml) — source of truth for which roles
  exist and which ones are dispatched. `REGISTRY.md` is the
  human-readable view.

## Conventions

- Role IDs are kebab-case (`software-architect`, not `architect`).
- Roles split between **defined** (the user's original list) and
  **proposed** (additional roles awaiting accept/reject) in the
  registry.
- Adding a new mode to a worker role: drop a new `tasks/<mode>.md`
  file, list it under `tasks:` in `registry.yaml`, and wire mode
  detection into `coder_core.workers.dispatcher._parse_mode_for_role`
  in coder-core.
- Promoting a non-worker role to a worker role: add a `tasks/`
  subfolder with the new mode contracts and list `tasks:` in
  `registry.yaml`. No rename, no template switch.
