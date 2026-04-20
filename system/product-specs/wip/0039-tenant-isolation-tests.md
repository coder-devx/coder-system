---
id: '0039'
title: Tenant isolation test harness
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
served_by_designs: ['0039']
related_specs:
  - multi-tenancy
  - service-accounts
  - impersonation
  - audit-log
  - knowledge-api
  - task-orchestration
---

# 0039 — Tenant isolation test harness

## Problem

Tenant isolation today is a _property we believe holds_ by reading code:
`require_project_auth` middleware rejects cross-tenant reads,
`record_audit_event` writes inside the caller's transaction, role SAs
have no IAM grant on other projects' secrets. None of that is
_continuously verified_. A future refactor that accidentally drops the
`project_id` filter on one endpoint, or loosens an IAM binding, or
leaks a row through a worker-path shortcut, would not be caught by any
test — and would likely surface only under pen test or incident.

Phase 6 exists to close the gap between "works" and "safe to let a
customer near it." 0037 (audit log) gives us forensics after the
fact; 0038 (secret rotation) cuts blast radius of a leaked credential;
0039 is the proactive half — a CI-enforced suite asserting that two
projects _cannot_ see each other across every endpoint, every token
type, every worker path, and every storage surface.

## Users

- **Reviewer-of-deploy (oncall/maintainer)** — needs a red/green signal
  before flipping a release flag or merging a PR that touches request
  handling, auth, or storage.
- **Security-reviewer (later, for pilots)** — needs a coverage report
  naming every boundary the suite exercises, so a gap is an explicit
  TODO rather than a silent miss.
- **PM / Architect workers** — when proposing changes that add a new
  endpoint or table, the worker output schema can reference the suite
  manifest to assert the new surface is covered.

## Goals

- Continuously verify the properties in `multi-tenancy.md`,
  `service-accounts.md`, and `impersonation.md` hold across every
  endpoint, token, and table in the live codebase.
- Fail the build if a PR introduces a project-scoped endpoint that
  isn't covered by the isolation matrix.
- Surface a machine-readable coverage report (endpoint × token × table
  → covered-by-test-id) that the Reviewer worker can consume and that
  the admin panel can render.
- Catch regressions at PR time, not at pen test time. SLO: mean time
  from regression → red CI < 10 minutes.

## Non-goals

- **Fuzzing or property-based testing** — deferred. The harness uses a
  fixed matrix of known boundaries; random input generation is a
  separate effort.
- **Chaos / fault injection** — e.g. simulating a broker-token
  replay attack, a torn audit row, or a network partition. Separate
  spec when we decide we want it.
- **Production traffic replay** — the suite runs against an isolated
  test Postgres + a test GCP project, not prod.
- **Cross-project _ability_** (e.g. "admin can intentionally see both
  projects with admin JWT") — that is a feature of
  `/v1/admin/audit-events` and the admin panel, not an isolation
  violation. The suite asserts admin _can_ see both; non-admin tokens
  _cannot_.
- **Performance / load testing** — separate concern.

## Scope

### In scope

1. **API cross-tenant matrix.** For every project-scoped endpoint in
   `coder-core`, assert:
   - own API key + own project path → 2xx
   - _other_ project's API key + own project path → 401/403
   - own API key + _other_ project path → 401/403 (never 404 _only_,
     because 404-vs-403 leakage is itself a bug — the suite asserts the
     contract defined in [`multi-tenancy.md`](../active/multi-tenancy.md))
   - no token / malformed token → 401
   Parametric over the endpoint manifest (see design).

2. **Token-type mismatch.** For each of the 4 token types
   (per-project API key, impersonation JWT, role SA token, admin JWT):
   assert that an endpoint expecting type X rejects tokens of types
   Y, Z with the documented status and does not partially execute
   (no side effect, no audit row beyond the rejected-auth audit).

3. **Direct-DB row visibility.** For every Postgres table carrying a
   `project_id` column — `projects`, `tasks`, `task_messages`,
   `task_plans`, `task_stage_runs`, `pipeline_runs`,
   `pipeline_run_contexts`, `audit_events`, `sessions`,
   `regression_events`, `secret_rotations` — assert that a read
   scoped to project A (via the repository layer, not raw SQL)
   returns zero rows belonging to project B, even when B has inserted
   rows with the same non-id fields.

4. **Worker-path reads/writes.** Mount a worker using project A's
   impersonation token and assert: (a) knowledge reads fetch only A's
   artifacts, (b) knowledge writes land in A's repo, (c) audit rows
   are stamped with A's `project_id`, (d) attempts to post a
   `task_messages` row with B's `task_id` fail at the repo layer.

5. **GCP IAM isolation.** Using the role SA client library, attempt
   to read project B's Anthropic key secret with project A's role SA;
   assert a 403 `IAM_PERMISSION_DENIED`. Same shape for GitHub App
   private key. Skipped on local/dev runs (no GCP creds); required in
   CI-staging.

6. **Coverage manifest.** A single `isolation_manifest.yaml` lists
   every endpoint, token type, and table the suite knows about, with
   the test IDs that cover each. A CI check fails the build when a
   project-scoped endpoint exists but isn't in the manifest (derived
   by enumerating the FastAPI router and filtering on the
   `require_project_auth` dependency).

