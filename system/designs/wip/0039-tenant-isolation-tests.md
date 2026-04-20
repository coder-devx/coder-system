---
id: '0039'
title: Tenant isolation test harness
type: design
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
implements_specs: ['0039']
related_designs:
  - system-overview
  - worker-roles
  - impersonation
  - audit-log
  - worker-communication
  - knowledge-write-api
affects_services:
  - coder-core
  - coder-admin
---

# 0039 — Tenant isolation test harness (design)

## Context

Spec [0039](../../product-specs/wip/0039-tenant-isolation-tests.md)
defines the properties we want continuously verified. This design
describes _how_: a parametric pytest suite driven by a single manifest,
plus a CI check that enforces the manifest stays in sync with the
FastAPI router, plus a thin admin surface for the staging trust badge.

Two goals shape the design:

1. **A new endpoint cannot be added without the author noticing the
   isolation matrix.** A build break on manifest drift is louder
   than any doc instruction.

2. **The suite exercises the real authorization path, not a mock.**
   The test mounts the actual FastAPI app, issues real API keys
   through the project-create flow, obtains real broker tokens, and
   hits real repository layers against a real (test) Postgres.

## Goals / non-goals

### Goals

- Fully parametric matrix over (endpoint × token × project).
- Single source of truth: `tests/isolation/isolation_manifest.yaml`.
- Drift-detection CI check: manifest must cover every project-scoped
  endpoint the FastAPI app exposes.
- Direct-repository tests for row-visibility, not end-to-end only.
- GCP IAM tests isolated to a `@pytest.mark.gcp` group, skipped locally.

### Non-goals

- Replacing the existing unit / integration suites. This is an
  additive, boundary-focused suite.
- Fuzzing or property-based generation (see spec non-goals).
- Production-data-shaped performance tests.

## Architecture

```mermaid
flowchart TB
  subgraph ci [CI / Nightly]
    pr[PR build]
    nightly[Nightly staging run]
    drift[check_isolation_manifest.py]
  end

  subgraph suite ["tests/isolation/"]
    conf[conftest.py<br/>isolation_projects fixture]
    manifest[(isolation_manifest.yaml)]
    api_matrix[test_api_cross_tenant.py]
    token_mix[test_token_type_mismatch.py]
    db_rows[test_row_visibility.py]
    worker[test_worker_paths.py]
    gcp[test_gcp_iam.py]
    report[coverage_report.py]
  end

  subgraph targets [System under test]
    app[FastAPI app<br/>coder_core.main]
    repos[Repository layer]
    pg[(Postgres)]
    broker[LocalBroker]
    sm[GCP Secret Manager]
  end

  subgraph admin [coder-admin]
    page[/admin/isolation]
  end

  pr --> drift
  pr --> api_matrix
  pr --> token_mix
  pr --> db_rows
  pr --> worker
  nightly --> api_matrix
  nightly --> token_mix
  nightly --> db_rows
  nightly --> worker
  nightly --> gcp

  drift -. reads router of .-> app
  drift -. compares to .-> manifest

  api_matrix --> conf
  token_mix --> conf
  db_rows --> conf
  worker --> conf

  conf --> app
  conf --> broker
  conf --> pg

  api_matrix --> app
  token_mix --> app
  db_rows --> repos
  repos --> pg
  worker --> app
  worker --> broker
  gcp --> sm

  api_matrix --> report
  token_mix --> report
  db_rows --> report
  worker --> report
  gcp --> report

  report --> page
  nightly -. red run posts to .-> slack[Slack regression-alerts]
```

## Parts

### 1. The fixture: `isolation_projects`

`tests/isolation/conftest.py` exposes one fixture used by every test:

```python
@pytest.fixture(scope="session")
def isolation_projects(db_session, app_client) -> tuple[IsolationProject, IsolationProject]:
    """
    Provision two projects through the real CRUD endpoints, mint real
    API keys, obtain real role-SA tokens for each, and seed one
    pipeline-run's worth of per-project data on each. Teardown at
    session exit archives both, verifies zero residual rows across
    every project_id-scoped table, then deletes archived records.
    """
```

`IsolationProject` is a small dataclass:

