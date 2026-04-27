---
id: dispatching-developer-tasks
title: Dispatching tasks via the developer worker
type: runbook
status: active
owner: ro
created: 2026-04-27
updated: 2026-04-27
last_verified_at: 2026-04-27
applies_to_services: [coder-core]
applies_to_integrations: [github, cloud-run]
---

# Dispatching tasks via the developer worker

How to send a code-implementation task to coder-core's developer worker
through the API, what the success path looks like, and how to recover
from the failure modes observed during the 2026-04-26 / 2026-04-27
0046+0052+0053 push.

This runbook is for a human operator dispatching directly via `curl`.
The same dispatch path is used by the pipeline-chain orchestrator when
chaining (PM → architect → TM → developer); the operator-driven path
is a subset of that.

## When to use this

- You have a sealed spec + design in coder-system main that defines
  a discrete code change in one repo.
- You want the change implemented as a reviewed PR, not committed
  directly.
- The change is single-repo and either greenfield-module-shaped (~250
  LoC of new code) or integration-shaped (~250 LoC + a non-trivial
  edit to an existing complex file).

## Pre-dispatch checklist

1. **One repo per task.** The dispatch's `repo` field designates one
   repo; the worker's workspace is that one repo. Cross-repo prompts
   (e.g. "add a yaml in coder-system AND a module in coder-core") will
   confuse the worker and time out. **Split into two dispatches.**
2. **Spec + design must be on coder-system `main`.** The architect /
   developer worker reads spec/design files from the knowledge repo
   at `main`, not from your working tree. If you've drafted in a
   branch but haven't merged, the worker can't see the canonical
   text.
3. **Wait for any in-flight CD rollout to settle** before dispatching.
   coder-core's CD pipeline takes ~6-7 min from merge to a ready
   revision. Dispatching during the rollout window risks the worker
   being killed by traffic shift (see § "Zombie executing"). A simple
   check:
   ```bash
   gcloud run revisions list --service=coder-core \
     --region=europe-west1 --limit=2 \
     --format='value(metadata.name, metadata.creationTimestamp)'
   ```
   The newest revision should be at least ~10 min old before you
   dispatch.
4. **Auth.** Per-project API key lives at
   `~/.config/coder/projects/<project>.key` (e.g. `coder.key`,
   `vibetrade.key`). Pass as `X-Api-Key` header.
5. **Tight prompt.** The longer the prompt, the more context Claude
   has to parse before doing useful work. Aim for: scope (what to
   ship), explicit out-of-scope list, file-list cap, branch-name
   directive, PR-meta. No more.

## The dispatch

```bash
CODER_KEY=$(cat ~/.config/coder/projects/coder.key)
curl -sS -X POST \
  -H "X-Api-Key: $CODER_KEY" \
  -H "Content-Type: application/json" \
  https://coder-core-8534948335.europe-west1.run.app/v1/projects/coder/tasks \
  -d @prompt.json
```

`prompt.json` body:
```json
{
  "role": "developer",
  "repo": "coder-core",
  "prompt": "..."
}
```

Response includes `task_id` and a one-time `worker_token`. The token
is unused in v0 (in-process worker writes back via SQLAlchemy) but
mint-once / not-stored; don't persist it.

## Lifecycle states

The orchestrator transitions tasks through:

```
queued → executing → testing → fixing → testing → reviewing → accepted
                       │           │
                       │           └─ at most MAX_FIX_ATTEMPTS retries on
                       │              internal pytest failure (spec 0025)
                       └─ Cloud Run instance running the claude CLI
```

Terminal states:

| status | stage | What happened |
|---|---|---|
| `succeeded` | `accepted` | PR opened, CI green-ish, reviewer accepted. **The success path.** |
| `succeeded` | `stuck` | Claude exited with success but no PR URL was extracted. See § "PR exists but task is stuck". |
| `failed` | `stuck` | Internal pytest exhausted MAX_FIX_ATTEMPTS or the worker hit a non-recoverable error. |
| `timed_out` | `stuck` | Worker hit `_DEFAULT_TIMEOUT_SECONDS` (currently 2400s = 40 min) without finishing. |
| `cancelled` | `rejected` | Operator called `POST .../override {action: reject}`. |

## Watching a dispatched task

Poll with the per-project key:

```bash
curl -sS -H "X-Api-Key: $CODER_KEY" \
  https://coder-core-8534948335.europe-west1.run.app/v1/projects/coder/tasks/$TASK_ID
```

Useful fields:
- `status` + `stage` — the terminal-state pair
- `pr_url` — populated when the worker prints a PR URL Claude opened
- `branch_name` — populated from the workspace's HEAD after claude exits
- `commit_sha` — populated from the workspace's HEAD
- `cost_input_tokens` / `cost_output_tokens` — non-cached input + output
- `cache_read_input_tokens` / `cache_creation_input_tokens` — prompt-cache hits (per spec 0029)
- `transcript_uri` — `gs://vibedevx-coder-worker-runs/...` for post-mortem

