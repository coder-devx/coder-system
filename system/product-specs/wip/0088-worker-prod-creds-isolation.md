---
id: '0088'
title: Developer-worker subprocesses must never inherit prod DB credentials
type: spec
status: wip
owner: ro
created: '2026-05-13'
updated: '2026-05-13'
last_verified_at: '2026-05-13'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- developer-worker
- multi-tenancy
- tenant-isolation
parent: tenancy-and-access
---

# Developer-worker subprocesses must never inherit prod DB credentials

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

On 2026-05-12 around 20:35 UTC, the developer worker for task `06141ff8` (a prerequisite of spec 0083) ran `alembic upgrade head` inside its sandbox container as part of its test cycle. The migration the worker had authored (a benign `DROP INDEX` + `CREATE INDEX CONCURRENTLY` on `tasks.original_task_id`) **applied cleanly against the production database**. The worker's PR ([coder-core#249](https://github.com/coder-devx/coder-core/pull/249)) then failed CI on four unrelated flaky tests and sat un-merged. Production was wedged at `alembic_version='0082'` with no script on `main` matching that revision — every subsequent deploy failed at the migrate step. Recovered via [coder-core#251](https://github.com/coder-devx/coder-core/pull/251), but the underlying gap is open.

Root cause: the dev worker runs inside a Cloud Run Job (`coder-core-worker`) provisioned with the `coder-core-sa@vibedevx.iam` service account, and the Job's spec carries `CLOUD_SQL_INSTANCE` / `CLOUD_SQL_USER` / `CLOUD_SQL_DATABASE` env vars pointing at the prod Cloud SQL instance. The worker passes those env vars through to the developer subprocess (claude-code) without modification, so any `alembic` / `psql` / SQLAlchemy connect call inside the subprocess reaches the prod DB with full write access via IAM auth.

This is a Phase B blast-radius issue. Every worker run that exercises a migration — for testing, for verification, or as a side effect of pytest fixtures bootstrapping schema — is one `alembic upgrade head` away from changing prod state, with no PR review and no operator approval. Memory's recovery muscle memory for this case did not previously exist.

## Users / personas

- **Operators relying on PR review as the gate for prod schema changes.** Today's worker harness bypasses the gate entirely; the operator finds out a migration applied only when CI deploy fails ~hours later.
- **The developer worker.** Currently produces work whose migration may already be in prod by the time the PR opens — the PR's CI then runs against a prod whose schema is past the PR's head. Misleading green-vs-red signals follow.
- **Phase B autopilot.** Cannot durably ship without a worker-creds boundary; one rogue migration can wedge the orchestrator for the whole org.

## Goals

- A developer worker subprocess that runs `alembic` / `psql` / direct SQLAlchemy connections **cannot reach the prod DB**. Period. Verified by spying on the subprocess environment at dispatch time.
- The worker can still run migrations as part of its test cycle — against an **ephemeral test DB** that the worker harness provisions per turn (SQLite in-memory for most cases, a postgres test container when the migration uses PG-specific features).
- The change is transparent to the worker's task prompt: the worker keeps invoking the same commands it does today; only the env points elsewhere.
- Operator-side recovery for in-flight rogue migrations stays available via the standard PR + deploy path.

## Non-goals

- Refactoring the Cloud Run Job harness or the worker subprocess shape. The fix is in the env-var construction between parent harness and subprocess, not in the broader process model.
- Replacing IAM auth with password auth. IAM stays; the env vars that select the IAM target are stripped/overridden.
- Restricting non-DB credentials (Anthropic API key, GitHub token, GCS bucket creds). Those have separate scopes and separate audit paths; this spec scopes to DB creds.
- Network-level firewall blocking the prod DB from the worker subprocess. That's a defense-in-depth follow-up worth its own spec; this one closes the env-var leak first.

## Scope

Two surfaces:

1. **Worker subprocess env construction** (`coder-core` `coder_core/workers/_auth_env.py` and its callers — `pm.py`, `developer.py`, `reviewer.py`, `architect.py`). When building the subprocess env, **explicitly remove** `CLOUD_SQL_INSTANCE`, `CLOUD_SQL_USER`, `CLOUD_SQL_DATABASE`, plus any `DATABASE_URL` / `PGHOST` / `PGUSER` / `PGPASSWORD` / `PGDATABASE` keys. Replace with values pointing at the ephemeral test DB the worker harness provisions for this turn.