```python
@dataclass(frozen=True)
class IsolationProject:
    project_id: str
    api_key: str                     # from POST /v1/projects
    impersonation_tokens: dict[str, str]  # role -> JWT, all 7 roles
    seed_task_id: str                # pre-inserted to give rows to query
    seed_pipeline_run_id: str
    seed_audit_event_id: str
    seed_secret_rotation_id: str | None
```

Scope is `session` — teardown cleanup is expensive (verifies every
table is clean), so we amortize. Individual tests wrap work in
`db_session.begin_nested()` and roll back, not creating new projects.

### 2. The manifest: `isolation_manifest.yaml`

Single source of truth for what the suite knows about. Shape:

```yaml
endpoints:
  - path: /v1/projects/{project_id}/tasks
    method: POST
    auth: project_api_key
    covers_tests: [test_api_cross_tenant::test_task_create]
  - path: /v1/projects/{project_id}/audit-events
    method: GET
    auth: project_api_key
    covers_tests: [test_api_cross_tenant::test_audit_list]
  - path: /v1/admin/audit-events
    method: GET
    auth: admin_jwt
    covers_tests: [test_api_cross_tenant::test_admin_audit_list]
  # ... one per endpoint

tables:
  - name: tasks
    project_column: project_id
    repository: coder_core.repositories.tasks.TasksRepository
    covers_tests: [test_row_visibility::test_tasks_isolated]
  # ... one per table

tokens:
  - name: project_api_key
    issuer: POST /v1/projects
    expected_claims: [project_id]
    covers_tests: [test_token_type_mismatch::test_api_key_vs_impersonation]
  # ... one per type

worker_paths:
  - name: knowledge_read_architect
    worker: architect
    action: read_knowledge_artifact
    covers_tests: [test_worker_paths::test_architect_reads_only_own_project]

gcp_surfaces:
  - name: project_anthropic_key
    resource_template: coder-{project}-{role}-anthropic-api-key
    covers_tests: [test_gcp_iam::test_cross_project_anthropic_key_denied]
```

Hand-maintained. Edits to this file are part of any PR that adds an
endpoint/table/token/worker path. The drift check (Part 3) ensures the
suite fails if the file drifts from the FastAPI router.

### 3. The drift check: `scripts/check_isolation_manifest.py`

Runs in CI on every PR. Enumerates the FastAPI app:

```python
def enumerate_project_scoped_endpoints(app: FastAPI) -> list[EndpointSig]:
    """
    Walk app.routes; for each APIRoute whose dependencies include
    require_project_auth or require_admin_jwt, emit an EndpointSig.
    """
```

Compares to the `endpoints:` section of the manifest; any endpoint
present in the router but absent from the manifest fails the build with:

```
isolation-manifest: new endpoint not covered by isolation suite:
  POST /v1/projects/{project_id}/foo (coder_core/app/routers/foo.py:42)
Add to tests/isolation/isolation_manifest.yaml with at least one
covers_tests entry, or justify exclusion with explicit skip: true.
```

Runtime < 2s. Runs in a separate CI job so the failure is obvious.

### 4. The API cross-tenant matrix: `test_api_cross_tenant.py`

Parametric over `(endpoint_sig, caller_project, target_project)`:

```python
@pytest.mark.parametrize("endpoint", MANIFEST.project_scoped_endpoints())
@pytest.mark.parametrize("caller_is_target", [True, False])
def test_project_scoped_endpoint(
    endpoint: EndpointSig,
    caller_is_target: bool,
    isolation_projects: tuple[IsolationProject, IsolationProject],
    app_client: TestClient,
) -> None:
    a, b = isolation_projects
    caller = a
    target = a if caller_is_target else b
    url = endpoint.path.format(project_id=target.project_id, **endpoint.sample_path_vars)
    resp = app_client.request(
        endpoint.method,
        url,
        headers={"Authorization": f"Bearer {caller.api_key}"},
        json=endpoint.sample_body,
    )
    if caller_is_target:
        assert resp.status_code < 400
    else:
        assert resp.status_code in {401, 403}, f"leak: {endpoint} → {resp.status_code}"
        # explicitly assert NOT 404: a 404 would disclose resource existence
        # (see multi-tenancy contract). We want 403 for wrong-tenant tokens.
        assert resp.status_code != 404, (
            f"{endpoint} returned 404 for cross-tenant read; "
            "should be 403 per multi-tenancy spec"
        )
```

