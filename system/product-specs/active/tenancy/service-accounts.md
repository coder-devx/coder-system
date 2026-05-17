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
served_by_designs: [worker-roles]
related_specs: []
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

- `0005-per-role-service-accounts` — initial provisioning of the seven
  role SAs, dispatcher cut over from env-var key to broker-issued token.
- `337d5d1` (2026-04-10) — replaced Credential Access Boundary design
  with per-secret IAM bindings after discovering CABs do not support
  Secret Manager.
- **Claude OAuth auth-mode (shipped 2026-04-22, `c992a7b`).**
  Workers resolve their Anthropic credential through a tri-state
  per-project `auth_mode` column on `projects` (migration 0050):
  `NULL` = inherit fleet default (OAuth when
  `settings.claude_code_oauth_token` is set, else API key),
  `"oauth"` = force Claude OAuth, `"api_key"` = force API key.
  Dispatcher's `_resolve_auth_mode()` picks the effective mode at
  dispatch time and stamps it on `WorkerInput`; the shared
  `coder_core.workers._auth_env.apply_claude_auth_env()` helper
  assembles the env block handed to each role's `claude` subprocess
  and explicitly *pops* the competing credential so the CLI's own
  preference order can't silently cross-wire the wrong one. All
  five role workers + the re-prompt helper use it. Admin
  `PATCH /v1/_admin/projects/{id}/auth-mode` writes the column plus
  a `project.set_auth_mode` audit event; `AuthModeCard` on
  `ProjectDetail` exposes the three-option toggle.
  `scripts/verify_oauth_auth_mode.py` exercises dispatcher +
  env-helper + child-process env shape end-to-end (3 scenarios
  green). 319 LoC of tests across `test_auth.py`,
  `test_auth_env.py`, `test_auth_mode_admin.py`. Prod: `coder` runs
  on `auth_mode=NULL` (fleet default). Decision-log ADR for why
  OAuth, which credential storage shape, and rotation story is
  nice-to-have for future reference but not blocking — the code +
  audit trail are self-describing.

## Links

- Designs: [worker-roles](../../designs/active/worker-roles.md),
  [tenancy-and-access](../../designs/active/tenancy-and-access.md)
- Related components: [impersonation](./impersonation.md),
  [multi-tenancy](./multi-tenancy.md),
  [tenant-isolation](../delivery/tenant-isolation.md),
  [audit-log](./audit-log.md), [admin-panel](../knowledge/admin-panel.md)
