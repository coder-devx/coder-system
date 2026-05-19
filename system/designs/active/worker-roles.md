---
id: worker-roles
title: Worker Roles
type: design
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-29
last_verified_at: 2026-04-29
summary: The role-typed worker subprocesses, their input contract, and how they compose.
implements_specs: []
decided_by: ["0006", "0007"]
related_designs: [system-overview, impersonation]
affects_services: [coder-core]
affects_repos: [coder-core, coder-system]
parent: ~
---

# Worker Roles

## What it is

A Coder project is operated by a **team** of **workers**, each filling
a **role**. A role is a contract — capabilities, permissions, prompts,
tools, and escalation paths. A worker is an instance of a role for a
project. A worker can be a backend service in the Coder fleet, or a
local agent (Claude Code, Cursor, etc.) impersonating that role. Both
obey the same role contract; the only difference is who runs the loop.

## Architecture

```mermaid
flowchart TB
  registry[roles/REGISTRY.md] --> contract[Role contract<br/>prompts · tools · escalation]
  contract --> svc[Fleet worker<br/>coder-core module]
  contract --> local[Local agent<br/>impersonating role]
  svc --> sa[GCP service account<br/>coder-{role}@vibedevx]
  sysadmin[System Admin worker] -. brokers access .-> svc
  sysadmin -. brokers access .-> local
```

### Parts

The current defined role set lives in `roles/REGISTRY.md`:

| Role | One-line job |
|---|---|
| `system-admin` | Owns cloud resources and brokers access to them. |
| `software-architect` | Decides how the system is built. Owns designs and ADRs. |
| `team-manager` | Plans cycles, breaks down work, ensures task quality. |
| `product-manager` | Owns specs, roadmap, acceptance. |
| `developer` | Executes tasks, writes tests, creates test environments. |
| `reviewer` | Reviews completed tasks for code quality before PM acceptance. |
| `consultant` | Async observer; suggests improvements to prompts and process. |
| `qa-engineer` *(proposed)* | Owns test strategy, coverage, regression suites. |
| `sre` *(proposed)* | Owns reliability, observability, oncall. |
| `security-officer` *(proposed)* | Owns auth, secrets policy, threat model. |
| `release-manager` *(proposed)* | Owns release trains, changelogs, rollbacks. |

Reviewer is a distinct role from Product Manager per
[ADR 0007](../../adrs/0007-reviewer-separated-from-pm.md): code review
(technical quality) is separated from product acceptance (product fit).

### Per-role designs

Each role has its own design covering what it produces, what it reads,
and how it composes with the others:

- [architect-worker](./workers/architect-worker.md) — produces designs + ADRs from approved specs.
- [pm-worker](./workers/pm-worker.md) — owns spec drafts and acceptance verdicts.
- [team-manager-worker](./workers/team-manager-worker.md) — decomposes design + spec into developer tasks.
- [developer-worker](./workers/developer-worker.md) — implements tasks; runs the test → fix → PR loop.
- [reviewer-worker](./workers/reviewer-worker.md) — technical-quality gate before PM acceptance.

### Cross-role infrastructure

- [worker-auth-env](./workers/worker-auth-env.md) — per-task Claude credential resolution; explicit clear-other env hygiene.
- [role-prompt-knowledge-layout](./workers/role-prompt-knowledge-layout.md) — per-role system prompts live in the knowledge repo at `roles/{role}/tasks/{mode}.md`; cached prefix per (role, mode).

### Data flow

1. A task arrives carrying `role` and `project_id`.
2. The dispatcher routes to the matching worker module (or the local
   agent holding an impersonation token for that role).
3. The worker loads its system prompt from
   `system/roles/{role}.md`, pulls project context via the Knowledge
   API, and runs the role's loop.
4. Tools the worker invokes are constrained by the role's service
   account permissions.
5. If the worker needs capabilities outside its grant, it escalates
   through the System Admin worker, which brokers scoped,
   time-bounded access.

### Invariants

- Each role-worker runs under its own GCP service account
  (`coder-{role}@vibedevx.iam.gserviceaccount.com`) with minimum
  permissions for its job ([ADR 0006](../../adrs/0006-per-role-service-accounts.md)).
- Workers don't share secrets. The System Admin worker is the only
  broker.
- Service workers and impersonated local agents obey the same role
  contract — same capabilities, same permissions, same escalation.
- The user can take over any role at any time via the admin panel
  (drive mode).

## Interfaces

- `system/roles/{role}.md` — canonical system prompt and contract.
- `roles/REGISTRY.md` — list of defined roles (generated).
- `coder-{role}@vibedevx.iam.gserviceaccount.com` — identity.
- Task API: `POST /v1/projects/{id}/tasks` with `role=<slug>`.

## Evolution

- Initial ship (specs 0002, 0005) — role/worker split, seven role
  service accounts, System Admin broker pattern.
- 2026-04 — shared transient-failure retry across all five role
  workers (spec 0027); retry loop lives inside the worker per
  ADR 0013, not the dispatcher.
- 2026-04-28 — shared `GH_TOKEN` injection via `_github_env`
  (spec 0055): non-workspace roles receive a knowledge-repo-scoped
  installation token on `WorkerInput.github_token`, closing the
  manual-dispatch `gh is unauthenticated` failure.

## Links

- ADRs: 0006 (per-role service accounts), 0007 (reviewer separated
  from PM)
- Designs: system-overview, impersonation, team-manager-worker,
  pm-worker, architect-worker
- Roles: `roles/`
