---
id: service-accounts
title: Service Accounts
type: design
status: active
owner: ro
created: 2026-05-03
updated: 2026-05-03
last_verified_at: 2026-05-03
implements_specs: [service-accounts]
decided_by: ['0006']
related_designs: [tenancy-and-access, impersonation, multi-tenancy, audit-log, worker-roles]
affects_services: [coder-core]
affects_repos: [coder-core, coder-system]
parent: tenancy-and-access
---

# Service Accounts

## What it is

Every worker role in Coder runs under a dedicated GCP service account
provisioned by Terraform. The SA-per-role split (architect, developer,
pm, reviewer, team-manager, sysadmin, escalation-watcher) was decided
in ADR [0006](../../adrs/0006-per-role-service-accounts.md). Workers
never read static keys: at dispatch time they call the
[impersonation](./impersonation.md) broker and receive a short-lived
JWT plus, when running in GCP, an OAuth2 access token minted via the
IAM Credentials API. Per-project isolation is enforced both in software
(broker stamps a `project_id` claim) and in IAM (per-secret bindings
on `coder-{project}-{role}-*` secrets).

## Architecture

```mermaid
flowchart TB
  tf["Terraform<br/>infra/terraform/"]
  yaml["roles.yaml"]
  matrix["CAPABILITY_MATRIX.md<br/>(generated)"]
  gcp[("GCP project<br/>vibedevx")]
  sm["Secret Manager<br/>coder-{project}-{role}-anthropic-api-key"]
  sa["coder-{role}@vibedevx.iam"]

  worker["Worker<br/>(role=developer, project=foo)"]
  broker["LocalBroker / GcpBroker<br/>integrations/broker.py"]
  api["POST /v1/projects/{id}/impersonate/{role}<br/>api/impersonate.py"]

  yaml --> tf --> gcp
  tf --> sa
  tf --> sm
  yaml -. capability_matrix.py .-> matrix

  worker -->|X-Api-Key| api --> broker
  broker -->|JWT (HS256)| worker
  broker -->|OAuth2 access token<br/>(GcpBroker only)| worker
  worker -.access_token.-> sm --> worker
  sa -.IAM grant.-> sm
```

### Parts

- **Terraform — `coder-core/infra/terraform/`.**
  - `roles.tf` provisions one GCP service account per role,
    iterating over `roles.yaml`.
  - `secrets.tf` provisions per-project Secret Manager entries
    (`coder-{project}-{role}-anthropic-api-key`) and the IAM
    binding that grants the matching role SA `roles/secretAccessor`
    on that secret only — cross-project reads fail at IAM with
    `IAM_PERMISSION_DENIED`.
  - `variables.tf` — `var.projects` is the list of project ids;
    `secrets.tf` does `for_each = toset(var.projects)`.
  - `outputs.tf`, `versions.tf` — wiring.
- **`roles.yaml`** — the authoritative role definition file (one
  document per role, each listing the IAM permissions and any
  per-role config). The renderer
  `infra/terraform/capability_matrix.py` regenerates
  `CAPABILITY_MATRIX.md` from it; CI runs `--check` and fails the
  build on drift.
- **Broker — `coder_core/integrations/broker.py`.**
  - `LocalBroker` (default for local / test) mints HS256 JWTs only;
    `gcp_access_token=None` so callers can detect that GCP IAM is
    not in the loop.
  - `GcpBroker` wraps `LocalBroker` and additionally calls the IAM
    Credentials API to mint a real OAuth2 access token for
    `coder-{role}@vibedevx.iam.gserviceaccount.com`. This is what
    runs in production.
- **Broker endpoint — `coder_core/api/impersonate.py`.**
  `POST /v1/projects/{project_id}/impersonate/{role}` accepts an
  `X-Api-Key` (per-project), checks scope, and returns
  `BrokerTokenResponse{ jwt, gcp_access_token? }`. The route is
  the single entry point — workers never instantiate the broker
  directly.
