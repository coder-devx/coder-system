# roles/

Worker roles in a Coder team. Each role is a **contract**: capabilities,
permissions, prompts, tools, and escalation paths. A **worker** is an
instance of a role for a specific project.

A worker can be a backend service in the Coder fleet **or** a local agent
(Claude Code, Cursor) impersonating that role. Both obey the same contract
defined here. See [`../designs/active/0002-worker-roles-and-impersonation.md`](../designs/active/0002-worker-roles-and-impersonation.md).

## Conventions

- One file per role. Filename = role id (kebab-case).
- Roles split into two groups in the registry:
  - **Defined** — the user's original list (six roles).
  - **Proposed** — additional roles I'm suggesting; review and accept/reject.
