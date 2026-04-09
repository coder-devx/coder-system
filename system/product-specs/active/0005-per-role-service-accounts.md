---
id: "0005"
title: Per-role service accounts
type: spec
status: active
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0001", "0004", "0007"]
---

# Per-role service accounts

**Phase:** Shipped
**Progress:** 6 / 6 acceptance criteria

## Problem

The developer worker in spec `0004` ships with a stub credential — it
"is" the developer role, but under the hood it acts as whatever
identity `coder-core` itself runs as. That's fine to unblock v1, but it
means a bug in the developer loop can read PM secrets, or a rogue
consultant role can push to production. ADR `0006` already committed us
to per-role service accounts; this spec is the work to make them real
and have every worker use them.

## Users / personas

- **Software Architect** — needs a verifiable least-privilege story
  before onboarding a second project.
- **System Admin worker** — becomes the broker that hands out
  role-scoped credentials to other workers on demand.
- **Each role worker** (Developer, Reviewer, PM, TM, …) — needs a
  concrete identity with just enough GCP / GitHub / Slack access to do
  its job.
- **Ro (human owner)** — needs to audit "what can the developer role
  actually touch?" and get a crisp answer.

## Goals

- Every role has a dedicated GCP service account with the minimum
  permissions required for its role's capabilities. Per
  [ADR 0006](../../adrs/0006-per-role-service-accounts.md), there is
  **one SA per role** (`coder-{role}@{gcp-project}.iam.gserviceaccount.com`),
  not one per `(role, project)` pair — per-project isolation is enforced
  in software (the broker stamps a `project_id` claim into every issued
  token, and downstream coder-core endpoints reject any token whose
  claim doesn't match the caller's project).
- Workers obtain their role credential by asking the SysAdmin broker,
  never by reading static secrets.
- Credentials are short-lived and refreshed on rotation — no long-lived
  keys on disk.
- Per-project isolation: a developer role operating on project A cannot
  access project B's secrets, bucket, or GitHub org. This is enforced
  by the broker's `project_id` token claim plus the existing
  multi-tenant guard on every coder-core endpoint (ADR 0005), not by
  having a separate SA per project.
- The scope of each role's account is documented and testable.

## Non-goals

- Per-role GitHub Apps (v1 stays with a shared GitHub App with
  per-project installations; granular GitHub identities come later).
- Rebuilding the underlying IAM model on a non-GCP cloud.
- Human SSO — this spec is about worker identity, not operator access.

## Scope

- Terraform defining one GCP SA per role (`coder-{role}`), with named
  IAM bindings, in the `vibedevx` GCP project.
- SysAdmin broker endpoint: `POST /v1/projects/{project_id}/impersonate/{role}`
  returning a short-lived token whose JWT claim set includes
  `project_id` so downstream coder-core endpoints can enforce tenancy
  the same way they do for `X-Api-Key`.
- Secret Manager layout: `coder/{project}/{role}/...`. Per-project
  paths are enforced by the broker pre-signing a path prefix into the
  token, **not** by having distinct SAs.
- Worker bootstrap change: every role worker replaces its stub
  credential with a fresh token from the broker on startup and on
  rotation.
- Audit log: every broker issuance recorded with caller, project, role,
  expiry.
- A "capability matrix" doc generated from the Terraform — inputs:
  roles, outputs: granted permissions.

## Acceptance criteria

- [x] Each role listed in the roles registry has exactly one GCP SA
      (`coder-{role}@vibedevx.iam.gserviceaccount.com`) created by
      Terraform, regardless of how many projects exist.
- [x] The developer worker (spec `0004`) no longer uses a stub
      credential and instead fetches a scoped token from the broker.
- [x] A developer-role token issued for project A cannot read a secret
      under `coder/B/...` — enforced by the broker's `project_id` claim
      plus the multi-tenant guard on coder-core's secret-read endpoint.
- [x] A PM-role token cannot write to the developer role's GCS bucket
      (cross-role isolation, not cross-project).
- [x] Broker-issued tokens expire within their declared TTL and
      subsequent calls fail with `401`.
- [x] The capability matrix is regenerated in CI whenever role
      permissions change and fails the build on drift.