## Diagnostic commands

```bash
# Task logs (orchestrator-side stage transitions; sparse)
curl -sS -H "X-Api-Key: $CODER_KEY" \
  https://coder-core-8534948335.europe-west1.run.app/v1/projects/coder/tasks/$TASK_ID/logs

# Cloud Run logs filtered to one task
gcloud logging read 'resource.type="cloud_run_revision" AND
  resource.labels.service_name="coder-core" AND
  (textPayload:"'$TASK_ID'" OR jsonPayload.task_id="'$TASK_ID'")' \
  --limit=50 --freshness=1h

# Transcript (set on terminal, not during execution)
gsutil ls gs://vibedevx-coder-worker-runs/projects/coder/tasks/$TASK_ID/

# What's the live revision + which env it has
gcloud run services describe coder-core --region=europe-west1 \
  --format='yaml(spec.traffic, status.latestReadyRevisionName)'
```

## Recovery procedures by failure mode

### Zombie executing (deployment-rollout race)

**Symptom:** task stays `running` `executing` past 25 min with no log
activity. Cloud Run logs show a `DEPLOYMENT_ROLLOUT - Instance started`
event between the dispatch time and the present, and a corresponding
`Shutting down user disabled instance` shortly after.

**Cause:** the worker subprocess running `claude` was killed when the
Cloud Run instance hosting it got drained mid-task. The task row never
received a terminal-state write because the worker died before
finalising.

**Auto-recovery:** as of 2026-04-27, 0042 self-healing v1.1 runs the
`zombie_executing` pattern in `apply` mode
(`SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE=apply` on the live revision).
The watcher re-queues `status='running'` rows older than 25 min after
detecting them. In practice: **wait 1-2 minutes after the 25-min mark
and the orchestrator will re-queue automatically.**

**Manual override** if the auto-recovery hasn't fired (e.g. self-heal
flag flipped off or the watcher is misconfigured):
```bash
curl -sS -X POST -H "X-Api-Key: $CODER_KEY" \
  -H "Content-Type: application/json" \
  https://coder-core-8534948335.europe-west1.run.app/v1/projects/coder/tasks/$TASK_ID/override \
  -d '{"action": "reject"}'
```
Then re-dispatch the same prompt. The worker is stateless across
attempts — a fresh task picks up where the killed one left off (i.e.
nowhere; it starts over with a clean workspace).

**Prevention:** wait 10+ min after a coder-core merge before
dispatching. The CD rollout takes ~6-7 min; an extra few-min margin
covers the drain.

### PR exists but task is stuck (worker skipped step 5 of the contract)

**Symptom:** `status=succeeded` `stage=stuck` with
`error="executing stage reported success but produced no PR (pr_url is
null) — nothing to test or review"`. The task row's `branch_name` and
`commit_sha` are populated; `pr_url` is null.

**Cause:** Claude completed the task (writes + commit + push + PR
open) but its final message did not include the PR URL. The
developer-completion contract requires the URL on its own line in the
final message; the worker's `parse_pr_url` extracts the first PR URL
match from `result_text`; if there's none, `pr_url` stays null and
orchestrator's Fix #3 marks the task stuck.

**Recovery:**

1. Check whether a PR actually exists on the branch:
   ```bash
   gh pr list --repo coder-devx/coder-core --head $BRANCH_NAME --state open
   ```
2. If a PR exists, the work is done — review and merge as normal. The
   stuck task row is informational only; it doesn't block the PR.
3. If no PR exists but the branch is pushed:
   ```bash
   gh pr create --repo coder-devx/coder-core \
     --base main --head $BRANCH_NAME \
     --title "..." --body "..."
   ```
   (Use the commit message as the title; reference the spec.)
4. If neither branch nor commit exists, re-dispatch with a tighter
   prompt that emphasises step 5 of the contract.

**Tracked fix:** WIP `0054-orchestrator-github-state-reconciliation`
will teach the orchestrator to query GitHub for an open PR on the
task's `branch_name` before marking stuck — closing this gap
automatically.

### Timed out at the budget ceiling

**Symptom:** `status=timed_out` `stage=stuck` with
`error="coder task deadline exceeded after 2400s"`. No PR, no cost
data, branch may or may not be partially pushed.

**Current ceiling:** 2400s (40 min) per `_DEFAULT_TIMEOUT_SECONDS` in
[`coder-core/src/coder_core/workers/developer.py`](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/workers/developer.py).

**Cause:** the prompt's scope exceeds what Claude can deliver in 40
min. The 40-min ceiling was sized for "greenfield-module + integration
into one complex existing file" tasks; tasks larger than that
(multiple file edits in a 1k+ line module, or speculative refactors
without a clear scope) don't fit.

**Recovery:**

