---
id: "0054"
title: Orchestrator GitHub-state reconciliation
type: spec
status: wip
owner: ro
created: 2026-04-27
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ["0054"]
related_specs:
  - developer-worker
  - task-orchestration
  - audit-log
---

# 0054 — Orchestrator GitHub-state reconciliation

## Problem

The orchestrator's "Fix #3" check in
[`workers/orchestrator.py`](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/workers/orchestrator.py)
marks a developer task `succeeded|stuck` when the executing stage
reports success but no PR URL was extracted from the worker's stdout:

```python
if status == TaskStatus.SUCCEEDED.value:
    if stage == TaskStage.EXECUTING.value:
        if not row.pr_url:
            new_stage = TaskStage.STUCK.value
            row.error = "executing stage reported success but produced no PR..."
```

**Realised pain (2026-04-27, task `22089ec6` → coder-core#36):** Claude
completed the task fully — wrote the new files, made a commit, pushed
the branch (`task/0053-preflight`), AND ran `gh pr create` (the PR
exists at coder-core#36). But Claude's final message was *"Both
background test runs passed. All clear."* without including the PR
URL. The worker's `parse_pr_url` returned `None`. Orchestrator's Fix
#3 marked the task stuck with the canonical error message.

The artifact (a green-CI mergeable PR) existed; the task row diverged
from reality. The operator had to manually:
1. Check GitHub for the branch (`task/0053-preflight`)
2. See if a PR was open on it
3. Discover that the PR existed
4. Proceed with normal review/merge

That manual reconciliation is exactly what the orchestrator should do
on the operator's behalf — the data needed (`branch_name`,
`commit_sha`) is already on the task row; the missing piece is the
GitHub-side check.

## Users

- **Operator** — today reads "succeeded|stuck — produced no PR" and
  has to manually check GitHub before deciding whether the task is
  actually broken or just contract-noncompliant. Wants the
  orchestrator to do the check.
- **Developer worker** — its existing completion contract still asks
  for the PR URL in the final message; this spec doesn't relax that.
  But when the contract slips, the orchestrator stops treating it as
  a stuck task.
- **Audit consumers** — every reconciliation writes an audit row so
  the rate at which the contract slips is visible.

## Goals

- **Eliminate the "PR exists but task stuck" failure class** by
  having the orchestrator query GitHub for an open PR on the task's
  `branch_name` before transitioning to STUCK.
- **No silent reconciliation.** When the orchestrator finds a PR on
  the branch, it writes an audit row
  (`task.pr_url_reconciled_from_github`) so the rate is observable
  and any anomalies surface.
- **Bounded blast radius.** The reconciliation is read-only against
  GitHub (single `gh pr list --head <branch>` equivalent call), runs
  only on the success-with-no-PR path, never modifies a PR that
  already exists, and never opens a new PR on the operator's behalf.
- **Backward compatible.** Tasks where Claude DOES print the PR URL
  continue to work exactly as today — the new check is a fallback,
  not a replacement.
- **Cheap.** One GitHub API call per stuck-with-no-PR transition.
  Falls within the existing per-project GitHub PAT budget; no new
  rate-limit surface.

## Non-goals

- **Opening a PR if one doesn't exist.** If the branch is pushed but
  no PR is open, the orchestrator still marks the task stuck — the
  operator decides whether to open the PR manually or re-dispatch.
  Auto-PR-open is out of scope; it would be making a write decision
  on the worker's behalf based on incomplete signal.
- **Reconciling tasks that timed out or failed.** This spec only
  addresses the `succeeded|executing|no pr_url` path. Timeout and
  fail paths have different recovery semantics (see
  [dispatching-developer-tasks runbook](../../runbooks/dispatching-developer-tasks.md)).
- **Generalised post-hoc state reconciliation.** This is the one
  failure class observed today. Other state-divergence cases (e.g.
  cost data missing, transcript missing) are not addressed here.
- **Cross-project reconciliation.** Each project has its own GitHub
  org + repo configuration; the reconciliation uses the same
  per-project credentials as the worker.
- **Closing the developer-worker contract gap upstream.** Improving
  the developer worker's prompt to make it more reliably print the
  PR URL is a separate, complementary spec; this one closes the
  catch-net side.

## Scope

### In scope — orchestrator check

In [`workers/orchestrator.py`](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/workers/orchestrator.py),
inside the `succeeded|executing|no pr_url` branch, before the STUCK
transition, add a reconciliation call:

```python
if status == TaskStatus.SUCCEEDED.value:
    if stage == TaskStage.EXECUTING.value:
        if not row.pr_url:
            # NEW: try to reconcile from GitHub before marking stuck.
            reconciled_url = await _reconcile_pr_url_from_github(
                session=session,
                task_row=row,
            )
            if reconciled_url is not None:
                row.pr_url = reconciled_url
                # fall through to the normal "PR exists" path; the next
                # orchestrator tick transitions executing → testing
                # exactly as if Claude had printed the URL.
                await _log_stage_transition(
                    session, row, from_stage=stage, new_stage=stage,
                    outcome="pr_url_reconciled_from_github",
                    triggered_by="orchestrator",
                )
                await session.commit()
                return stage
            # Otherwise: the existing stuck-transition path runs unchanged.
            new_stage = TaskStage.STUCK.value
            row.stage = new_stage
            row.error = "executing stage reported success but produced no PR..."
```

### In scope — `_reconcile_pr_url_from_github` helper

New helper in `workers/orchestrator.py` (or a small adjacent module
if it grows beyond a single function — author's call):

```python
async def _reconcile_pr_url_from_github(
    *,
    session: AsyncSession,
    task_row: TaskRow,
) -> str | None:
    """Return the URL of an open PR on the task's branch, if any.

    Returns None if:
      - branch_name is not set on the task row (worker never pushed),
      - GitHub returns no open PR on that branch,
      - the call errors (logged + audit-noted, returns None — fail
        soft to the existing stuck-transition path),
      - the project is not configured for the github_org / repo lookup.

    No-op for non-developer roles or for tasks without a workspace.
    """
```

Behaviour:

1. **Guard.** If `task_row.branch_name` is None or empty → return None
   immediately (the worker never pushed; nothing to reconcile against).
2. **Resolve org + repo.** Use the existing
   `projects.github_org` lookup + the task's `repo` field to construct
   the full repo identifier.
3. **Query GitHub.** Use the existing `GitHubClient` (re-use whatever
   workers and the merge endpoint use today). Call the equivalent of
   `GET /repos/{org}/{repo}/pulls?head={org}:{branch_name}&state=open`.
4. **Pick the PR.** Of the open PRs on that branch, pick the one whose
   author is the project's GitHub-App installation (the worker's
   identity). If multiple match, take the most recently created. If
   the only matches are human-authored, return None (we don't
   reconcile against PRs the operator opened separately).
5. **Audit + return.** On a successful reconciliation, write an
   `audit_events` row with
   `action='task.pr_url_reconciled_from_github'`,
   `target_type='task'`, `target_id=task_row.id`, `details={'pr_url':
   <url>, 'branch_name': <branch>, 'commit_sha': <sha>}`. Return the
   URL.
6. **Fail-soft.** Any unhandled exception → log + audit
   `action='task.pr_url_reconcile_failed'` with the error class +
   message + return None. The existing stuck-transition path takes
   over.

### In scope — audit actions

Two new action strings:
- `task.pr_url_reconciled_from_github` — successful reconciliation
- `task.pr_url_reconcile_failed` — query errored or returned
  unexpected shape

### In scope — flag-gating

`coder_orchestrator_pr_url_reconcile_enabled: bool = False` (default
off). When False, the new branch is short-circuited and the existing
behaviour runs unchanged. Allows shadow-mode rollout: flip on,
observe the audit-row rate, then trust it.

### In scope — tests

Unit tests for `_reconcile_pr_url_from_github` covering:

- branch_name absent → returns None, no GitHub call made
- GitHub returns no open PR → returns None, no audit row written
- GitHub returns one matching PR (worker-authored) → returns URL,
  audit row written
- GitHub returns one matching PR (human-authored) → returns None
  (we don't reconcile against operator-opened PRs)
- GitHub returns multiple matching PRs → returns the
  most-recently-created
- GitHub call raises → returns None, fail-soft audit row written

Integration test: end-to-end orchestrator transition where a task is
in `succeeded|executing` with `pr_url=None` but `branch_name=foo`
and a matching PR exists on GitHub (mocked via the test client).
After the orchestrator tick, `task_row.pr_url` is populated from
the reconciliation and the stuck transition is NOT taken.

### Out of scope

- Opening a new PR if the branch is pushed but no PR exists (manual
  recovery, per the runbook).
- Reconciling tasks that timed out or failed (different recovery
  semantics).
- Reconciling for non-developer roles (PM/architect/TM workers don't
  push branches; the failure class doesn't apply).
- Improving the developer-worker prompt to reduce the contract-slip
  rate at source (separate spec).
- A retry loop if the GitHub call fails. v1 fails soft on first error;
  the existing zombie-recovery path handles longer-term stuck cases.

## Acceptance criteria

- **AC1.** `coder_core.workers.orchestrator` exports
  `_reconcile_pr_url_from_github` (or equivalent module-private
  helper) with the documented behaviour. The function is async,
  returns `str | None`, and never raises.

- **AC2.** The orchestrator's `succeeded|executing|no pr_url` branch
  calls the helper before the STUCK transition. On a non-None
  return, sets `task_row.pr_url`, writes a stage-transition log
  with `outcome='pr_url_reconciled_from_github'`, and returns the
  current stage (the next orchestrator tick handles the
  `executing → testing` transition naturally). On None, the existing
  STUCK transition runs unchanged.

- **AC3.** Two new audit action strings —
  `task.pr_url_reconciled_from_github` and
  `task.pr_url_reconcile_failed` — registered in the audit-action
  enum. Both write `target_type='task'`, `target_id=<task_id>`,
  with `details` carrying enough context (`pr_url`, `branch_name`,
  `commit_sha` on success; `error_class`, `error_message` on
  failure).

- **AC4.** Settings flag
  `coder_orchestrator_pr_url_reconcile_enabled: bool = False` in
  `coder_core/config.py` gates the new behaviour. When False, the
  orchestrator branch is bypassed entirely (no GitHub call made).

- **AC5.** Unit tests cover the six branches in § "In scope —
  tests". GitHub client mocked via existing test fixtures.

- **AC6.** Integration test: dispatch a synthetic task with
  `succeeded|executing|pr_url=None|branch_name=foo`; mock GitHub to
  return a matching PR; assert the orchestrator transition does NOT
  go to STUCK and `task_row.pr_url` is populated.

- **AC7.** Backward compatibility: tasks where Claude DOES print the
  PR URL run identically to today (no extra GitHub call, no audit
  rows). Test: a task whose worker output includes a PR URL is
  parsed by the existing `parse_pr_url` and the new code path is
  not entered.

- **AC8.** Documentation: update [`developer-worker`
  active spec](../active/developer-worker.md) Evolution section
  with the reconciliation behaviour. Update the
  [dispatching-developer-tasks
  runbook](../../runbooks/dispatching-developer-tasks.md)'s
  "PR exists but task is stuck" section to note that v0.0.4+ does
  this automatically, with the manual `gh pr list / gh pr create`
  steps as the v0.0.3 fallback.

## Metrics

- **Reconciliation hit rate** — count of
  `task.pr_url_reconciled_from_github` audit rows per week. Headline
  KPI: tracks the rate at which the developer-worker contract slips.
  Trends over time should drop as the developer-worker prompt
  matures; sustained high rate is a signal to invest in the
  upstream contract.

- **Reconciliation failure rate** — count of
  `task.pr_url_reconcile_failed` rows per week. Sustained > 5% of
  reconciliation attempts is a signal that the GitHub API call
  shape needs revision (rate limits, auth issues, etc.).

- **Stuck-task false-positive elimination** — count of
  `succeeded|stuck` transitions with `error="executing stage
  reported success but produced no PR..."` per week. Should drop
  to ~0 once this spec ships and the flag is on. Any residual
  count is a real failure (genuinely missing PR, e.g. Claude
  didn't push the branch).

## Decisions

Resolved 2026-04-27 at spec creation.

- **Read-only against GitHub.** No PR opened, no PR closed, no
  comment posted. The reconciliation is purely about discovering
  state that already exists. Auto-PR-open would be making a write
  decision on incomplete signal (worker exited successfully but
  didn't push? didn't create? we can't tell from the task row
  alone).
- **Worker-authored PRs only.** If the only match on the branch is
  human-authored, we don't reconcile. The operator may have opened
  their own PR for some reason (e.g. recovery from a prior failure)
  and we shouldn't conflate the two. Worker-authored is identified
  by the GitHub-App installation's bot identity.
- **Fail-soft to the existing stuck path.** If anything goes wrong
  in the reconciliation (GitHub API down, auth misconfigured,
  unexpected response shape), the existing stuck-transition runs.
  We never block a task because reconciliation failed.
- **Flag-gated for shadow rollout.** Off by default; flipped on
  fleet-wide after a soak window observing the audit-row rate.
- **No retry loop.** First call succeeds or returns None. The
  zombie-recovery path (0042 v1.1) handles tasks that genuinely got
  stuck for longer.
- **Single helper, not a new module.** The function fits in
  orchestrator.py alongside the existing
  `_log_stage_transition` and `_build_fix_context` helpers.
  Promote to a separate module only if a second reconciliation
  shape emerges.

## Open questions

- **Should the helper handle non-`task/*` branch names?** Some
  worker workflows might push branches with different prefixes
  (e.g. `chore/*` if Claude decided the change was a chore). v1
  matches any branch name on the task row's `branch_name` field —
  the task row's value is the source of truth, not a regex.
  Worth confirming in implementation that all worker push paths
  populate `branch_name` correctly.

- **Multi-PR-on-branch semantics.** GitHub allows multiple PRs on
  the same branch in different states (e.g. one closed, one open).
  The query is `state=open` so closed PRs don't surface — but
  conceptually, if a worker pushed a branch, a PR was opened, the
  PR was closed (e.g. because the branch was force-pushed), and
  then a new PR was opened on the same branch — does the
  reconciliation pick the newest open PR? v1 semantics: yes,
  newest open PR by `created_at`.

- **Project configuration coverage.** `projects.github_org` exists
  for managed projects. What about the rare case where a task is
  dispatched against a project that hasn't been onboarded with a
  github_org config? The helper returns None (no GitHub call
  attempted). Worth a clear log message so the operator can fix
  the project config rather than silently degrade.

- **Race with the worker's audit-of-claude-stdout flow.** If the
  worker's stdout-parser races with the orchestrator's
  reconciliation tick, we might write `pr_url` twice. The second
  write is idempotent (same URL value), but worth a defensive
  check that `task_row.pr_url` is still None at write time.

## Links

- Designs: [0054](../../designs/wip/0054-orchestrator-github-state-reconciliation.md)
- Related specs:
  [developer-worker](../active/developer-worker.md),
  [task-orchestration](../active/task-orchestration.md),
  [audit-log](../active/audit-log.md)
- Related runbook:
  [dispatching-developer-tasks](../../runbooks/dispatching-developer-tasks.md)
- Realised pain: [coder-core#36](https://github.com/coder-devx/coder-core/pull/36)
  (the dispatch where this failure mode was observed)
