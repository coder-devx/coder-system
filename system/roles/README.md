# roles/

Worker roles in a Coder team. Each role is a **contract**: capabilities,
permissions, prompts, tools, and escalation paths. A **worker** is an
instance of a role for a specific project.

A worker can be a backend service in the Coder fleet **or** a local agent
(Claude Code, Cursor) impersonating that role. Both obey the same contract
defined here. See [`../designs/active/worker-roles.md`](../designs/active/worker-roles.md).

## Layout

Two shapes coexist (introduced by design [0057](../designs/wip/0057-role-prompt-knowledge-layout.md)):

- **Worker roles** — the ones `coder-core` dispatches as LLM workers
  (`product-manager`, `software-architect`, `team-manager`, `developer`,
  `reviewer`). One folder per role:

  ```
  <role-id>/
    role.md            ← identity, scope, permissions
    tasks/
      <mode>.md        ← per-mode task contract (output format, instructions)
  ```

  At task pickup the dispatcher fetches three files from this directory
  and assembles the worker's system prompt:

  ```
  [_common.md] + [<role>/role.md] + [<role>/tasks/<mode>.md]
  ```

- **Non-worker roles** — flat `<role-id>.md` files. These describe roles
  the Coder system recognises but doesn't dispatch as workers
  (`system-admin`, `consultant`, and the proposed roles).

## Files

- [`_common.md`](./_common.md) — preamble prepended to every worker
  prompt. Establishes the Coder System mission and where the role sits
  on the project's team.
- [`_TEMPLATE.md`](./_TEMPLATE.md) — shape for new role docs (use it
  as the starting point for `<role-id>/role.md` for new worker roles
  or for new flat `<role-id>.md` non-worker roles).
- [`registry.yaml`](./registry.yaml) — source of truth for which roles
  exist and which ones use the worker-folder layout. `REGISTRY.md` is
  generated from this.

## Conventions

- Role IDs are kebab-case (`software-architect`, not `architect`).
- Worker roles split between **defined** (the user's original list)
  and **proposed** (additional roles awaiting accept/reject) in the
  registry.
- Adding a new mode to a worker role: drop a new `tasks/<mode>.md`
  file, list it under `tasks:` in `registry.yaml`, and wire mode
  detection into `coder_core.workers.dispatcher._parse_mode_for_role`
  in coder-core.
