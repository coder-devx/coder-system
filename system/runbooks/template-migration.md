---
id: template-migration
title: Template schema migration — authoring, rollout, and rollback
type: runbook
status: active
owner: ro
created: 2026-05-05
updated: 2026-05-05
last_verified_at: 2026-05-05
applies_to_services: [coder-core]
applies_to_integrations: [github, gcp]
---

# Template schema migration — authoring, rollout, and rollback

## When to run this

When you need to evolve the `coder-system/template/` schema — adding a field,
renaming a key, removing a deprecated key, restructuring a folder — and roll
the change across every managed project's knowledge repo as a reviewed PR.

## Who can run this

System Admin or Release Manager with write access to `coder-system` and admin
access to `coder-core`.

---

## 1. Authoring a migration

### Python vs YAML — decision tree

```
Is the migration a uniform transformation (add/rename/remove a key, move a folder)
with no conditional logic?
  └─ Yes → consider YAML (.yaml) — shorter, readable, interpreter-verified
  └─ No  → use Python (.py) — required for content inspection, conditionals,
            multi-step mutations, or any logic that needs the file body
```

Use Python whenever: you need to read the file body (not just frontmatter), the
transformation depends on existing field values, or you're combining multiple
change types that interact.

### Steps

1. Determine the next migration NUMBER:

   ```bash
   ls migrations/knowledge/*.py migrations/knowledge/*.yaml | sort | tail -5
   ```

   Take the highest `NUMBER` found and add 1.  The number must be 4-digit
   zero-padded in the filename (`00NN-slug.py`).

2. Copy the appropriate template:

   ```bash
   cp migrations/knowledge/_TEMPLATE.py  migrations/knowledge/00NN-my-slug.py
   # or
   cp migrations/knowledge/_TEMPLATE.yaml migrations/knowledge/00NN-my-slug.yaml
   ```

3. Fill in every required field (`NUMBER`, `SLUG`, `DESCRIPTION`,
   `TARGET_VERSION`).  Set `TARGET_VERSION` to the previous migration's
   `TARGET_VERSION + 1`.

4. **Idempotency requirement.**  Your `migrate()` function (Python) or op list
   (YAML) must be safe to run twice on the same repo.  The standard pattern:
   check whether the target state already exists before writing a change.
   Example (Python):

   ```python
   if "criticality" in fm:
       continue  # already migrated — skip
   ```

5. **Rename migrations: set `VALIDATOR_ALIASES`.**  If your migration renames
   a frontmatter key, you must declare the alias in Python:

   ```python
   VALIDATOR_ALIASES = {"old_key_name": "new_key_name"}
   ```

   The coder-system CI validator reads this dict and enables alias tolerance
   in the knowledge repo validator while any managed project is below
   `TARGET_VERSION`.  The alias window closes automatically when fleet
   adoption reaches 100%.  **Do not ship a rename migration without
   `VALIDATOR_ALIASES`** — the renamed field will break CI on every unrelated
   PR in projects that haven't merged the migration PR yet.

6. Update `coder-system/system/repos.yaml` — bump `template_version` to your
   `TARGET_VERSION` manually (coder-system self-applies migrations by hand per
   spec non-goal).

---

## 2. Local testing

Before opening a PR, run the migration locally against the fixture repos to
catch logic errors without touching any real project data.

### Against the minimal fixture (no-op path)

```bash
coder migrate test \
  --against migrations/_fixtures/minimal \
  --migration migrations/knowledge/00NN-my-slug.py
```

Expected: `FileChange[]` is empty.  The runner will open a no-op PR bumping
`template_version` only.

### Against the typical fixture (real change path)

```bash
coder migrate test \
  --against migrations/_fixtures/typical \
  --migration migrations/knowledge/00NN-my-slug.py
```

Expected: non-empty `FileChange[]` showing the artifacts that would be
modified.  Review the diff output to confirm correctness.

### Against a live project (dry-run)

To test against real project data without opening any PR:

```bash
curl -X POST https://<CODER_CORE_URL>/v1/_admin/template/migrate \
  -H "Authorization: Bearer $CODER_ADMIN_TOKEN" \
  -d '{"migration_numbers":[NN],"projects":["my-project"],"dry_run":true}'
```

Returns the computed `FileChange[]` per project with no DB writes or PRs
opened.

---

## 3. Rolling out

### Standard rollout sequence

1. **Merge the migration file to `coder-system`.**  CI validates:
   - `NUMBER` is unique and matches the filename.
   - `VALIDATOR_ALIASES` present for rename migrations.
   - No import boundary violations (Python only).

2. **Trigger the runner** (or wait for the weekly Cloud Scheduler tick):

   ```bash
   curl -X POST https://<CODER_CORE_URL>/v1/_admin/template/migrate \
     -H "Authorization: Bearer $CODER_ADMIN_TOKEN" \
     -d '{}'
   ```

   The endpoint dispatches a Cloud Run Job and returns `{run_id, scheduled_jobs: N}`
   immediately.  The runner processes up to 4 projects in parallel (flag:
   `--max-parallel-projects`).