1. Cancel the timed-out task (it's already terminal; this is just to
   keep the admin UI tidy):
   ```bash
   curl -sS -X POST -H "X-Api-Key: $CODER_KEY" \
     -H "Content-Type: application/json" \
     https://coder-core-8534948335.europe-west1.run.app/v1/projects/coder/tasks/$TASK_ID/override \
     -d '{"action": "reject"}'
   ```
2. Split the prompt into two slices: a greenfield-module slice (just
   the new files + tests) and an integration slice (the edit to the
   existing file). Dispatch the module first; merge it; then dispatch
   the integration with the module already in place.

**When to bump `_DEFAULT_TIMEOUT_SECONDS` instead of splitting:** only
if the splitting attempt also times out, indicating the task itself is
genuinely large. Bumping is a code change in coder-core; splitting is
free.

### CD canary-promote gap

**Symptom:** you merge a PR to coder-core, the CD pipeline builds and
deploys a new revision, but production traffic stays on the prior
revision. The new revision shows `tag: canary` at 0% traffic.

**Cause:** the CD pipeline's traffic-promotion step did not run, or
ran with `--no-traffic` semantics. As of 2026-04-27 the operator-side
expected behaviour (auto-promote-to-100%) is **not** consistent across
deploys — observed during the 0053 push: PRs #34 and #35 promoted
correctly; PR #36 landed at 0% canary.

**Detection:**
```bash
gcloud run services describe coder-core --region=europe-west1 \
  --format='yaml(spec.traffic, status.latestReadyRevisionName)'
```
If `spec.traffic` shows the latest ready revision at < 100%, you have
the gap.

**Recovery — promote latest to 100%:**
```bash
gcloud run services update-traffic coder-core \
  --region=europe-west1 --to-latest
```

After promotion, verify:
```bash
curl -sS https://coder-core-8534948335.europe-west1.run.app/v1/health
gcloud run services describe coder-core --region=europe-west1 \
  --format='value(status.traffic[0].revisionName, status.traffic[0].percent)'
```

**Tracked investigation:** the canary-promote gap may be intentional
(blue/green safety) or a regression. Until investigated, treat it as
"check after every merge."

### Reviewer worker posts COMMENTED, not APPROVED

**Symptom:** the reviewer worker leaves a thorough analytical review
on the PR but the GitHub review state is `COMMENTED`, not `APPROVED`.

**Cause:** the `gh` CLI on the worker authenticates as the same
`coder-devx[bot]` identity that opened the PR. GitHub blocks
self-approval. The reviewer worker leaves a substantive
"ready-to-ship" comment in lieu of a formal approval.

**This is policy, not a bug.** The operator-side merge gate (option-4
manual squash-merge) is the deliberate safety property. If a future
spec needs branch-protection-required approving reviews, that's its
own work — likely a second GitHub identity for reviews.

## Pre-flight (active as of 2026-04-27)

Spec 0053 Stage 0a is live: every developer-worker task now runs
`uv run ruff format` + `uv run ruff check --fix` after `claude` exits
and before the task is finalised. Auto-fixes are committed as `chore:
apply preflight fixes` and pushed to the same branch. Surviving
failures (e.g. an unfixable lint, a mypy error) are commented on the
PR via `gh pr comment` but do not block.

**What this means in practice:** mechanical CI failures (the kind that
hit PR #34 with ruff format) no longer reach CI. If you see a CI-red
PR, the failure is a real one — not formatting drift.

**What this does *not* cover:**
- Real test failures (those still loop through the existing
  MAX_FIX_ATTEMPTS internal-test fix loop, spec 0025)
- CI failures from non-Python checks (terraform, build) — those land
  on the PR and require manual intervention until 0053 Stage 1 (the
  post-PR CI watcher) ships.

## Appendix — observed timings (2026-04-27)

For setting expectations on dispatch wall-clock:

| Task shape | Worker wall-clock | Tokens (non-cached) |
|---|---|---|
| 1 file, 16 LoC YAML | 3:46 | 284 in / 4840 out |
| 3 new files, ~250 LoC + tests, no existing-file edits | 22:18 | 4023 in / 31289 out |
| 2 new files, ~600 LoC + 12 tests, no existing-file edits | 22:23 | 949 in / 38238 out |
| 3 new files + edit existing 800-line worker | 21:00 | 3 in / 12 out (cache=72k) — but worker forgot to print PR URL |

## Links

- [developer-worker active spec](../product-specs/active/developer-worker.md)
- [task-orchestration active spec](../product-specs/active/task-orchestration.md)
- [self-healing active spec](../product-specs/active/self-healing.md)
- [worker-transient-failure runbook](./worker-transient-failure.md)
- [worker-schema-failure runbook](./worker-schema-failure.md)
- [pipeline-run-blocked runbook](./pipeline-run-blocked.md)
- WIP [0053 — post-PR CI fix loop](../product-specs/wip/0053-post-pr-ci-fix-loop.md)