### Out of scope

- WebSocket / SSE endpoints (`/events` stream) — covered by a follow-up
  once we decide the contract for cross-tenant subscription attempts.
- Admin panel React components — out-of-process, covered by separate
  admin e2e tests.
- Knowledge-repo GitHub permissions — asserted in a separate Terraform
  `tfsec` policy (noted in Open questions).

## Acceptance criteria

- **AC1.** `tests/isolation/conftest.py` exposes an
  `isolation_projects` fixture that provisions two projects with
  distinct API keys, distinct role-SA tokens, and distinct test
  Postgres rows. Fixture teardown deletes both projects and verifies
  zero residual rows across all `project_id`-scoped tables.

- **AC2.** The API cross-tenant matrix covers every project-scoped
  endpoint registered on the FastAPI app. A CI check
  (`scripts/check_isolation_manifest.py`) fails the build when a new
  endpoint with `Depends(require_project_auth)` is added without a
  manifest entry.

- **AC3.** Token-type mismatch tests cover the 4 token types × the 3
  endpoint authorization classes (project-scoped, admin-only,
  broker-only). Asserts specific status codes, not "some 4xx."

- **AC4.** Direct-DB row-visibility tests cover every Postgres table
  carrying `project_id`. The test inserts a paired row in project B
  and asserts the project-A-scoped repository query does not return
  it. Runs under a rolled-back transaction per test for speed.

- **AC5.** GCP IAM isolation test attempts cross-project Secret
  Manager reads and asserts 403. Runs in CI-staging only; locally the
  test is skipped with a clear reason.

- **AC6.** Suite runtime on CI ≤ 5 minutes P95. The matrix runs in
  parallel by endpoint group.

- **AC7.** The suite is _blocking_ on every PR that touches
  `coder-core/app/routers/`, `coder-core/app/auth/`,
  `coder-core/app/repositories/`, or `coder-core/infra/terraform/`.
  Non-blocking elsewhere.

- **AC8.** A nightly run on staging posts a "green for N days" badge
  to the `/admin/isolation` page; a red run posts to the existing
  regression-alerts Slack webhook with the failing test ID and
  boundary category.

- **AC9.** Coverage report (JSON + admin panel view) lists every
  endpoint / token / table with the test IDs that cover it. A row
  with zero test IDs is a CI failure, not a warning.

- **AC10.** Rolling out the suite does not break existing CI: the
  blocking flag `CI_ISOLATION_SUITE_BLOCKING` defaults to `false` on
  first deploy, flips to `true` after 1 week of consistent green
  runs. Explicit flip via repo settings, audited.

## Metrics

- **Coverage:** % of project-scoped endpoints with a matrix test
  entry. Target 100% (enforced by AC2).
- **Suite runtime (P95):** target < 5 min on CI (AC6).
- **False positive rate:** tests flaking > 1% in a rolling 7-day
  window trigger a quarantine review (not ignore).
- **Time-to-red:** median time from a regression-introducing merge to
  CI red. Target < 10 minutes.
- **Days-since-last-red on staging:** published to `/admin/isolation`
  as the trust indicator.

## Open questions

- **Cross-project token validity.** Today the broker stamps
  `project_id` into role-SA tokens and `LocalBroker.verify` rejects
  wrong-project tokens. Should the test also assert that a _past_
  token from project A, after project A is archived, is rejected?
  Answer probably yes; files a follow-up if no existing test covers it.

- **Knowledge repo GitHub isolation.** Project repos are distinct
  GitHub repos; isolation there is a GitHub IAM concern. Do we assert
  it in this suite (via a test PAT that should have no access to
  repo B)? Leaning: yes, as a `pytest.mark.github` group, gated on a
  CI secret so the local dev loop isn't broken.

- **WebSocket endpoints.** `/events` SSE stream isn't in the
  manifest today. Left as an explicit TODO with a follow-up spec.

- **Archived-project access.** An archived project's resources
  should be invisible to normal listing but retrievable for audit.
  The matrix currently tests active projects only. Do archived-A +
  active-B need a separate axis? Probably yes, noted in design.

## Links

- Related specs:
  [multi-tenancy](../active/multi-tenancy.md),
  [service-accounts](../active/service-accounts.md),
  [impersonation](../active/impersonation.md),
  [audit-log](../active/audit-log.md),
  [knowledge-api](../active/knowledge-api.md),
  [task-orchestration](../active/task-orchestration.md)
- Design: [0039](../../designs/wip/0039-tenant-isolation-tests.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 6 / 0039
