---
id: '0084'
title: Worker pr_url guard against duplicate PRs on retry
type: spec
status: wip
owner: ro
created: '2026-05-12'
updated: '2026-05-12'
last_verified_at: '2026-05-12'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- developer-worker
- task-orchestration
parent: pipeline-operations
---

# Worker pr_url guard against duplicate PRs on retry

**Phase:** wip
**Progress:** 0 / 4 acceptance criteria

## Problem

When a developer task is `action: retry`-overridden by the orchestrator (or operator) after it has already opened a PR, the second worker run produces a second PR for the same task — same `task_id`, different branch suffix. The first PR may have already merged; the second arrives stale and conflicting. The operator has to recognize it as a retry-spawn duplicate and close it manually.

Memory's recovery muscle memory captures the routine: "Close the duplicate after confirming the merged one has the full work." Closures in Phase A alone (per the tracking note): coder-core #215, #223, #226, #230, plus coder-admin #53, #57, #59. **Seven duplicate-PR closures in a single push.** Every one is a small operator cost but the cumulative friction is real, and Phase B's autopilot multiplies the volume.

The orchestrator's task row already has the right state to prevent this: `pr_url` gets populated on first-PR-open and stays set across retries (per the orchestrator's row model). The worker spawn path doesn't consult it. Adding a check — "if `task.pr_url` is set and the existing PR is still open, don't open a second one; resume against the existing PR's branch instead" — closes the gap.

The fix has to handle three branches of behaviour, based on the state of the pre-existing PR:

1. **Existing PR is open and unmerged** — worker should resume against the existing branch (`git checkout <existing_branch>` + push fixes there) rather than opening a new PR. This is the common retry-after-CI-failure case.
2. **Existing PR is merged** — the task's prior work shipped already. The worker run is wasted work; it should exit cleanly with `failure_kind=duplicate_retry_on_merged_pr` and let the orchestrator's unblock check pick it up.
3. **Existing PR is closed (not merged)** — operator intentionally killed the PR. The retry should proceed as today, opening a fresh PR. Distinct from cases 1 and 2.

## Users / personas

- **Operators driving the orchestrator.** Today they spend visible cycles closing retry-spawned duplicate PRs after every retry that fires post-PR-open. Under Phase B's autopilot, the cost compounds.
- **Reviewer worker.** Currently has to triage duplicate PRs as part of its queue. Removing the duplicate at source reduces reviewer noise.
- **Developer worker.** Should not waste a worker slot reproducing work that already shipped or is in flight on an existing PR.

## Goals

- A developer worker spawning for a retry checks `task.pr_url` before opening a new PR. The retry-open path branches on PR state (open/merged/closed) per the three cases above.
- The check is fail-open: if the GitHub API call to read PR state errors, the worker logs and proceeds as today (opens a fresh PR). Don't introduce a new way for retries to silently hang.
- Operator's `action: retry` override surface is unchanged. The fix is internal to the worker, not the override API.
- Distinct `failure_kind` codes for the three exit branches so memory and the operator dashboard can tell them apart.

## Non-goals

- Auto-closing duplicate PRs that have already been opened pre-this-fix. The cleanup of historical duplicates stays operator-side.
- Changing the orchestrator's queue model. Retries still spawn as separate task rows with `original_task_id` pointing back; this spec just changes what they *do* once they start.
- Cross-task-PR deduplication (e.g. two tasks accidentally targeting the same PR). Different gap; out of scope.

## Scope

One surface, narrow change:

**Developer worker spawn path** (`coder-core` `coder_core/workers/developer.py` — the pre-commit / pre-PR section). Before opening a new PR, check `task.pr_url`. If set, hit the GitHub REST API for that PR's state:

- `state=open AND merged=false` → resume against the existing branch. Worker run continues against `git checkout <existing_branch>`; the existing PR receives new commits and stays the same PR number.
- `state=closed AND merged=true` → terminal state. Worker exits with `failure_kind=duplicate_retry_on_merged_pr`, logs a structured event, no new PR opened, no fix attempts run. The orchestrator's unblock check (post spec 0083) sees the task chain and unblocks downstream.
- `state=closed AND merged=false` → operator-killed PR. Proceed as today: open a fresh PR. Log a structured event distinguishing this case from the no-prior-pr_url case.
- API-error path → log `developer.pr_state_check_failed`, fall through to the existing open-fresh-PR behaviour. Fail-open.

No admin-UI changes. The operator sees the duplicate-prevention reflected in the task's `failure_kind` chip on the Pipeline list when the duplicate-retry-on-merged-pr branch fires.

## Acceptance criteria

- **AC1.** Task `T_orig` opens PR `P` (state=open). Operator issues `action: retry` on `T_orig`. The retry worker reads `T_orig.pr_url`, sees `P` is open-and-unmerged, and resumes against `P`'s branch. `P` receives the retry's new commits; no second PR is opened. The retry's task row records the same `pr_url=P`.
- **AC2.** Task `T_orig` opens PR `P`, `P` merges. A retry fires (e.g. via a self-heal path that didn't notice the merge). The retry worker sees `P` is merged, exits with `failure_kind=duplicate_retry_on_merged_pr`, opens no new PR. The original task's `pr_url` stays set; the merged state is detectable on the task page.
- **AC3.** Task `T_orig` opens PR `P`, operator closes `P` without merging. A retry fires. The retry worker sees `P` is closed-not-merged and proceeds as today (opens a fresh PR). Distinct log line confirms the "operator-killed PR" branch fired.
- **AC4.** GitHub REST API returns 503 when the worker checks `P`'s state. The worker logs `developer.pr_state_check_failed`, falls through, and opens a fresh PR (matching today's behaviour). Regression guard: don't introduce a new hang path on a transient GitHub outage.

## Open questions

- Should AC1's "resume against existing branch" path also run the worker's pre-commit lint gate? Yes, for consistency — the gate runs on every PR commit anyway. Worth confirming in design.
- For AC2's `duplicate_retry_on_merged_pr` exit, should the worker also write a comment on the merged PR linking back to the task? Probably not — adds GitHub-side noise. The structured log + task-page state is the visible surface.
- The fail-open path (AC4) means a flaky GitHub API turns a duplicate-prevented case into the old duplicate-spawn behaviour. Operator-visible degradation, but accepts the risk. Consider a retry-with-backoff on the state-check call before falling through.

## Links

- Related operator memory: orchestrator-side gap #8 in the Phase A tracking note. Documents the seven duplicate-PR closures in Phase A alone and the recovery muscle memory.
- Related spec: `developer-worker` (active) — this spec extends the worker's commit/PR-open semantics. Needs an ADR if the pr_url-guard framework grows beyond developer (e.g. PM-worker spec drafts also race on duplicate-PR via the spec_run coordinator).
- Related spec: `0083-plan-unblock-checks-retry-chain.md` (this batch) — the AC2 path relies on 0083 for the post-exit unblock to fire automatically.
