---
id: tenant-isolation
title: Tenant isolation test harness
type: spec
status: active
owner: ro
created: 2026-04-19
updated: 2026-04-21
last_verified_at: 2026-04-21
summary: Test-suite harness for the multi-tenancy contract.
served_by_designs: [tenant-isolation]
related_specs:
  - multi-tenancy
  - service-accounts
  - impersonation
  - audit-log
  - knowledge-api
  - task-orchestration
  - admin-panel
parent: delivery-and-infra
---

# Tenant isolation test harness

## What it is

A continuously-verified guarantee that two projects cannot see each
other across every project-scoped API endpoint, every token type,
and every `project_id`-bearing table. What `multi-tenancy.md` asserts
as a property, this component proves on every PR.

The harness is a pytest suite under `coder-core/tests/isolation/`
plus two drift-check scripts run in CI; a coverage endpoint
(`GET /v1/_admin/isolation`) and an admin panel page
(`/admin/isolation`) make the coverage legible to humans and
auditors.

## Capabilities

- **API cross-tenant matrix.** For every endpoint registered with
  `require_project_auth` or `require_project_api_key`, the suite
  asserts that project alpha's credential returns 4xx when used
  against project bravo's path — never 2xx, never 404. The matrix
  parametrises over the endpoint list in the manifest, so a single
  test function covers the breadth of the API surface.

- **Token-type mismatch.** Per token type (project API key,
  impersonation JWT, admin JWT), the suite asserts that an endpoint
  expecting one type rejects the others with the documented status
  and without side effect.

- **Row visibility per table.** For every Postgres table with a
  `project_id` column (20 tables as of 2026-04-21), the repository
  layer's project-scoped read must not return another project's
  rows, even when non-id fields collide.

- **Archived-project invariants.** An archived project's API key,
  impersonation JWT (issued *before* archive), and direct
  `GET /v1/projects/{id}` all stop resolving immediately after
  `POST /v1/projects/{id}/archive`. No bearer-only fast path sneaks
  a previously-valid JWT through.

- **Manifest drift check.** `scripts/check_isolation_manifest.py`
  enumerates the live FastAPI app and fails if any route bearing
  `require_project_auth` / `require_project_api_key` is missing from
  `tests/isolation/isolation_manifest.yaml`. Wired into CI's `check`
  job, so "added an endpoint but forgot the matrix" is a build
  failure at PR time.

- **Coverage drift check.** `tests/isolation/coverage_report.py --check`
  regenerates the summary in memory and compares it against the
  committed `isolation_coverage.json`. Keeps the human-readable
  snapshot in sync with the manifest; same pattern as the
  `capability_matrix.py --check` guard.

- **Coverage dashboard.** `/admin/isolation` fetches the live
  summary (every endpoint / table / token with its covering test
  ids) and renders three tables. Reviewers reading a PR can point
  to this page and say "your new endpoint is covered" rather than
  auditing by hand.

## Interfaces

- **CLI / test runner:** `uv run pytest tests/isolation/` — runs the
  full suite locally; `uv run pytest` includes it automatically in
  CI.
- **Manifest file:** `tests/isolation/isolation_manifest.yaml` —
  single source of truth for which endpoints, tables, tokens, and
  GCP surfaces the harness covers. Hand-edited for new entries; the
  drift check enforces completeness.
- **Admin HTTP endpoint:** `GET /v1/_admin/isolation` — admin-JWT
  gated, returns the parsed manifest + coverage summary as JSON.
- **Admin page:** `/admin/isolation` in `coder-admin`, behind
  `VITE_ISOLATION_VIEW_ENABLED`.
- **CI hooks:**
  - `check_isolation_manifest.py` in the `check` job.
  - `coverage_report.py --check` in the `check` job.
  - The full pytest suite in the same `check` job, so isolation
    tests block every PR.

## Dependencies