`sample_path_vars` and `sample_body` come from the manifest entry
(e.g. `seed_task_id` for endpoints that take a `{task_id}`).

### 5. Token-type mismatch: `test_token_type_mismatch.py`

For each endpoint, iterate 4 token types × expected-type. Asserts
401/403 for mismatches and that no audit row is written beyond the
authz-rejection marker:

```python
@pytest.mark.parametrize("endpoint", MANIFEST.project_scoped_endpoints())
@pytest.mark.parametrize("token_type", ["project_api_key", "impersonation_jwt", "role_sa_token", "admin_jwt"])
def test_token_type_accepted(endpoint, token_type, isolation_projects, app_client, db_session):
    # ... as above, asserting:
    # - if token_type == endpoint.auth: 2xx
    # - else: 401/403 AND no side-effect audit row
    events_before = db_session.query(AuditEventRow).filter_by(project_id=a.project_id).count()
    resp = app_client.request(...)
    events_after = db_session.query(AuditEventRow).filter_by(project_id=a.project_id).count()
    if token_type != endpoint.auth:
        assert events_after == events_before, (
            f"{endpoint} wrote an audit row under wrong-token rejection"
        )
```

### 6. Direct-DB row visibility: `test_row_visibility.py`

For every manifest `tables:` entry, instantiate the repository with
project A's scope and assert it doesn't return project B's rows:

```python
@pytest.mark.parametrize("table", MANIFEST.tables())
def test_row_scoped_to_project(table, isolation_projects, db_session):
    a, b = isolation_projects
    repo_cls = import_class(table.repository)
    repo_a = repo_cls(db_session, project_id=a.project_id)
    results = repo_a.list()
    assert all(r.project_id == a.project_id for r in results), (
        f"{table.name}: repo scoped to {a.project_id} returned row "
        f"for other project"
    )
    # Additionally, ensure zero-rows query with a B-only filter returns empty
    b_only = repo_a.find_by(id=b.seed_row_id(table))
    assert b_only is None, f"{table.name}: repo scoped to A found B's row"
```

Uses `SAVEPOINT` around each test so session-scope fixtures aren't
dirtied.

### 7. Worker-path tests: `test_worker_paths.py`

Mounts a worker role (architect, developer, etc.) using project A's
impersonation token and drives it through a synthetic task. Asserts:

- knowledge reads return only A's artifacts,
- knowledge writes land in A's repo (mocked `GitHubClient` records
  target repo),
- `record_audit_event` calls are stamped with A's `project_id`,
- an attempt to post a `task_messages` row with B's `task_id` (via
  `TaskMessagesRepository`) raises `CrossTenantWriteError` or a 404
  from the repo layer.

### 8. GCP IAM tests: `test_gcp_iam.py`

```python
@pytest.mark.gcp
@pytest.mark.parametrize("surface", MANIFEST.gcp_surfaces())
def test_cross_project_secret_read_denied(surface, gcp_test_creds):
    a, b = surface.project_pair
    client = secretmanager.SecretManagerServiceClient(credentials=gcp_test_creds[a])
    b_resource = surface.resource_for(b)
    with pytest.raises(PermissionDenied) as exc:
        client.access_secret_version(name=f"{b_resource}/versions/latest")
    assert exc.value.code == 403
```

Skipped locally (`@pytest.mark.gcp` + a CI-only env var). Runs in
CI-staging where two test GCP projects exist.

### 9. The coverage report: `coverage_report.py`

After pytest run, emits `isolation_coverage.json` listing:

```json
{
  "endpoints": {
    "POST /v1/projects/{project_id}/tasks": {
      "covered_by": ["test_api_cross_tenant::test_task_create"],
      "status": "green"
    },
    ...
  },
  "tables": {...},
  "tokens": {...},
  "gcp_surfaces": {...},
  "generated_at": "2026-04-19T…",
  "suite_runtime_seconds": 241,
  "days_since_last_red": 12
}
```

