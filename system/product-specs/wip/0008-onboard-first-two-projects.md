---
id: "0008"
title: Onboard first two projects
type: spec
status: wip
owner: ro
created: 2026-04-09
updated: 2026-04-09
deprecated_at:
reason:
served_by_designs: ["0004"]
related_specs: ["0001", "0002", "0004", "0005", "0006", "0007"]
---

# Onboard first two projects

**Phase:** Later (promotion criterion for design 0004 → active)
**Progress:** 0 / 7 acceptance criteria

## Problem

Specs `0001` through `0007` each look correct in isolation, but the
only way to know the rebuild actually works is to run it against a
real project end-to-end. VibeTrade is the natural first project —
it's the one the old `coder-agent` served, and re-onboarding it proves
parity. A single project isn't enough though: multi-tenancy only gets
exercised with a second project running in parallel, with real
isolation between them. This spec is the end-to-end test that gates
design `0004`'s promotion from `wip` to `active`.

## Users / personas

- **Ro (human owner)** — needs proof that switching from the old
  system to the new one doesn't lose anything and that a second
  project genuinely runs alongside without cross-bleed.
- **Software Architect** — validates the promotion criteria from
  design `0004`.
- **Developer worker** (spec `0004`) — this is the first time it runs
  under real conditions against two distinct repos.
- **Future teammates** — use the second project's onboarding as the
  canonical playbook for every subsequent project.

## Goals

- VibeTrade re-onboarded onto the new `coder-core` + `coder-admin`
  stack end-to-end: knowledge repo wired, developer worker running,
  pipeline visible in admin.
- A second, smaller project onboarded alongside VibeTrade, living in
  its own GitHub org and GCP project.
- Both projects runnable in parallel with demonstrable isolation —
  credentials, secrets, tasks, and logs never cross.
- A written onboarding runbook that the next project can follow
  without Ro's help.
- All of design `0004`'s promotion criteria satisfied and checked off.

## Non-goals

- Migrating historical VibeTrade state from the old `coder-agent`
  (there isn't any worth migrating).
- A polished onboarding self-service flow — v1 onboarding can be
  hands-on and scripted.
- Onboarding a third project — two is the isolation proof; more is
  just repetition.

## Scope

- Create VibeTrade's new `coder-system` knowledge repo from the
  `template/` blueprint and seed it with the existing specs/designs.
- Terraform a VibeTrade GCP project and a second-project GCP project,
  each with their role SAs per spec `0005`.
- Register both projects via the Core API (spec `0001`) and verify
  they show up in the admin panel.
- Run a real developer task on VibeTrade via the developer worker
  (spec `0004`) and a second on the other project.
- Walk through the pipeline UI (spec `0006`) for both runs in parallel.
- Produce a `runbooks/onboard-project.md` runbook captured during the
  second onboarding.
- Tick through each of design `0004`'s promotion criteria and link the
  evidence.

## Acceptance criteria

- [ ] VibeTrade is registered as a project in the new Core and its
      knowledge repo is served through the knowledge API.
- [ ] A developer task enqueued on VibeTrade runs end-to-end and
      produces a commit on a feature branch in the VibeTrade repo.
- [ ] A second project exists with its own GitHub org, GCP project,
      and role service accounts.
- [ ] A developer task enqueued on the second project runs to success
      without touching VibeTrade's repos, secrets, or logs.
- [ ] Both projects' pipelines are visible side-by-side in the admin
      panel (via project switcher) with no data bleed.
- [ ] Ro can drive both projects from a local Claude Code using
      impersonation (spec `0007`).
- [ ] A new `runbooks/onboard-project.md` exists and was actually
      followed to onboard the second project.

## Metrics

- **Parity:** VibeTrade's developer loop produces equivalent output on
  the new system to what it did on the old `coder-agent` (same kind of
  commits, same test pass rate on the same input).
- **Isolation:** 0 cross-project reads or writes across a one-week
  window of dual-project operation.
- **Onboarding effort:** second project onboarded in under half a day
  using only the runbook.

## Open questions

- Which second project? A small internal utility, or a friendly
  external one?
- Do we keep the old `coder-agent` running as a fallback during
  VibeTrade's re-onboarding, or cut over hard?
- What's the rollback plan if VibeTrade's parity test fails on the new
  stack?

## Links

- Designs: [`0004`](../../designs/wip/0001-generalize-coder-from-vibetrade.md) (build plan step 8 + promotion criteria)
- Related specs: [`0001`](./0001-multi-tenant-project-crud.md), [`0002`](./0002-knowledge-repo-read-api.md), [`0004`](./0004-developer-worker-v1.md), [`0005`](./0005-per-role-service-accounts.md), [`0006`](./0006-pipeline-ui-in-admin.md), [`0007`](./0007-local-agent-impersonation.md)
