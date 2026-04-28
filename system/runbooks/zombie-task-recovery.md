---
id: zombie-task-recovery
title: Recover from zombied worker dispatches
type: runbook
status: active
owner: ro
created: 2026-04-28
updated: 2026-04-28
last_verified_at: 2026-04-28
applies_to_services: [coder-core]
applies_to_integrations: [cloud-run-self-heal]
---

# Recover from zombied worker dispatches

## When to run this

Use this runbook when one or both of the following are true:

1. A task row has `status='running'` for >45 min with no terminal
   transition, and the operator wants to know what to do.
2. A wave of dispatches went out and several came back as
   `status='timed_out'` with `failure_kind='orchestrator_died'`.

## Who can run this

Operator with admin API token. The fix is observation + a few API
calls, no code changes.

## Prerequisites

- API key for the affected project at `~/.config/coder/projects/<project>.key`
- Cloud Run admin access (to read the self-heal-tick logs if needed)
- `gh` CLI authenticated (to inspect any PRs the worker may have opened
  before it zombied)

## Background

Spec 0042 self-heal v1 detects "zombie" tasks — rows at
`status='running'` whose `started_at` is older than
`zombie_executing_min_minutes` (45 min as of 2026-04-28). The
remediator now CAS-flips the row to `status='timed_out'` with
`failure_kind='orchestrator_died'` (spec 0042 v1.1, coder-core PR #45).
This is **terminal**; the row no longer matches the detect query.

Workers zombie when the Cloud Run service instance hosting the
asyncio `orchestrate_task` is killed before the dispatcher's Phase 3b
DB writeback runs (`dispatcher.py:1604–1654`). Side effects in
GitHub (PR opened, commit pushed) are durable; the task row state is
not. Spec 0056 tracks the architectural fix (move workers to Cloud
Run Jobs).

## Steps

### 1. Identify the zombied tasks

```bash
API_KEY=$(cat ~/.config/coder/projects/coder.key)
PROD="https://coder-core-ql732k45va-ew.a.run.app"

# List recent failed/timed_out tasks
curl -s "$PROD/v1/projects/coder/tasks?limit=30&status=timed_out" \
  -H "X-API-Key: $API_KEY" | jq '.[] | {id, role, started_at, finished_at, failure_kind}'
```

### 2. Check for partial-completion side effects

For each zombied task with role=architect/developer/reviewer, check
whether a PR was opened before the zombie. The PR is durable in
GitHub even if the row state never reflected it.

```bash
TASK_ID=…
curl -s "$PROD/v1/projects/coder/tasks/$TASK_ID" \
  -H "X-API-Key: $API_KEY" | jq '{pr_url, commit_sha, branch_name, role, prompt}'
```

If `pr_url` is set:

- The worker reached the PR-opening step before its parent died.
- The PR may already be merged or merge-ready (check `gh pr view`).
- For developer-direct tasks, this is **complete work**. Merge the
  PR via `gh pr merge` if CI is green; the task row state is
  cosmetic.
- For architect/TM tasks where the schema-validated output failed
  envelope checks (e.g. `frontmatter` as YAML string instead of JSON
  object), check whether the PR's actual files are correct — they
  usually are, despite the envelope failure. Merge manually.

### 3. Decide on retry vs. cancel

For each zombied task, choose:

**Retry** — when the work needs to be redone (no usable PR exists):

```bash
curl -s -X POST "$PROD/v1/projects/coder/tasks/$TASK_ID/override" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "retry"}'
```

**Cancel** — when the work landed durably (PR merged) and the row
state is just cosmetic, OR the task is no longer needed:

```bash
curl -s -X POST "$PROD/v1/projects/coder/tasks/$TASK_ID/override" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"action": "reject"}'
```

Cancellation flips the row to `status='cancelled'`,
`stage='rejected'` — terminal.

**Architect tasks have no pipeline stage**, so `action=retry` is
rejected with HTTP 422 `no_pipeline`. For architects, cancel + re-fire
a fresh dispatch (or accept the PR if one was opened).

### 4. Re-fire fresh dispatches

For tasks that need fresh runs:

```bash
PAYLOAD='{"role": "architect", "repo": "coder-system", "prompt": "<from original dispatch>"}'
curl -s -X POST "$PROD/v1/projects/coder/tasks" \
  -H "X-API-Key: $API_KEY" \
  -H "Content-Type: application/json" \
  -d "$PAYLOAD"
```

The original prompts are usually in `/tmp/coder-dispatch/*.json` files
from the dispatch session.

### 5. Watch the new dispatch

Workers take 5–30 min normally; the zombie reaper fires at 45 min.
Either the worker completes naturally and the row reaches
`succeeded`, or it zombies again and the row reaches `timed_out`. In
both cases the row reaches a clean terminal state.

```bash
watch -n 30 "curl -s '$PROD/v1/projects/coder/tasks/$NEW_TASK_ID' \
  -H 'X-API-Key: $API_KEY' | jq -r '.status + \" \" + (.failure_kind // \"\")'"
```

## Success condition

- All zombied rows have a terminal `status` (`succeeded`, `failed`,
  `timed_out`, or `cancelled`).
- For each, you've decided: keep the side-effect PR, retry, or accept
  the cancellation.
- The 4-task per-project concurrency cap is no longer blocked by
  stuck rows.

## If something goes wrong

### Reaper isn't firing on stuck tasks

Symptoms: `status='running'` for >45 min, no transition.

Check:

1. The `coder-core-self-heal-tick` Cloud Run **Job** has env var
   `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE=apply` (not `dry_run`).
   This was the smoking-gun bug on 2026-04-28 — the JOB had `dry_run`
   while the SERVICE had `apply`, so the reaper detected zombies and
   wrote `dry_run` rows that filled the cap and never mutated.
   ```bash
   gcloud run jobs describe coder-core-self-heal-tick \
     --region=europe-west1 --format=json | jq '.spec.template.spec.template.spec.containers[0].env'
   ```
2. The `zombie_executing_min_minutes` env var is ≥ the worker timeout
   (`coder_developer_task_timeout_seconds` is 2400 = 40 min). The
   threshold should be 45 min or higher; if it's lower, the reaper
   kills live workers prematurely.
3. The Cloud Scheduler `coder-core-self-heal-tick` is running every
   minute (`* * * * *` UTC).
   ```bash
   gcloud scheduler jobs list --location=europe-west1 \
     --filter="name~self-heal"
   ```

### Cap is blocking remediation (older deploys)

Symptoms: reaper logs show `skipped_cap` for the same task IDs
repeatedly.

This was the pre-PR #45 behaviour. Verify the deployed image is
≥ `b47fdf5` (PR #45 merge commit). If older, the remediator is
trying the broken `launch_re_enqueue` path which fails silently in
the Cloud Run Job context.

```bash
gcloud run jobs describe coder-core-self-heal-tick \
  --region=europe-west1 --format='value(spec.template.spec.template.spec.containers[0].image)'
```

### Tasks stuck at `status='queued'`

Symptoms: a task row never transitions from `queued` to `running`
even though concurrency slots are open.

The per-process queue (`_dispatcher_queue.py`) is in-memory. If the
service instance hosting the queue dies, queued tasks lose their
waiters. Workaround:

```bash
curl -X POST "$PROD/v1/projects/coder/tasks/$TASK_ID/override" \
  -H "X-API-Key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"action":"retry"}'
```

`action=retry` re-triggers `dispatcher.dispatch` on a live instance.

The proper fix is a DB-backed queue (spec 0056 design §F1).

## Related

- Spec 0042 — self-healing watchdog
- Spec 0056 — worker dispatch durability (the architectural fix)
- ADR 0011 — orphan reaper
- coder-core PR #45 — zombie_executing terminal-mark fix
- coder-core PR #47 — architect/TM prompt hardening
- 2026-04-28 session log — the wave-2 dispatch run that surfaced
  these patterns end-to-end
