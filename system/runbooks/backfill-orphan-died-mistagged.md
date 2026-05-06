---
id: backfill-orphan-died-mistagged
title: Backfill historical mis-tagged orphan_died rows
type: runbook
status: active
owner: ro
created: 2026-05-06
updated: 2026-05-06
last_verified_at: 2026-05-06
applies_to_services: [coder-core]
applies_to_integrations: [cloud-sql]
---

# Backfill historical mis-tagged orphan_died rows

## When to run this

One-shot cleanup after [coder-core#157](https://github.com/coder-devx/coder-core/pull/157)
ships. Up to ~24h of `tasks` rows pre-merge will have:

- `status = 'succeeded'`
- `failure_kind = 'orchestrator_died'`
- `failure_detail` containing `"remediated_by": "self_heal.zombie_executing"`
- A populated `pr_url` and full `result` body

These are successful tasks mis-tagged by the zombie reaper's TOCTOU
race (detect cached `running`, worker writeback committed `succeeded`,
ORM UPDATE without a status WHERE clobbered `failure_kind` onto an
already-succeeded row). The work itself is fine — only the metadata
is wrong. Dashboards that aggregate by `failure_kind` will keep
mis-reporting orphan-deaths until backfilled.

## Who can run this

Operator with Cloud SQL IAM access to the `coder-core-sa` service
account (or anyone whose principal has been granted `UPDATE` on the
`tasks` table directly — the SA is the table owner).

## Prerequisites

- `gcloud` authenticated: `gcloud auth login` AND
  `gcloud auth application-default login` (per the
  [ADC ≠ gcloud login](#adc-vs-gcloud-login) note in memory).
- `cloud-sql-proxy` on PATH.
- `psql` on PATH.

## Procedure

### 1. Start the proxy as the runtime service account

```bash
gcloud config set auth/impersonate_service_account \
  coder-core-sa@vibedevx.iam.gserviceaccount.com

cloud-sql-proxy --port 5432 vibedevx:europe-west1:coder-core-db &
PROXY_PID=$!
```

If you can't impersonate the SA, see [the alternative path below](#alt-direct-connection)
that uses a token explicitly.

### 2. Inspect what would be touched (read-only)

```bash
PGPASSWORD="$(gcloud auth print-access-token \
  --impersonate-service-account=coder-core-sa@vibedevx.iam.gserviceaccount.com)" \
  psql -h 127.0.0.1 -p 5432 -U coder-core-sa@vibedevx.iam -d coder_core <<'SQL'

SELECT count(*) AS to_backfill,
       count(*) FILTER (WHERE pr_url IS NOT NULL) AS with_pr,
       min(created_at) AS earliest,
       max(created_at) AS latest
  FROM tasks
 WHERE status = 'succeeded'
   AND failure_kind = 'orchestrator_died';
SQL
```

Sanity checks before applying:

- `to_backfill` should be small (≤ ~20 rows from the 24h pre-merge
  window; growing past that means the reaper fix hasn't deployed yet
  or a different bug is producing the same shape).
- `with_pr` should equal `to_backfill` — every row in this bucket
  shipped a PR. If any row has no PR, investigate before proceeding;
  it may indicate a different failure mode that legitimately deserves
  the orphan_died tag.
- `earliest` / `latest` bracket the affected window.

### 3. Apply the backfill

```bash
PGPASSWORD="$(gcloud auth print-access-token \
  --impersonate-service-account=coder-core-sa@vibedevx.iam.gserviceaccount.com)" \
  psql -h 127.0.0.1 -p 5432 -U coder-core-sa@vibedevx.iam -d coder_core <<'SQL'

BEGIN;

-- Defensive: only touch rows the reaper-mistag pattern produced.
-- Filtering on the failure_detail JSON marker stops the UPDATE from
-- accidentally clearing fields on a row that legitimately died and
-- was later re-dispatched to success (a different code path).
UPDATE tasks
   SET failure_kind = NULL,
       failure_detail = NULL
 WHERE status = 'succeeded'
   AND failure_kind = 'orchestrator_died'
   AND failure_detail::text LIKE '%self_heal.zombie_executing%';

-- Spot-check: should match to_backfill from step 2.
SELECT count(*) AS rows_updated FROM tasks
 WHERE status = 'succeeded'
   AND failure_kind IS NULL
   AND xmax::text != '0';  -- modified in this txn

COMMIT;
SQL
```

If the COMMIT prints anything other than the expected count, ROLLBACK
and investigate before retrying.

### 4. Verify dashboards re-render

- Admin panel `/projects/<p>/dashboard` — orphan-death rate widget
  should drop to its true value (~0% for reviewer, ~4% for dev).
- Any `failure_kind` aggregation in the audit-log view should reflect
  the new counts.

### 5. Tear down

```bash
kill $PROXY_PID
gcloud config unset auth/impersonate_service_account
```

## Alt: direct connection (no impersonation)

If `iam.serviceAccountTokenCreator` isn't granted to your principal,
either:

- Have an admin run the SQL block in step 3 from a Cloud Shell with
  the SA already attached, **or**
- Get `UPDATE` granted directly on the `tasks` table:

```bash
gcloud sql users grant ... # platform team
```

The SQL itself is the same; just adjust `-U` and `PGPASSWORD`.

## Why this is one-shot

The fix in coder-core#157 makes the reaper's UPDATE atomic — once
deployed, no new mis-tagged rows are produced. Re-running this
runbook on a future date should match zero rows.

## Related

- [Cloud SQL bootstrap](./cloud-sql-bootstrap.md) — proxy + IAM auth
  setup.
- [Zombie task recovery](./zombie-task-recovery.md) — the
  operator-facing companion when a zombie row needs manual handling
  (different problem, post-fix still relevant).
- coder-core#157 — the underlying bug fix.
- Spec [0056](../product-specs/wip/0056-worker-dispatch-durability.md)
  §"2026-05-05 — Phase 2 IS working" — the analysis that surfaced this
  cleanup item.