2. **Ephemeral test DB provisioning** (`coder-core`, new module `coder_core/workers/_test_db.py`). Two strategies:
   - **SQLite in-memory** (default) — the worker constructs `sqlite+aiosqlite:///:memory:` and exposes it via `DATABASE_URL`. The existing migration suite already has `if bind.dialect.name != "postgresql"` guards for PG-only features; the SQLite path no-ops them. Sufficient for the majority of dev tasks that don't exercise PG-specific behaviour.
   - **Postgres test container** (escape hatch) — when the worker's task touches a migration with PG-only features that need real validation (e.g., `CREATE INDEX CONCURRENTLY`, `WITH RECURSIVE`, partial indexes, generated columns), the harness boots a throwaway postgres-15 container with a fresh DB, exposes its connection string via `DATABASE_URL`, tears it down on subprocess exit. Triggered by a marker file in the task's prompt context (`needs_postgres_test_db: true`) — opt-in, not default, to keep most turns fast.

Worker harness logs the env-strip event with task_id + the set of stripped keys for audit. Audit event `worker.prod_creds_stripped` written to the task row's audit trail.

## Acceptance criteria

- **AC1.** Unit test on `_auth_env.py`: given a parent process env that includes `CLOUD_SQL_INSTANCE=vibedevx:europe-west1:coder-core-db`, the worker's subprocess-env construction returns a dict where `CLOUD_SQL_INSTANCE` is absent (or replaced with a test-DB sentinel). Same for the rest of the DB env-var list.
- **AC2.** Integration test (SQLite path): a developer subprocess that runs `alembic upgrade head` succeeds against the ephemeral SQLite DB. The prod DB's `alembic_version` row is unchanged after the subprocess exits.
- **AC3.** Integration test (postgres-container path): with `needs_postgres_test_db: true` in the task prompt, the worker harness boots a postgres-15 container, exposes its DSN, the subprocess runs `alembic upgrade head` against it, and the prod DB stays untouched. Container is torn down on exit (no orphans).
- **AC4.** Regression: replay the 2026-05-12 incident. Construct a synthetic worker task that authors migration `0099_test_marker.py` (creates a single `test_marker` table). Verify the prod DB does not contain that table after the worker turn ends, and the prod DB's `alembic_version` stays at its pre-test value.
- **AC5.** Audit-trail check: every worker turn writes a `worker.prod_creds_stripped` audit event with the task_id and the comma-separated list of stripped env keys. Operator can grep audit-log by action prefix.

## Open questions

- Should the strip list be **deny-list** (strip a known set of DB-related keys) or **allow-list** (start from an empty env and add only safe keys)? Allow-list is safer but more invasive — every existing keys the worker subprocess relies on must be explicitly enumerated. Lean deny-list for v1; revisit if a credential leak slips through.
- For migrations that exercise PG-only features but the operator hasn't tagged `needs_postgres_test_db: true`, the SQLite path silently no-ops the PG branch. The worker won't observe the migration's PG behaviour. Is that acceptable? Probably yes — the operator's PR review is the gate; CI's deploy-step migrate validates against actual prod.
- Cost of the postgres-test-container path: each opt-in turn pays a ~30s container boot. Estimate: <5% of dev turns need it. Acceptable cost vs. preventing the prod-credentials leak.
- Should this spec also cover `coder-core-worker` Cloud Run Job env-spec hardening (e.g., move DB creds to a separate secret that only the parent process can read, not subprocess-inherit)? That's a deeper fix and a separate spec. Keep this one tight.

## Links

- [coder-core#251](https://github.com/coder-devx/coder-core/pull/251) — the immediate-recovery hotfix that unblocked prod after the 2026-05-12 incident.
- [coder-core#249](https://github.com/coder-devx/coder-core/pull/249) — the dev worker PR whose subprocess landed migration 0082 against prod.
- Related operator memory: this session's prod-wedge incident at 2026-05-12 20:35 UTC. The recovery muscle memory: "cherry-pick the migration into a clean PR" path needs no extra credentials. Direct DB write would need postgres password (no Secret Manager entry) or `roles/cloudsql.instanceUser` grant to the operator's IAM user.
- Related spec: `tenant-isolation` (active) — the test harness for cross-tenant separation. This spec extends the isolation boundary to include "prod-DB-from-subprocess" as a categorically blocked path.
- Related spec: `multi-tenancy` (active) — the broader multi-tenancy invariants. Adding "worker subprocess cannot reach prod DB" to the invariant set requires confirming with this spec's design.
