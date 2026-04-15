---
id: worker-roles
title: Worker Roles
type: design
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-15
implements_specs: []
decided_by: ["0006", "0007"]
related_designs: [system-overview, impersonation]
affects_services: [coder-core]
affects_repos: [coder-core, coder-system]
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

- `0002-worker-roles-and-impersonation` — introduced the role/worker
  split, the fleet, and per-role service accounts.
- Build plan step 5 (spec 0005) — provisioned the seven role SAs and
  the System Admin broker pattern.

## Links

- ADRs: 0006 (per-role service accounts), 0007 (reviewer separated
  from PM)
- Designs: system-overview, impersonation, team-manager-worker,
  pm-worker, architect-worker
- Roles: `roles/`