Uploaded as a CI artifact; nightly runs push to a GCS bucket that the
admin `/admin/isolation` page reads.

### 10. Admin surface: `/admin/isolation`

Thin React page in `coder-admin/src/admin/isolation/IsolationTab.tsx`:

- Trust badge: "green for N days" / "RED — last green N days ago."
- Coverage table: endpoint × latest status, sortable.
- Latest coverage JSON link.
- Behind `VITE_ISOLATION_VIEW_ENABLED` (default on after first ship).

No new backend endpoint; page fetches the JSON directly from GCS via
a signed URL minted by an existing admin endpoint (follows the same
pattern as the regression-events artifact view from 0032).

### 11. CI wiring

New job `isolation-suite` in the existing GitHub Actions workflow:

```yaml
isolation-suite:
  runs-on: ubuntu-latest
  services:
    postgres: { image: postgres:16 }
  steps:
    - uses: actions/checkout@v4
    - run: python scripts/check_isolation_manifest.py
    - run: pytest tests/isolation/ -m "not gcp" --junit-xml=isolation.xml
    - if: always()
      uses: actions/upload-artifact@v4
      with: { name: isolation-coverage, path: isolation_coverage.json }
```

A separate `isolation-suite-gcp` job runs on `schedule:` nightly on
`staging` branch with GCP creds from secrets, emitting to Slack on
red.

Blocking behaviour: the `isolation-suite` job uses
`continue-on-error: ${{ vars.CI_ISOLATION_SUITE_BLOCKING != 'true' }}`
until the flag flips (per AC10).

## Data flow

### Scenario A — PR adds a new project-scoped endpoint

1. Dev adds `POST /v1/projects/{project_id}/frobnicate`.
2. `check_isolation_manifest.py` in CI job `isolation-suite` compares
   the FastAPI router to `isolation_manifest.yaml`; `frobnicate` is
   missing from the manifest.
3. CI fails with a message naming the endpoint file + line, telling
   the dev to add a manifest entry with `covers_tests`.
4. Dev adds:
   ```yaml
   - path: /v1/projects/{project_id}/frobnicate
     method: POST
     auth: project_api_key
     sample_body: {"target": "{seed_task_id}"}
     covers_tests: [test_api_cross_tenant::test_project_scoped_endpoint]
   ```
   The parametric `test_project_scoped_endpoint` will now cover the
   new endpoint automatically because the matrix reads the manifest.
5. PR goes green; merge.

### Scenario B — PR accidentally drops a `project_id` filter

1. Dev refactors `TasksRepository.list()` and accidentally removes
   the `.filter(project_id=…)` clause.
2. `test_row_visibility::test_tasks_isolated` runs on PR; the
   repository now returns rows from both A and B; the assertion
   `all(r.project_id == a.project_id for r in results)` fails.
3. CI red within ~5 minutes of push. Dev notices before merge.

### Scenario C — Nightly staging run catches a drifted IAM binding

1. A Terraform change broadens the `secretAccessor` binding on
   `coder-project-b-architect-anthropic-api-key` to include project
   A's architect SA (accidental).
2. Nightly `isolation-suite-gcp` runs;
   `test_cross_project_secret_read_denied` no longer gets
   `PermissionDenied` — the read succeeds.
3. Suite reports red; Slack posts to the regression-alerts channel
   with test ID + surface name.
4. Oncall reverts the Terraform change; next nightly goes green;
   `/admin/isolation` badge flips back.

## Invariants

1. **Every project-scoped endpoint in the FastAPI app is listed in
   the manifest.** Enforced by the drift check.
2. **Every `project_id`-bearing table is listed under `tables:`.**
   Enforced by a secondary drift check (grep for `project_id` columns
   in SQLAlchemy models vs manifest — see open questions for impl).
3. **The fixture's teardown verifies zero residual rows.** A test
   that forgets to roll back fails loudly at session end, not
   silently leaks rows into the next run.
4. **No test may assert a specific error message string.** Status
   codes and audit-row counts only — message strings are allowed to
   evolve. Enforced by code review.

## Interfaces

