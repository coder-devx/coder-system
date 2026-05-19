---
id: service-accounts
title: Per-role service accounts
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-05-03
last_verified_at: 2026-05-03
summary: Per-role GCP service accounts and brokered escalations.
served_by_designs: []
related_specs: [admin-panel, audit-log, impersonation, multi-tenancy, tenant-isolation]
parent: tenancy-and-access
---

# Per-role service accounts

## What it is

Every worker role in Coder runs under a dedicated GCP service account,
provisioned by Terraform and granted only the permissions that role
needs. Workers never read static keys; they obtain short-lived,
role-scoped credentials from the SysAdmin broker at runtime. Per-project
isolation is enforced in software (broker stamps a `project_id` claim
into every token) and in IAM (per-secret bindings on
`coder-{project}-{role}-*` resources).

## Capabilities

- One GCP SA per role (`coder-{role}@vibedevx.iam.gserviceaccount.com`),
  shared across projects. Seven SAs currently provisioned, one per role
  in `roles.yaml`.
- Broker endpoint `POST /v1/projects/{project_id}/impersonate/{role}`
  mints short-lived JWTs carrying `project_id`, `role`, and expiry.
- Dispatcher fetches per-project Anthropic keys through the broker
  instead of a process-wide env var; hard-fails on `SecretReadError`.
- Cross-project secret reads fail at the GCP IAM layer (403
  `IAM_PERMISSION_DENIED`) because the role SA has no project-level
  Secret Manager grant.
- Token expiry enforced by `LocalBroker.verify`; expired tokens rejected.
- `capability_matrix.py` regenerates `CAPABILITY_MATRIX.md` from
  `roles.yaml`; CI runs `--check` alongside `tofu fmt -check` and
  `tofu validate` on every PR, failing the build on drift.

## Interfaces

- Broker HTTP: `POST /v1/projects/{project_id}/impersonate/{role}`.
- Terraform: `coder-core/infra/terraform` with state in
  `gs://vibedevx-coder-core-tfstate`. Inputs: `roles.yaml`,
  `var.projects`. Outputs: role SAs, per-secret IAM bindings.
- Python: `fetch_project_anthropic_key(broker, gcp_project_id, project_id)`
  in `coder_core.workers.dispatcher`.
- Docs surface: `CAPABILITY_MATRIX.md` (generated).

## Dependencies

- GCP IAM + Secret Manager (per-secret `secretAccessor` bindings).
- `roles.yaml` — single source of truth for role capabilities,
  consumed by both `roles.tf` (`yamldecode`) and `capability_matrix.py`.
- Multi-tenant `project_id` guard on coder-core endpoints (ADR 0005).
- SysAdmin broker process for token issuance.

## Evolution

- 2026-04 — Initial ship (spec 0005): seven role SAs, dispatcher
  cut over from env-var key to broker-issued token. Per-secret IAM
  bindings (CABs ruled out — no Secret Manager support).
- 2026-04-22 — Claude OAuth auth-mode: per-project tri-state
  (`NULL` = fleet inherit, `oauth`, `api_key`); shared `_auth_env`
  helper assembles the env block + pops the competing credential so
  the CLI can't cross-wire. `PATCH /v1/_admin/projects/{id}/auth-mode`
  + `AuthModeCard` expose the toggle.

## Links

- Designs: [worker-roles](../../../designs/active/worker-roles.md),
  [tenancy-and-access](../../../designs/active/tenancy-and-access.md)
- Related components: [impersonation](./impersonation.md),
  [multi-tenancy](./multi-tenancy.md),
  [tenant-isolation](../delivery/tenant-isolation.md),
  [audit-log](./audit-log.md), [admin-panel](../knowledge/admin-panel.md)
