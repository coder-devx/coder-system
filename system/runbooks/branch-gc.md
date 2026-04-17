---
id: branch-gc
title: Branch cleanup GC — operate, dry-run, force-delete
type: runbook
status: active
owner: ro
created: 2026-04-15
updated: 2026-04-15
last_verified_at: 2026-04-15
applies_to_services: [coder-core]
applies_to_integrations: [github]
---

# Branch cleanup GC

Operational guide for the ``task/*`` branch cleanup GC in
``coder-core`` (component: [branch-cleanup](../product-specs/active/branch-cleanup.md)).
Cloud Scheduler invokes ``POST /v1/_admin/gc/branches`` hourly; this
runbook covers the operator-facing actions around it.

## When to run this

- You see ``task/*`` branches piling up on a managed project's repo.
- Someone reports a branch was deleted that shouldn't have been (open
  PR, non-``task/*`` name).
- You need to freeze GC activity during an incident.
- You need a one-off delete of a specific stale branch.

## Who can run this

Operator — humans in the admin panel, or automation using an admin JWT.
The endpoints are gated behind ``decode_admin_jwt`` (same signing key
and audience as ``/v1/admin/*``).

## Prerequisites

- An admin JWT (sign in to the admin panel and copy from devtools, or
  mint one via ``scripts/mint-admin-jwt.py`` with
  ``CODER_BROKER_SIGNING_KEY`` set).
- ``curl`` or the admin panel.
- The project id (e.g. ``coder``, ``vibetrade``).

Store the JWT once:

```bash
export ADMIN_JWT="..."
export CORE="https://coder-core-<hash>-ew.a.run.app"
```

## Steps

### Dry-run for a single project

Show what GC *would* delete without touching GitHub.

```bash
curl -s "$CORE/v1/_admin/gc/branches" \
  -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"project_id": "coder", "dry_run": true}' | jq
```

Response lists per-project ``GcRunSummary`` rows. Inspect the events:

```bash
RUN_ID=$(... | jq -r '.runs[0].run_id')
curl -s "$CORE/v1/_admin/gc/runs/$RUN_ID" \
  -H "Authorization: Bearer $ADMIN_JWT" | jq
```

Each event has ``action`` (``dry_run_delete`` / ``skipped``) and
``reason`` (``age_lt_24h``, ``open_pr``, ``task_not_terminal``, …).

### Disable GC for one project

Set the project's ``gc_enabled`` flag to false. All branches on that
project's repos are then skipped with ``reason=gc_disabled`` on the
next pass.

```sql
-- In the Cloud SQL console, as the admin role:
UPDATE projects SET gc_enabled = false WHERE id = '<project-id>';
```

Re-enable with ``gc_enabled = true``.

### Force-delete a specific branch

When a specific stale branch needs to go *now* (e.g. it's clogging
branch protection review lists) and you've confirmed there's no open
PR, delete it directly via the GitHub CLI — don't race the GC:

```bash
gh api -X DELETE "repos/<org>/<repo>/git/refs/heads/task/<slug>"
```

Then record an audit note (Slack #ops or the project's `ops-log` doc).
The next GC pass will record a ``task_not_found`` skip for the branch
name if any row still references it; that's harmless.

### Check counters over a period

```bash
curl -s "$CORE/v1/_admin/gc/metrics?period=7d" \
  -H "Authorization: Bearer $ADMIN_JWT" | jq
```

Returns ``deleted_total`` / ``errors_total`` / ``skipped_total`` /
``dry_run_deleted_total`` / ``false_delete_total``. Alert if
``false_delete_total > 0`` — see "If something goes wrong" below.

### Inspect recent runs

```bash
curl -s "$CORE/v1/_admin/gc/runs?project_id=coder&limit=20" \
  -H "Authorization: Bearer $ADMIN_JWT" | jq
```

## Success condition

- ``deleted_total`` increases on each hourly run when there are stale
  branches; ``errors_total`` stays at zero.
- No ``task/*`` branch older than 48h persists on any managed repo.
- ``false_delete_total`` is zero across all periods.
- Operators never issue manual ``git push --delete`` commands in a
  given week (the Secondary metric in spec 0023).

## If something goes wrong

- **``errors_total`` climbing**: inspect the run events —
  ``reason=github_error`` rows carry the API response. Common causes:
  installation token expired (look for 401 in the logs), rate limit hit
  (429), network blip. Re-run the hour; persistent failures mean the
  GitHub App installation needs attention.
- **``false_delete_total > 0``**: SEV-2. A deleted branch had an open
  PR or was non-``task/*``. Page the owner, pull the event row for the
  branch (``GET /v1/_admin/gc/runs/{run_id}`` and grep for it), and
  correlate with GitHub's branch creation hook webhook log. The
  eligibility pipeline is fail-closed by design, so a false delete
  points to a bug — do NOT re-enable the schedule until fixed.
- **Something's getting skipped that shouldn't be**: run a dry-run and
  check the ``reason`` on the skip event. ``task_not_terminal`` means
  the task's stage isn't in ``accepted``/``rejected``/``stuck`` —
  verify the task row directly.
- **Schedule fired but nothing happened**: check Cloud Scheduler logs
  and the ``coder-core`` request logs for ``gc_trigger`` entries. The
  admin token the scheduler uses lives in Secret Manager; rotate via
  the standard admin-token rotation procedure.