### New files

- `coder-core/tests/isolation/conftest.py`
- `coder-core/tests/isolation/isolation_manifest.yaml`
- `coder-core/tests/isolation/test_api_cross_tenant.py`
- `coder-core/tests/isolation/test_token_type_mismatch.py`
- `coder-core/tests/isolation/test_row_visibility.py`
- `coder-core/tests/isolation/test_worker_paths.py`
- `coder-core/tests/isolation/test_gcp_iam.py`
- `coder-core/tests/isolation/coverage_report.py`
- `coder-core/scripts/check_isolation_manifest.py`
- `coder-admin/src/admin/isolation/IsolationTab.tsx`

### Modified files

- `.github/workflows/ci.yml` — two new jobs (`isolation-suite`,
  `isolation-suite-gcp`).
- `coder-admin/src/routes.tsx` — add `/admin/isolation` behind
  `VITE_ISOLATION_VIEW_ENABLED`.
- `coder-core/pyproject.toml` — register the new pytest marker `gcp`.
- `coder-core/infra/terraform/ci.tf` — provision the two
  CI-staging projects used by the GCP job (`isolation-ci-a`,
  `isolation-ci-b`) plus their per-role SAs.

### Environment flags

- `CI_ISOLATION_SUITE_BLOCKING` (repo variable) — default `false` on
  first deploy; flip to `true` after 7 days of green.
- `VITE_ISOLATION_VIEW_ENABLED` (frontend) — default on after ship.

## Open questions

- **Drift check for tables.** Inspecting SQLAlchemy models at import
  time is fragile (some models live in plugin packages). Leaning
  toward a simpler approach: declare the expected model-module list
  in the manifest (`watched_model_modules: [...]`) and fail if any
  listed module declares a `project_id` column-bearing model that
  isn't in `tables:`. Revisit at implementation time.

- **Archived-project axis.** Spec open question notes this. Suggest
  phase-2: add `caller_project_archived: [False, True]` axis to the
  API matrix for a couple of representative endpoints (list, fetch,
  audit-events).

- **Knowledge-repo GitHub isolation.** Feasible to assert via a
  dedicated test GitHub PAT with scope to only repo A; the test
  attempts `fetch_repo_contents(repo_b)` and asserts 404. Gated on
  `pytest.mark.github` so local dev isn't broken. Phase-2.

- **WebSocket / SSE.** The `/events` SSE stream isn't in the
  manifest. Current thinking: add a `streams:` section with the
  same drift-check shape, assert subscription to project B from
  project A's token is rejected. Phase-2.

- **Flakiness quarantine.** If a test flakes > 1% in 7 days, does it
  get marked `xfail` automatically, or does it remain blocking until
  a human reviews? Leaning manual review — flakiness in _isolation_
  tests is exactly the kind of thing that shouldn't be auto-hidden.

## Rollout

### Stage 1 — land the manifest + drift check + API matrix (week 1)

Ship the manifest, drift check, API cross-tenant matrix, token-type
mismatch tests. Run in non-blocking mode (`continue-on-error: true`).
Verify zero false positives on a week of PRs. Populate the manifest
for every existing endpoint before flipping blocking.

### Stage 2 — row-visibility + worker-path (week 2)

Add the repository-layer tests and the worker-path tests. Still
non-blocking.

### Stage 3 — GCP IAM + admin surface (week 3)

Provision the two CI-staging projects, wire the nightly
`isolation-suite-gcp` job, and ship the `/admin/isolation` page.

### Stage 4 — flip blocking (week 4+)

After 7 consecutive days of green on staging nightly _and_ zero
false positives on PR non-blocking runs, flip
`CI_ISOLATION_SUITE_BLOCKING=true`. Announce in #eng-deploys.

## Backout plan

- If the PR-blocking suite starts false-positiving, flip
  `CI_ISOLATION_SUITE_BLOCKING=false` — tests still run and report
  but do not block merges.
- If the nightly GCP job starts false-positiving, revert the
  Slack-posting step first (suite keeps running, just quiet) before
  touching the test logic.
- The manifest + suite can be deleted wholesale without rolling back
  any `coder-core` application change; it's additive.