- **`multi-tenancy`** — provides the property being tested. Every
  row in the matrix is a restatement of a multi-tenancy invariant in
  code-form.
- **`service-accounts`** — the per-role SA identities the harness
  mints impersonation tokens against.
- **`impersonation`** — the broker token path (`LocalBroker` for
  tests) the suite uses to prove bearer-token isolation.
- **`audit-log`** — the suite asserts that cross-tenant rejection
  does not emit a partial audit row.
- **`admin-panel`** — the UI surface for the coverage view.

## Operational notes

- **Runtime P95 on CI:** seconds (tests run against in-memory
  SQLite). The 5-min SLO from the spec is comfortably met.
- **Drift handling:** when CI flags manifest drift, the failure
  message points at the exact YAML file and tells the author what
  to add (a `covers_tests:` entry or `skip: true` + `reason:`). No
  way to merge a new project-scoped endpoint without at least an
  explicit `skip`.
- **Coverage snapshot:** `isolation_coverage.json` is committed at
  the repo root so a reviewer sees the same numbers the admin page
  shows. The `generated_at` timestamp is excluded from drift
  comparison so a re-run without content changes doesn't flap.
- **Containerisation:** the Dockerfile copies just
  `tests/isolation/isolation_manifest.yaml` (the `.dockerignore`
  has a matching un-ignore rule) so the runtime
  `/v1/_admin/isolation` endpoint can read it in the Cloud Run
  container. The rest of `tests/` is intentionally still excluded.

## Coverage at ship (2026-04-21)

- **Endpoints:** 54/60 covered. The 6 skipped entries have explicit
  reasons in the manifest (3 public reads, 2 admin-JWT endpoints
  that cross tenants by design, 1 redirect-only route).
- **Tables:** 20/20 covered.
- **Tokens:** 3/3 covered (`project_api_key`, `impersonation_jwt`,
  `admin_jwt`).
- **GCP surfaces:** 0/3 covered — **deferred**. The three registered
  surfaces (`project_anthropic_key`, `admin_jwt_signing_key`,
  `github_app_private_key`) require a CI-staging GCP project with
  two sibling projects provisioned against the same terraform module.
  Two of the three (admin JWT, GitHub App key) are fleet singletons
  with no cross-tenant dimension; they stay skipped permanently.
  The remaining one (`project_anthropic_key`) will move to covered
  once CI-staging exists. Tracked in a follow-up spec for
  "CI-staging for isolation" — see the Open items below.

## Open items

- **AC5 — GCP IAM cross-tenant assertion.** The harness asserts
  cross-tenant rejection at the HTTP and database layers today.
  It does **not** assert that project A's role SA gets `403
  IAM_PERMISSION_DENIED` when attempting to read project B's
  `coder-{b}-developer-anthropic-api-key` Secret Manager version.
  The Terraform in `infra/terraform/secrets.tf` grants per-secret
  `secretAccessor` only — the property should hold — but nothing
  verifies it end-to-end. Blocked on CI-staging: the test needs two
  real projects in a real GCP project, and we currently run CI
  against in-memory SQLite with no GCP calls. A future spec will
  introduce CI-staging for this and a couple of other "needs real
  infra" cases; that spec will pick up AC5 as one of its headline
  tests.

- **Nightly staging run.** Spec 0039 AC8 called for a nightly run
  against staging posting a "green for N days" badge to
  `/admin/isolation`. Same CI-staging blocker. The admin page is
  live and renders the current coverage; adding a
  run-history-over-time strip is a minor follow-up once the nightly
  exists to populate it.

## Evolution

- 2026-04-21 — Component shipped into `active/` from 0039. Harness
  covers 54/60 endpoints, 20/20 tables, 3/3 tokens. Archived-project
  invariants added. Manifest drift check + coverage JSON drift
  check wired into CI. Admin page unblocked (Dockerfile + dockerignore
  fix). GCP IAM dimension deferred to a future CI-staging spec.
