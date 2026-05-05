---
id: template-migration
title: Template schema migration — author, test, roll out, and recover
type: runbook
status: active
owner: ro
created: 2026-05-05
updated: 2026-05-05
last_verified_at: 2026-05-05
applies_to_services: [coder-core]
applies_to_integrations: [github]
---

# Template schema migration — author, test, roll out, and recover

## When to run this

When you need to evolve the `coder-system/template/` schema — adding a new
frontmatter field, renaming an existing field, removing a deprecated field, or
restructuring artifact folders — and roll that change across every managed
project's knowledge repo.

## Who can run this

- Schema authors (any `ro` team member) for authoring and local testing.
- Operators (`ro`) for triggering the fleet run and monitoring progress.

---

## 1. Authoring a migration

### Python vs YAML decision tree

```
Does the migration need per-artifact value inspection or conditional logic?
├── Yes → use a .py migration (full Python, KnowledgeRepoView, FileChange API)
└── No  → can it be expressed as one of the five declarative operations?
          ├── Yes → use a .yaml migration (simpler, less error-prone)
          └── No  → use .py
```

The five declarative YAML operations are:
- `rename_frontmatter_key` — rename a key in matching artifacts
- `add_frontmatter_key_with_default` — add a key absent from matching artifacts
- `remove_frontmatter_key` — remove a key from matching artifacts
- `move_folder` — relocate a folder and update registry.yaml entries
- `rename_folder` — rename a folder's leaf name

Use `migrations/knowledge/_TEMPLATE.py` or `migrations/knowledge/_TEMPLATE.yaml`
as your starting point.  Both templates contain annotated comments explaining
every field.

### Picking a migration number

```sh
ls migrations/knowledge/ | grep -oP '^\d+' | sort -n | tail -1
```

Take the next integer.  Numbers are shared across `.py` and `.yaml` files;
never reuse a retired number.

### Idempotency requirement

Your `migrate()` function (or the YAML interpreter) will be called once per
project, but may be called again on a retry.  The runner's idempotency key is
the `template_migrations` DB row, but your migration logic must also be safe
to run twice.  Typical guard:

```python
if "new_field" in artifact.frontmatter:
    continue  # already applied
```

### `VALIDATOR_ALIASES` for rename migrations

Any migration that renames a frontmatter key **must** declare:

```python
VALIDATOR_ALIASES = {"old_key": "new_key"}
```

(or the YAML `validator_aliases:` equivalent).

The CI validator on `coder-system` reads this dict from every migration file
and writes entries into `system/migrations/validator-aliases.yaml`.  While an
alias's `retired_at` is null, the validator accepts both names in frontmatter
and cross-link lookups.  The alias window closes automatically once fleet
adoption reaches 100% — the runner sets `retired_at` via a `coder-system` PR
at that point, not on a fixed calendar date (ADR 0019).

Omit `VALIDATOR_ALIASES` for purely additive (`add_frontmatter_key_with_default`)
or removal (`remove_frontmatter_key`) migrations.

---

## 2. Local testing

```sh
# Test against the typical fixture (has one service + one wip design):
coder migrate test \
  --against migrations/_fixtures/typical \
  --migration migrations/knowledge/00NN-your-slug.py

# Test against the minimal fixture (bare repo, no artifacts — exercises no-op path):
coder migrate test \
  --against migrations/_fixtures/minimal \
  --migration migrations/knowledge/00NN-your-slug.py
```

Both commands run entirely in-process — no network, no GitHub, no DB.  Output
is the `FileChange[]` list the runner would produce for that fixture repo, with
a diff view per changed file.

### What to verify locally

1. `FileChange` output matches your intent.
2. Running the command twice produces identical output (idempotency).
3. On the minimal fixture the command returns an empty list (or a one-line
   repos.yaml bump only) — no fixture artifacts means no field edits.
4. For rename migrations, confirm `VALIDATOR_ALIASES` is declared and the
   old key no longer appears in fixture output after migration.

---

## 3. Rolling out

### Step 1 — merge the migration file to `coder-system`

Open a PR to `coder-system` that adds your migration file to
`migrations/knowledge/`.  CI validates:
- `NUMBER` is unique across all migration files.
- `VALIDATOR_ALIASES` (if present) are extractable and written to
  `system/migrations/validator-aliases.yaml`.
- The file parses without import errors.

After merge, the runner can see the new migration.

### Step 2 — trigger the fleet run

```sh
# Trigger via admin API (operator only):
curl -X POST https://<CODER_CORE_URL>/v1/_admin/template/migrate \
  -H "Authorization: Bearer $CODER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
# Returns immediately: {"run_id": "...", "scheduled_jobs": N}
```

Or wait for the weekly Cloud Scheduler tick (fires automatically, no action
needed).

Optional filters:
```json
{
  "migration_numbers": [3],        // restrict to specific migration(s)
  "projects": ["my-project"],      // restrict to specific project slug(s)
  "dry_run": true                  // compute FileChange[] without opening PRs
}
```