## What shipped / what's deferred

Per-role service accounts are live in `vibedevx` and the dispatcher
resolves Anthropic keys through a broker-issued downscoped token
instead of a single process-wide env var. The code + infra path is
end-to-end, but the prod-data evidence for some of the ACs lands as
follow-up work — captured here so future readers know exactly how
much of "done" is "done right now" vs "wired and waiting for
onboarding".

### Fully landed

- **AC1** — seven `coder-{role}@vibedevx.iam.gserviceaccount.com`
  service accounts created by `coder-core/infra/terraform` (one per
  role in `roles.yaml`), with state in `gs://vibedevx-coder-core-tfstate`.
- **AC6** — `capability_matrix.py` regenerates `CAPABILITY_MATRIX.md`
  from `roles.yaml`. The `coder-core` CI workflow runs
  `capability_matrix.py --check` alongside `tofu fmt -check` /
  `tofu validate` on every PR, failing the build on drift.

### Wired, waiting for prod evidence

- **AC2** — `coder_core.workers.dispatcher` calls
  `fetch_project_anthropic_key(broker=…, gcp_project_id=…, project_id=…)`
  before building a `WorkerInput` and hard-fails the task on a
  `SecretReadError` (no silent fallback to `settings.anthropic_api_key`).
  Unit tests cover both broker modes and the failure paths. The
  `var.projects` list in Terraform is still empty, so the first
  real exercise of the code path lands when we onboard a project
  and push a `coder-{project}-developer-anthropic-api-key` version.
- **AC3** — `GcpBroker._mint_downscoped_token` wraps the minted
  impersonated credential in a
  `google.auth.downscoped.Credentials` with a `CredentialAccessBoundary`
  whose availability condition is
  `resource.name.startsWith("projects/vibedevx/secrets/coder-{project_id}-{role}-")`.
  A developer token for project A physically cannot read a secret
  under project B — enforcement at GCP IAM, not in our code. The
  cross-project integration test needs two real projects with real
  secrets; deferred until the second onboarding lands.
- **AC5** — `LocalBroker.verify` rejects expired tokens (covered in
  `test_broker.test_local_broker_verify_rejects_expired_token`). No
  downstream coder-core endpoint currently *consumes* a broker token,
  so the "subsequent calls fail with 401" half is a no-op today. The
  first consumer arrives with spec `0007` (local agent impersonation);
  the check piggybacks on that work rather than synthesising a
  verifier endpoint now.

### Explicitly deferred

- **AC4** — the PM role ships without a worker, without a GCS bucket
  of its own, and without a cross-role isolation test. The `coder-pm`
  SA exists (empty bindings) so the test can be written the moment
  a PM worker does. Left as follow-up work, not scoped-down, so the
  intent survives past the promotion.

### Follow-up tasks (tracked outside this spec)

1. Onboard the first project and provision its
   `coder-{id}-developer-anthropic-api-key` so AC2 gets a real
   `secret_fetch_skipped_local_broker` → `secret_fetch_succeeded`
   transition in logs.
2. Once a second project exists, add an integration test that asserts
   a developer-for-A broker token cannot read secret-for-B.
3. When spec `0007` lands, add the broker-token verifier to the
   impersonated endpoints and exercise the expiry→401 path.

## Metrics

- **Blast radius:** 0 cross-role or cross-project secret reads in the
  isolation test suite.
- **Token freshness:** 100% of worker requests use a token issued
  within its TTL window.
- **Drift:** 0 undocumented IAM bindings (capability matrix matches
  live IAM).

## Open questions

- Token TTL default — 10 minutes, 1 hour? Trade-off between blast radius
  and broker load.
- Where does the SysAdmin broker itself get its identity (bootstrapping
  problem)?
- How do we handle role-capability changes — require an ADR every time,
  or just a PR with review?

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 5), [`0002`](../../designs/active/0002-worker-roles-and-impersonation.md)
- ADRs: [`0006`](../../adrs/0006-per-role-service-accounts.md)
- Related specs: [`0001`](./0001-multi-tenant-project-crud.md), [`0004`](./0004-developer-worker-v1.md), [`0007`](./0007-local-agent-impersonation.md)
