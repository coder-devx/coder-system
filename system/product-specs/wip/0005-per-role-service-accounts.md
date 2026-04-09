---
id: "0005"
title: Per-role service accounts
type: spec
status: wip
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0001", "0004", "0007"]
---

# Per-role service accounts

**Phase:** Next (first real work gets done)
**Progress:** 0 / 6 acceptance criteria

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
  permissions required for its role's capabilities.
- Workers obtain their role credential by asking the SysAdmin broker,
  never by reading static secrets.
- Credentials are short-lived and refreshed on rotation — no long-lived
  keys on disk.
- Per-project isolation: a developer role operating on project A cannot
  access project B's secrets, bucket, or GitHub org.
- The scope of each role's account is documented and testable.

## Non-goals

- Per-role GitHub Apps (v1 stays with a shared GitHub App with
  per-project installations; granular GitHub identities come later).
- Rebuilding the underlying IAM model on a non-GCP cloud.
- Human SSO — this spec is about worker identity, not operator access.

## Scope

- Terraform (or equivalent) defining one GCP SA per role per project,
  with named IAM bindings.
- SysAdmin broker endpoint: `POST /impersonate/{role}` returning a
  short-lived token scoped to the caller's project.
- Secret Manager layout: `coder/{project}/{role}/...`.
- Worker bootstrap change: every role worker replaces its stub
  credential with a fresh token from the broker on startup and on
  rotation.
- Audit log: every broker issuance recorded with caller, project, role,
  expiry.
- A "capability matrix" doc generated from the Terraform — inputs:
  roles, outputs: granted permissions.

## Acceptance criteria

- [ ] Each role listed in the roles registry has exactly one GCP SA per
      active project, created by Terraform.
- [ ] The developer worker (spec `0004`) no longer uses a stub
      credential and instead fetches a scoped token from the broker.
- [ ] A developer-role token cannot read a secret under
      `coder/{other_project}/...`.
- [ ] A PM-role token cannot write to the developer role's GCS bucket.
- [ ] Broker-issued tokens expire within their declared TTL and
      subsequent calls fail with `401`.
- [ ] The capability matrix is regenerated in CI whenever role
      permissions change and fails the build on drift.

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