3. **Monitor the fleet matrix:**

   ```
   GET /v1/_admin/template/migrations?migration_number=NN
   # or view via Admin UI: /admin/template-migrations
   ```

   Within ~10 minutes, expect one PR per managed project with status `pr_open`.

4. **Review and merge PRs.**  Each PR is titled `template-migration: 00NN-slug`
   and opened against the project's `main` branch.  The project's CI validator
   runs on the PR.  Merge when CI is green.

5. **Callback fires.**  After each PR merge, the `record-template-migration.yml`
   GitHub Actions workflow POSTs to coder-core, flipping the
   `template_migrations` row to `status=merged` and bumping `template_version`
   in the project's `repos.yaml`.

6. **Verify fleet completion:**

   ```
   GET /v1/_admin/template/migrations?migration_number=NN&status=merged
   ```

   When every project shows `merged`, the migration is complete.

### Restricting scope (optional)

To roll out to specific projects only:

```bash
curl -X POST https://<CODER_CORE_URL>/v1/_admin/template/migrate \
  -H "Authorization: Bearer $CODER_ADMIN_TOKEN" \
  -d '{"migration_numbers":[NN],"projects":["project-a","project-b"]}'
```

---

## 4. Handling a failed application

A failed migration appears in the fleet matrix with `status=failed` and an
`error_kind` / `error_detail`.

| error_kind | Meaning | Recovery |
|---|---|---|
| `migrate_raised` | `migrate()` raised an exception | Fix the logic, ship a **new higher-numbered** migration |
| `parse_error` | A project artifact has malformed YAML frontmatter | Operator fixes the corrupt artifact in the project repo (direct PR), then re-triggers the migration |
| `github_upstream` | GitHub API returned 5xx after retry | Re-trigger the runner; usually transient |
| `suspicious_noop` | Every project returned `[]` but `EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT=True` | Check `AFFECTS` patterns in the migration file; fix and ship a new migration |
| `batch_required` | Change set > 50 files but `ALLOW_BATCHING=False` | Set `ALLOW_BATCHING = True` in the migration file and ship a corrected version |
| `forbidden_path` | Migration tried to move a protected path (`active/`, `wip/`, `deprecated/`) | Use Python with explicit `FileChange` objects instead of `MoveFile` for these paths |

**Check `error_detail` in the admin UI** (`/admin/template-migrations` → click
the failed row) for the full traceback.

**Do not edit an existing migration file to fix a failed migration.**  The
runner skips any `(project, migration_number)` pair with `status=failed` or
`status=abandoned`.  Ship a **new migration with a higher number** that
corrects the error.

---

## 5. Rollback

### Close a single open PR (per-project)

1. Close the migration PR in the project repo manually.
2. Mark the row abandoned:

   ```bash
   curl -X PATCH \
     "https://<CODER_CORE_URL>/v1/_admin/template/migrations/<project_id>/NN/1/abandon" \
     -H "Authorization: Bearer $CODER_ADMIN_TOKEN"
   ```

   The project remains at its pre-migration `template_version`.  The runner
   will not re-open a PR for an `abandoned` row.  A new (higher-numbered)
   migration is required to retry.

### Revert a migration before any PR is opened

If you catch the error before the runner dispatches any PRs:

1. Revert the migration file commit on `coder-system`.
2. Set any `status=pending` rows to `abandoned` via the admin endpoint above.
3. The runner will no longer see the migration as pending.

### Undo a migration after PRs have merged (paired-reversal)

Once any project has merged the migration PR, the only safe path is a
**paired-reversal migration** — a new, higher-numbered migration that undoes
the effects of the bad one:

1. Write a new migration `00MM-revert-NN-slug.py` (MM > NN) that inverts the
   change (rename back, remove the added field, etc.).
2. Merge to `coder-system` and roll out normally (steps in §3 above).

The original migration rows remain in `template_migrations` as historical
record.  Do not manually alter merged rows.

### Fleet kill switch

To halt all migration runner activity immediately:

```bash
# On coder-core Cloud Run service:
CODER_TEMPLATE_MIGRATIONS_ENABLED=false
```

`POST /v1/_admin/template/migrate` will return `423 Locked` until the flag is
re-enabled.  Existing open PRs are unaffected.

---

## Success condition

All managed projects show `status=merged` for the migration number in the
fleet matrix at `/admin/template-migrations`.

## If something goes wrong

- **PR sits open for > 30 days:** Close the PR, mark the row `abandoned` via
  the admin endpoint, issue a new migration number.
- **CI fails on the migration PR:** The migration likely introduced a
  cross-link or validation error.  Check whether `VALIDATOR_ALIASES` is
  missing for a rename.  Fix in a new migration number.
- **Alias window should close:** Once fleet adoption is 100%, file a
  `coder-system` PR to set `retired_at` in
  `system/migrations/validator-aliases.yaml` for the relevant alias entry.
