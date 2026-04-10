---
id: "0004"
title: Clean rebuild — coder-core + coder-admin
type: design
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-10
implements_specs: []
decided_by: ["0005", "0006", "0007", "0008"]
related_designs: ["0001", "0002", "0003"]
affects_services: [coder-core, coder-admin]
affects_repos: [coder-core, coder-admin]
---

# Clean rebuild — `coder-core` + `coder-admin`

## Context

The previous `coder-agent` and `coder-agent-admin` were hard-wired to one
project (VibeTrade) and bundled all roles into a single process. Rather
than refactor in place, we are **deleting them and rebuilding from a clean
slate** under the new design.

The new system is multi-tenant from day one, project-aware in every API
call, and ships with a fleet of role-typed workers each running with its
own service account.

## Goals

- Two new repos / services from scratch:
  - **`coder-core`** — multi-tenant orchestrator (Python / FastAPI).
  - **`coder-admin`** — admin panel SPA (React / Vite).
- **First-class projects** — `project_id` is a required dimension on every
  API call, log line, audit row, and emitted event.
- **Role-typed workers** — start as modules inside `coder-core`, ready to
  split into `coder-worker-{role}` repos when fleet size warrants.
- **Per-role service accounts** — see [ADR 0006](../../adrs/0006-per-role-service-accounts.md).
- **Knowledge API** — `coder-core` reads each project's `coder-system`
  knowledge repo and serves it to workers and the admin panel.
- **Impersonation** — local agents (Claude Code, Cursor) get short-lived
  role-scoped tokens.

## Non-goals (this design)

- Not migrating data from the old VibeTrade-coupled state. There's nothing
  to migrate; VibeTrade will be re-onboarded as the first project on the
  new system.
- Not designing the worker-fleet split into separate repos yet. That comes
  when scale demands it.

## New shape

```mermaid
flowchart TB
  subgraph CoderCoreSvc[coder-core]
    api[FastAPI multi-tenant API]
    pipe[Pipeline runner]
    knapi[Knowledge API]
    auth[Project ACL + impersonation]
    workers[Role workers<br/>architect · pm · tm · dev · reviewer · sysadmin · consultant]
  end
  subgraph Stores
    pg[(Postgres)]
    sm[GCP Secret Manager<br/>coder/{project}/...]
    gh[GitHub<br/>per-project knowledge repos]
  end
  admin[coder-admin] --> api
  local[Local Agent] -- impersonate --> api
  api --> pg
  api --> sm
  knapi --> gh
  workers --> ext[GitHub · GCP · Slack · Notion · Anthropic]
```

## Key choices

| Choice | Decision | Linked ADR |
|---|---|---|
| Tenancy model | Single multi-tenant Core, project-aware in every call. | [0005](../../adrs/0005-multi-tenant-coder-core.md) |
| Worker identities | Each role-worker gets its own GCP service account. | [0006](../../adrs/0006-per-role-service-accounts.md) |
| Reviewer | Separate role from PM (code review ≠ product acceptance). | [0007](../../adrs/0007-reviewer-separated-from-pm.md) |
| Knowledge repo CI | Validate frontmatter, registries, and cross-links on every PR. | [0008](../../adrs/0008-ci-validation-of-knowledge-repo.md) |

## Build plan

1. **Create empty repos** `coder-devx/coder-core` and `coder-devx/coder-admin`. Wire CI/CD scaffolds.
2. **`coder-core` v0**: project CRUD, Postgres schema, project ACL, GitHub-backed knowledge read API. No workers yet.
3. **`coder-admin` v0**: project switcher + project list + knowledge browser. Read-only.
4. **First role worker — `developer`**: in-process, picks tasks from a Postgres queue, runs the existing `enrich → execute → fix → test` loop against a project's repos.
5. **Service-account split**: each role-worker gets its own GCP SA with the minimum permissions for its job. System Admin worker becomes the broker.
6. **Pipeline UI** in admin: task list, state, logs, test environments.
7. **Impersonation**: short-lived role-scoped tokens for local agents.
8. **Onboard VibeTrade as project #1** on the new system end-to-end. Then onboard a second project to prove multi-tenancy.

## Promotion criteria → active (all met 2026-04-10)

- [x] `coder-core` and `coder-admin` running in prod (Cloud Run,
      `europe-west1`, `vibedevx` GCP project).
- [x] Two projects exist and are isolated: `coder` (coder-devx org)
      and `vibetrade` (ViberTrade org). Cross-project API key and
      bearer token requests return 403.
- [x] Seven role service accounts provisioned
      (`coder-{role}@vibedevx.iam.gserviceaccount.com`). Developer
      worker runs with per-secret IAM isolation.
- [x] VibeTrade developer task ran end-to-end on the new system:
      commit `1311290`, PR ViberTrade/vibetrade-backend#1.
- [x] Local Claude Code impersonates `developer` for both projects
      via `coder impersonate developer --project=X`.

## What shipped

All 8 specs in the build plan reached 100% AC (51/51):

| Step | Spec | ACs | Shipped |
|------|------|-----|---------|
| 1–2 | 0001 Multi-tenant project CRUD | 6/6 | Project CRUD, API keys, structured logging |
| 2 | 0002 Knowledge repo read API | 7/7 | Typed routes, cross-links, TTL cache |
| 3 | 0003 Admin Panel v0 | 6/6 | Project switcher, knowledge browser, API client |
| 4 | 0004 Developer worker v1 | 7/7 | Dispatcher, claude CLI, workspace clone, logs |
| 5 | 0005 Per-role service accounts | 6/6 | 7 SAs, broker, per-secret IAM |
| 6 | 0006 Pipeline UI | 6/6 | Task list, filters, polling, commit links |
| 7 | 0007 Local agent impersonation | 6/6 | Bearer auth, CLI, sessions, revocation |
| 8 | 0008 Onboard first two projects | 7/7 | VibeTrade + Coder, runbook |

Key infrastructure: Terraform in `coder-core/infra/terraform` manages
role SAs and per-project secrets. CI runs `tofu validate` + capability
matrix drift check on every PR. Deploys via GitHub Actions with
Workload Identity Federation (no long-lived keys).

## Open questions (resolved)

- **Worker fleet split**: deferred. In-process workers are sufficient
  for current load. Split when concurrent task execution or memory
  pressure demands it.
- **Knowledge cache**: pull-on-read with in-memory TTL cache. Webhook
  invalidation deferred — cache TTL is short enough for the current
  update cadence.
- **Pipeline state**: Postgres rows with `SELECT ... FOR UPDATE SKIP
  LOCKED` leasing. No workflow engine needed — the state machine is
  simple (queued → running → succeeded/failed/timed_out).

## Links

- Designs: [`0001`](../active/0001-system-overview.md), [`0002`](../active/0002-worker-roles-and-impersonation.md), [`0003`](../active/0003-knowledge-repo-model.md)
- ADRs: [0005](../../adrs/0005-multi-tenant-coder-core.md), [0006](../../adrs/0006-per-role-service-accounts.md), [0007](../../adrs/0007-reviewer-separated-from-pm.md), [0008](../../adrs/0008-ci-validation-of-knowledge-repo.md)
- Services: [`coder-core`](../../services/coder-core.md), [`coder-admin`](../../services/coder-admin.md)