- **`fetch_project_anthropic_key(broker, gcp_project, project_id)`**
  — the helper a worker calls with its broker token to read the
  per-project secret. Hard-fails on `SecretReadError`; a worker
  with no key cannot proceed.
- **CI capability-matrix gate.** ADR
  [0008](../../adrs/0008-ci-validation-of-knowledge-repo.md) runs
  `capability_matrix.py --check` alongside `tofu fmt -check` and
  `tofu validate` on every PR. Drift between `roles.yaml` and
  `CAPABILITY_MATRIX.md` blocks merge.

### Data flow

1. Worker is dispatched with `role=developer, project_id=foo`.
2. Dispatcher calls
   `POST /v1/projects/foo/impersonate/developer` with the
   per-project API key.
3. Broker checks scope, mints a JWT (`role=developer`,
   `project_id=foo`, short expiry) and (if GcpBroker) calls IAM
   Credentials to mint an OAuth2 access token for
   `coder-developer@vibedevx.iam`.
4. Dispatcher passes both to the worker subprocess; worker uses the
   access token to read
   `coder-foo-developer-anthropic-api-key` from Secret Manager.
5. A wrong-project worker with token for project `foo` trying to
   read project `bar`'s secret hits IAM `403` — defense in depth
   with the application-level check.
6. Token expiry is enforced by `LocalBroker.verify`; expired
   tokens are rejected at the API boundary.

### Invariants

- **No static keys in process env.** Anthropic keys are read
  per-task through the broker; worker subprocess env carries the
  short-lived token, not the secret.
- **Cross-project reads fail at IAM.** Even if an application-level
  bug bypassed the JWT check, GCP would still 403 the read.
- **`roles.yaml` is the single source of truth.** Changing IAM
  permissions for a role means editing `roles.yaml` and letting
  Terraform + `capability_matrix.py` propagate it. Hand-edited
  IAM bindings drift and are caught by `tofu plan`.
- **Token expiry is enforced both ways.** The JWT carries `exp`;
  `LocalBroker.verify` rejects past-due. GCP access tokens are
  themselves time-bounded by IAM.

## Interfaces

- **Broker HTTP:**
  `POST /v1/projects/{project_id}/impersonate/{role}` (X-Api-Key
  auth) → `{ jwt, gcp_access_token? }`.
- **Terraform:** `coder-core/infra/terraform/`. State in
  `gs://vibedevx-coder-core-tfstate`. Inputs: `roles.yaml`,
  `var.projects`. Outputs: per-role SAs, per-secret IAM bindings.
- **Python helpers:**
  `fetch_project_anthropic_key(broker, gcp_project, project_id)`,
  `LocalBroker.verify(token)`.
- **Generated artifacts:** `CAPABILITY_MATRIX.md` (do not
  hand-edit — regenerated from `roles.yaml`).

## Evolution

- ADR [0006](../../adrs/0006-per-role-service-accounts.md) — split
  into one SA per role rather than one for all workers.
- 0006 — Terraform module shape (`roles.tf`, `secrets.tf`),
  per-secret IAM bindings, `var.projects`.
- 0008 — CI gate: capability-matrix drift check + `tofu fmt -check`
  + `tofu validate`.
- 0027 — broker JWT expiry enforced server-side (was previously
  trusted from the worker's claim).

## Links

- Specs: [service-accounts](../../product-specs/active/service-accounts.md),
  [tenancy-and-access](../../product-specs/active/tenancy-and-access.md)
- Designs: [impersonation](./impersonation.md),
  [tenancy-and-access](./tenancy-and-access.md),
  [multi-tenancy](./multi-tenancy.md),
  [worker-roles](./worker-roles.md),
  [audit-log](./audit-log.md)
- ADRs: [0006](../../adrs/0006-per-role-service-accounts.md),
  [0008](../../adrs/0008-ci-validation-of-knowledge-repo.md)
- Services: `coder-core`