### Step 3 — monitor `/admin/template-migrations`

Open the admin SPA → Template Migrations.  Expect:

- Rows flip from `pending` → `pr_open` within ~10 minutes of the run starting.
- PRs appear in each managed project's knowledge repo titled
  `template-migration: 00NN-<slug>`.
- After each project team merges the PR, the `record-template-migration`
  GitHub Action fires and the row flips to `merged`.

The fleet matrix shows per-project status.  All rows `merged` = rollout
complete.

### Step 4 — check Prometheus metrics

| Metric | What to watch |
|---|---|
| `template_migration_run_total{outcome="failed"}` | Should stay at 0 |
| `template_migration_pr_open_age_seconds` | Should decline as PRs merge |
| `template_migration_pending_count` | Should reach 0 across all projects |

---

## 4. Handling a failed application

A row with `status='failed'` means the migration crashed or hit a guard
for that project.  Check `error_detail` in the admin UI (or via
`GET /v1/_admin/template/migrations?status=failed`).

| `error_kind` | Cause | Fix |
|---|---|---|
| `migrate_raised` | `migrate()` threw an exception | Fix the migration logic; ship a new higher-numbered migration |
| `parse_error` | Artifact frontmatter was malformed | Fix the corrupt artifact in the project repo; re-trigger the same migration number |
| `github_upstream` | GitHub API 5xx after retry | Re-trigger; transient — no logic change needed |
| `forbidden_path` | Migration tried to move `active/`, `wip/`, or `deprecated/` | Fix `MoveFile` / `rename_folder` paths in the migration |
| `batch_required` | Result exceeded 50 files and `ALLOW_BATCHING=False` | Set `ALLOW_BATCHING = True` or split into multiple migrations |
| `suspicious_noop` | All projects returned empty `FileChange[]` despite `EXPECTED_NONEMPTY_AT_LEAST_ONE_PROJECT=True` | Investigate why the migration matched nothing; fix the path glob or field check |

**Failed rows are terminal** — the runner will not re-attempt a `failed` or
`abandoned` row.  The only path forward is a new migration with a higher number
that corrects the logic.

---

## 5. Rollback

### Close a single in-flight PR (per-project rollback)

1. Close the open migration PR in the project's knowledge repo.
2. Mark the row abandoned:

```sh
curl -X PATCH \
  "https://<CODER_CORE_URL>/v1/_admin/template/migrations/<project_id>/<number>/<batch>/abandon" \
  -H "Authorization: Bearer $CODER_ADMIN_TOKEN"
```

The project stays at its pre-migration `template_version`.  The runner will not
re-open a PR for this migration on this project.  To retry, ship a new
migration with a higher number.

### Revert before any PR is opened (migration not yet running)

Revert the migration file commit on `coder-system`.  The runner will no longer
see the migration as pending.  Any rows already in `status='pending'` should
be manually set to `abandoned` via the abandon endpoint.

### Paired-reversal migration (post-merge fix)

Once any project has merged a migration PR, the only safe path is a new
migration with a higher number that undoes the effects:

```python
# Example reversal: remove a field that 0003 added
NUMBER = 4
SLUG = "revert-add-criticality"
DESCRIPTION = "Revert migration 0003: remove the criticality field added in error."
TARGET_VERSION = 4

def migrate(repo):
    changes = []
    for artifact in repo.artifacts("system/services/*.md"):
        if "criticality" not in artifact.frontmatter:
            continue
        # Remove the line from the raw content
        new_content = "\n".join(
            line for line in artifact.content.splitlines()
            if not line.startswith("criticality:")
        ) + "\n"
        changes.append(FileChange(path=artifact.path, content=new_content))
    return changes
```

The reversal migration creates rows under its own number and appears in the
fleet matrix as a standard migration.

### Fleet kill switch

Set `CODER_TEMPLATE_MIGRATIONS_ENABLED=false` on coder-core to stop the runner
from processing any migrations.  The admin POST endpoint returns `423 Locked`
while the flag is off.  Open PRs are unaffected.

## Success condition

- All rows in `template_migrations` for the target migration number show
  `status='merged'`.
- `template_migration_pending_count` gauge is 0 across all projects.
- No `status='failed'` rows remain unacknowledged.

## If something goes wrong

- `error_kind=parse_error` in a project → fix the corrupt artifact in that
  project's repo; re-trigger the same migration number via the admin API.
- `error_kind=github_upstream` repeatedly → check GitHub status page; re-trigger
  when GitHub recovers.
- Migration PR sitting in `pr_open` for > 30 days → close PR, call the abandon
  endpoint, issue a new higher-numbered migration to retry.
- `record-template-migration.yml` Action not firing → confirm the workflow is
  synced to the project's repo (`coder managed-workflows sync`); check Actions
  permissions on the repo.
