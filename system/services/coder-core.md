---
id: coder-core
name: Coder Core
type: service
status: active
owner: ro
tier: core
repos: [coder-core]
tech: [python, fastapi]
runtime: cloud-run
region: europe-west1
url: https://coder-core-8534948335.europe-west1.run.app
depends_on:
  services: []
  integrations: [github, gcp, slack, notion, anthropic]
  data_stores: [postgres]
exposes:
  - protocol: http
    port: 8080
    path: /v1/health
implements_designs: ["0001", "0002", "0004"]
decided_by: ["0005", "0006", "0010"]
---

# Coder Core

## What it does

The central, **multi-tenant** orchestrator for Coder. Owns project
lifecycle, dispatches work to role-typed workers, serves knowledge repo
contents to workers and the admin panel, and mints scoped credentials for
worker actions.

Multi-tenant — but **always project-aware in context**. Every API call
carries (or implies) a `project_id`, and every response, log line, and
emitted event is scoped to that project. There is no operation that
acts across projects without an explicit fan-out.

## Responsibilities

- **Project lifecycle**: create, list, archive projects.
- **Knowledge API**: read-through layer over each project's `coder-system`
  knowledge repo. Serves files, registries, and graph queries.
- **Worker dispatch**: route tasks to role-typed workers, track state.
- **Pipeline orchestration**: enrich → execute → fix → test → ready.
- **Impersonation**: mint short-lived, role-scoped tokens for local agents.
- **Admin Panel backend**: status, override, debug surfaces.

## Current state (as of commit #2 · 2026-04-08)

- **v0.0.1 walking skeleton** — deployed to Cloud Run. `GET /v1/health` only.
- URL: <https://coder-core-8534948335.europe-west1.run.app>
- First revision: `coder-core-00001-9lp`
- Runtime SA: `coder-core-sa@vibedevx.iam.gserviceaccount.com` with `logging.logWriter` + `monitoring.metricWriter` only.
- Ingress: `allow-unauthenticated` (auth gating lands in commit #4).

## Planned API surface

| Method | Path | Commit | Purpose |
|---|---|---|---|
| GET  | `/v1/health` | **#1** ✓ | Liveness |
| GET  | `/v1/projects` | #3 | List projects user has access to |
| POST | `/v1/projects` | #3 | Create a project |
| GET  | `/v1/projects/{id}` | #3 | Project detail |
| GET  | `/v1/projects/{id}/knowledge/{path}` | #4 | Read project knowledge repo |
| GET  | `/v1/projects/{id}/workers` | post-#5 | List workers in this project's team |
| POST | `/v1/projects/{id}/tasks` | post-#5 | Submit a task to the pipeline |
| POST | `/v1/projects/{id}/impersonate` | post-#5 | Mint a token for a local agent acting as a role |
| POST | `/v1/projects/{id}/chat` | post-#5 | SSE — interactive agent for the project |

Auth: per-project ACL enforced via static API key per project (commit #4).
Google OAuth + impersonation token minting land later. See
[ADR 0005](../adrs/0005-multi-tenant-coder-core.md).

## Data model

- **Postgres** — projects, workers, tasks, pipeline runs, audit log.
- **Per-project knowledge repos** in GitHub — read via the GitHub
  integration; cached locally per project.
- **GCP Secret Manager** — secrets are stored under per-project prefixes.

## Interactions

```mermaid
flowchart LR
  admin[Admin Panel] --> core[Coder Core]
  local[Local Agent<br/>Claude Code] -- impersonate --> core
  core --> pg[(Postgres)]
  core --> github[GitHub<br/>knowledge repos]
  core --> sm[GCP Secret Manager]
  core --> workers[Role-typed Workers]
  workers --> ext[GitHub · GCP · Slack · Notion]
```

## Operational notes

- **Runtime SA**: `coder-core-sa@vibedevx.iam.gserviceaccount.com`. Current
  roles: `logging.logWriter`, `monitoring.metricWriter`. New roles are
  added in the commit that introduces the need — never preemptively.
- **Image registry**: `europe-west1-docker.pkg.dev/vibedevx/coder-core`.
- **Secrets storage convention**: `coder/{managed_project_id}/{secret_name}` in `vibedevx` Secret Manager.
- **Deployment**: Cloud Run, region `europe-west1`, project `vibedevx`.
- **Deploy runbook**: [`runbooks/deploy-coder-core.md`](../runbooks/deploy-coder-core.md) (manual until commit #5 adds push-to-main CD).

## Open questions

- Where does pipeline state live during a run — Postgres rows + state
  machine, or a real workflow engine?
- How are workers actually launched? Long-running per-role services that
  pull tasks, or short-lived job runners spawned by Core?
- Cache strategy for the GitHub-backed knowledge layer — pull-on-read,
  webhook-triggered refresh, or a periodic sync?
