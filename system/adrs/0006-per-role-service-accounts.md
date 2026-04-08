---
id: "0006"
title: Each role-worker gets its own GCP service account
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: ["0002", "0004"]
---

# ADR 0006 — Each role-worker gets its own GCP service account

## Context

Workers fill roles, and roles have very different permission needs. The
System Admin role provisions infra; the Developer role writes code; the
Reviewer role only reads. We have to decide how worker identity maps to
GCP service accounts.

## Options considered

1. **One service account for all workers** — simple, but every worker
   gets the union of permissions. The Developer worker would have IAM
   write access "just in case" the System Admin worker needs it.
2. **One service account per role-worker** — each role's SA has the
   minimum permissions for that role. The System Admin worker is the
   only broker that can grant time-bounded access to other workers.
3. **One service account per (role, project) pair** — strongest isolation
   but explosive in number of SAs.

## Decision

One GCP service account per role-worker. Naming convention:
`coder-{role}@{gcp-project}.iam.gserviceaccount.com`.

## Rationale

Role-based identity is the natural unit. It maps cleanly to the role
contract documented in `system/roles/`. Per-project SAs are over-fitted
because per-project isolation is already enforced in software (see
[ADR 0005](./0005-multi-tenant-coder-core.md)).

## Consequences

- Positive: a leaked credential blasts only one role's permissions.
- Positive: SA names match role names — auditing IAM is human-readable.
- Positive: System Admin worker becomes the only broker for elevated
  access, and it's a small auditable surface.
- Negative: more SAs to manage; adding a new role means a new SA + IAM
  bindings.
- Follow-up: provisioning a new role-worker must include a Terraform (or
  equivalent) module that creates the SA with the role's documented
  permissions. Drift between `roles/{role}.md` "Permissions" section and
  the actual IAM bindings is a bug — Consultant role watches for it.
