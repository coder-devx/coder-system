---
id: onboarding
title: Project onboarding
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-06
last_verified_at: 2026-05-06
summary: How a new project gets wired into Coder.
served_by_designs: []
related_specs: [admin-panel, continuous-deployment, impersonation, knowledge-api, knowledge-schema-migration, multi-tenancy, service-accounts]
parent: knowledge-and-admin
---

# Project onboarding

## What it is

The path by which a new project becomes a first-class tenant in Coder:
a knowledge repo built from the `coder-system/template/` blueprint, a
Terraform variable addition that provisions per-project Secret Manager
entries with per-secret IAM bindings, a registration call against the
Core API, and an end-to-end developer task proving isolation from
existing projects. Captured as a runbook so subsequent projects
onboard without bespoke help. VibeTrade and Coder (dog-fooding) are
the two live projects running in parallel today.

## Capabilities

- Terraform `var.projects` list drives per-project secret creation:
  `coder-{project}-developer-anthropic-api-key` with scoped IAM
  bindings to the developer role SA.
- Project registration via the multi-tenant CRUD API; project
  immediately visible in admin panel project switcher.
- Knowledge repo bootstrapped from `coder-system/template/` with
  `system/` prefix, role definitions, and `repos.yaml` listing the
  project's code repos. The bootstrapped `system/repos.yaml` carries
  `template_version: <current>` — the highest `NUMBER` across
  `coder-system/migrations/knowledge/` at the moment of onboarding —
  so the new project has no pending template migrations on day one.
- Per-project API keys and broker-minted bearer tokens both scoped
  to the project; cross-project use returns 403.
- Side-by-side operation verified: two projects, two GitHub orgs,
  shared GCP project, no cross-bleed in secrets, tasks, or logs.
- `coder project onboard <slug>` CLI automates steps 1–5 of the
  runbook; `coder project doctor <slug>` runs an 8-point health check.

## Interfaces

- Runbook: `system/runbooks/onboard-project.md` (10 steps, Terraform
  through verification).
- CLI: `coder project onboard`, `coder project doctor`.
- HTTP: project CRUD, knowledge read/write, task enqueue — all
  gated on `project_id`.
- Terraform: `var.projects` in `coder-core/infra/terraform`.
- Template: `coder-system/template/` blueprint.

## Dependencies

- Multi-tenant project CRUD.
- Knowledge repo read API.
- Developer worker.
- Per-role service accounts (per-secret IAM + broker `project_id`
  claim).
- Pipeline UI (project switcher, side-by-side visibility).
- Local agent impersonation (CLI path into both projects).

## Evolution

- `0008-onboard-first-two-projects` — VibeTrade (`vibetrade`,
  `ViberTrade` org) and Coder (`coder`, `coder-devx` org) onboarded
  2026-04-10. First real developer tasks produced
  `ViberTrade/vibetrade-backend#1` (commit `1311290`) and
  `coder-devx/coder-core#1` (commit `d36bf94`). Migrations 0005–0008
  applied. Runbook written during the vibetrade pass.
- 0047 Template schema migration (shipped 2026-05-06) — the template
  bootstrap step now writes `template_version: <current>` into the
  new project's `system/repos.yaml`; resolves to the highest `NUMBER`
  across `coder-system/migrations/knowledge/` at onboarding time.
  Ensures day-one projects carry no pending migrations and the admin
  fleet matrix shows them clean.
  See [knowledge-schema-migration](./knowledge-schema-migration.md).

## Links

- Designs: [system-overview](../../../designs/active/system-overview.md)
- Related components: [multi-tenancy](../tenancy/multi-tenancy.md),
  [knowledge-api](./knowledge-api.md),
  [knowledge-schema-migration](./knowledge-schema-migration.md),
  [service-accounts](../tenancy/service-accounts.md),
  [impersonation](../tenancy/impersonation.md),
  [admin-panel](./admin-panel.md),
  [continuous-deployment](../delivery/continuous-deployment.md)
