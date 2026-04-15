---
id: "0009"
title: Each managed project has its own GCP project and GitHub org
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: [system-overview]
---

# ADR 0009 — Each managed project has its own GCP project and GitHub org

## Context

Coder itself runs in:

- **GCP project** [`vibedevx`](https://console.cloud.google.com/welcome/new?project=vibedevx) — Coder Core, Admin Panel, Artifact Registry, Secret Manager, IAM.
- **GitHub org** [`coder-devx`](https://github.com/coder-devx) — `coder-core`, `coder-admin`, `coder-system`, future `coder-worker-*` repos.

A **managed project** is a software product Coder operates on behalf of
the user (e.g. VibeTrade). We had to decide where each managed project's
cloud resources and code repositories live.

## Options considered

1. **Everything under Coder's `vibedevx` GCP project and `coder-devx` GitHub org** — single account, single org, easiest to start. Catastrophic blast radius: a misconfigured managed project's IAM, billing alert, or repo permission affects Coder itself. Audit and billing are unisolatable.
2. **Sub-folders / sub-orgs only** — GCP folders inside one Org, GitHub repos prefixed with the project name in `coder-devx`. Better than #1 but still shares the parent's quotas, billing, and admin surface.
3. **One GCP project + one GitHub org per managed project** — full isolation. Each project gets its own billing, its own IAM, its own audit, its own repo administration. More accounts to manage, but the boundaries are real.

## Decision

Option 3. Every managed project gets:

- Its **own GCP project** (the user provides one or Coder provisions one
  during onboarding).
- Its **own GitHub org** (same: provided or provisioned).
- Its own `{project}-coder-system` knowledge repo inside that org,
  instantiated from [`template/`](../../template/).

Coder itself stays in `vibedevx` / `coder-devx` and never co-mingles
its own resources with a managed project's.

## Rationale

- **Blast radius**: a managed project misconfiguration cannot reach Coder
  or another managed project.
- **Billing isolation**: each project's costs are visible and chargeable
  to that project.
- **Audit isolation**: GCP audit logs and GitHub audit logs are
  per-account; the boundary makes "who did what to whom" trivially
  answerable.
- **Permission realism**: GitHub Apps and GCP IAM are designed around
  the org/project boundary. Working within that grain is much less work
  than fighting it.
- **User trust**: a user who hands Coder access to one product cannot
  accidentally hand it access to anything else.

## Consequences

- Positive: hard isolation between Coder, between managed projects, and
  between two managed projects.
- Positive: onboarding is conceptually clean — "give Coder a GCP project
  and a GitHub org" is a sentence the user can act on.
- Negative: more accounts and orgs to provision and monitor. Mitigation:
  the System Admin worker owns the onboarding runbook; provisioning is
  automated.
- Negative: cross-project IAM is the System Admin worker's job, and
  getting it wrong is the most likely security failure mode. Mitigation:
  System Admin is the **only** role with cross-project credentials
  (see [ADR 0006](./0006-per-role-service-accounts.md)). Every other
  worker requests scoped, time-bounded access through it.
- Follow-up: write a "onboard a new managed project" runbook that lists
  the exact GCP APIs to enable, the IAM bindings to create, and the
  GitHub App installation steps.
- Follow-up: extend the validator (and the future Coder API) to track a
  managed-project registry — id, GCP project name, GitHub org, owner.
