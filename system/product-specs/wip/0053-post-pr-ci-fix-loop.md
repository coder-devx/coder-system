---
id: "0053"
title: Post-PR CI fix loop
type: spec
status: wip
owner: ro
created: 2026-04-27
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ["0053"]
related_specs:
  - developer-worker
  - reviewer-worker
  - task-orchestration
  - audit-log
  - admin-panel
---

# 0053 — Post-PR CI fix loop

## Problem

The developer worker's task lifecycle today ends at
`succeeded|accepted` once its internal pytest run passes and the
reviewer worker accepts the PR. **External GitHub Actions checks —
ruff format, lint, build, terraform, deploy — run independently, and
their failures aren't observed by the orchestrator.** Once a task is
terminal, the orchestrator stops watching. A CI-failing PR sits open
with no automated remediation; an operator must either push a manual
fix commit, retrigger CI, or close+redispatch.

Realised pain: PR #34 (0046 GraphExpander, 2026-04-27) succeeded
internally (pytest green, reviewer accepted) but failed CI on
`ruff format --check` — a one-file whitespace fix that consumed
operator time to push manually. The previous PR #33 happened to land
ruff-clean by luck. There's no system property guaranteeing CI green;
it's coincidence whether the worker's free-form code matches the
project's formatter.

The pipeline has a [fix-attempts loop](workers/orchestrator.py:737)
keyed on `stage == TaskStage.TESTING`, so internal pytest failures
trigger `executing → testing → fixing → executing` retries up to
`MAX_FIX_ATTEMPTS`. **External CI failures aren't wired into this
loop.** That's the gap.

## Users

- **Operator** — today receives a notification that a PR is CI-red,
  manually pushes a fix or redispatches. Wants the system to
  self-heal on mechanical CI failures (format, lint, simple
  type-check fixes) and only escalate when the failure is genuinely
  ambiguous.
- **Developer worker** — emits PRs that may be CI-red. Wants a
  pre-flight that runs the project's formatters/linters/typecheckers
  before opening, so the loop doesn't fire in the first place when
  the fix is purely mechanical.
- **Project owner** — wants to opt into / out of the fix loop per
  project; some repos may prefer hard-fail rather than auto-fix.

## Goals

- **Post-PR CI failures trigger automatic fix-up tasks** targeting
  the failing checks, up to `MAX_CI_FIX_ATTEMPTS` (default 3), then
  escalate to the operator queue.
- **Pre-flight on the developer worker** runs the project's
  formatter / linter / typechecker before opening the PR, so the
  loop only fires for irreducible cases (real test failures,
  semantic lint issues that need judgement, etc.).
- **No silent landings.** Every fix-up task writes an audit row;
  every escalation writes an audit row; the operator queue surfaces
  CI-stuck PRs distinctly from worker-stuck tasks.
- **Bounded concurrency.** Only one fix-up task per PR at a time;
  the watcher serialises on `(pr_url)`.
- **Reversible.** Per-project tri-state opt-out
  (`projects.ci_fix_loop_enabled`); fleet kill-switch
  `CODER_CI_FIX_LOOP_ENABLED`.

## Non-goals

- **Fixing semantic test failures.** This spec only auto-fixes
  *mechanical* CI failures (format, lint, simple type errors). A
  failing pytest assertion is a real bug; sending it back through
  the fix loop without bound risks the worker's mechanical retries
  papering over a real defect. The internal-test fix loop (existing
  `MAX_FIX_ATTEMPTS` from spec 0025) handles those during the
  worker's testing phase, not after PR open.
- **Approving / merging the fix-up commit.** Auto-merge of the
  fix-up commit is out of scope per the existing manual-merge
  posture. This spec lands the fix; the PR's existing review +
  human-merge flow is unchanged.
- **Generic webhook receiver beyond GitHub.** v1 watches GitHub
  Actions `check_run` events only. GitLab / Bitbucket / etc. are
  out of scope.
- **Cross-PR fix-ups.** A fix-up task targets the single PR whose
  CI failed; it does not bundle fixes across multiple in-flight
  PRs.

## Scope

### Stage 0 — Pre-flight on the developer worker

Cheap prevention. Before the worker invokes `gh pr create`, it runs:

- `uv run ruff format` (formats the diff in place — never `--check`)
- `uv run ruff check --fix` (auto-fixes lint that has a fix)
- Project-specific commands listed in `system/repos/<repo>.md`'s
  optional new `preflight_commands:` frontmatter list (e.g.
  `mypy`, `prettier --write`, etc.)

Failures of pre-flight commands that **don't auto-fix** (e.g. a
`ruff check` with an unfixable lint, a `mypy` error) cause the
worker to either:
- Re-prompt itself once with the failure context (similar shape to
  the existing testing-stage fix loop), OR
- If the error survives the re-prompt, fall through to opening the
  PR anyway (so the operator sees the real CI failure with the
  worker's best effort recorded).

The preflight runs *after* the worker's own tests pass and *before*
`git push` + `gh pr create`. Its output is captured into the task's
transcript for diagnostic visibility.

### Stage 1 — Post-PR CI watcher + fix-up dispatcher

A new component `coder_core/integrations/ci_watcher.py` subscribes
to GitHub `check_run` events for PRs opened by managed workers.
On every `check_run` `completed` event:

- **Filter to managed PRs.** The watcher only acts on PRs whose
  branch matches `task/*` and whose author is the worker SA. Skip
  human-authored PRs.
- **Aggregate the PR's check status.** Pull all check_runs for the
  PR's HEAD SHA. If any are `failure`, the PR is CI-red.
- **Build a fix_context.** Pull the failed check's logs (top
  `ci_fix_log_tail_lines`, default 200) and a structured summary
  (which check, what command, what error excerpt).
- **Dispatch a fix-up task.** New developer task on the same repo,
  targeting the same PR's branch, with prompt:
  ```
  # CI fix-up
  
  PR: <url>
  Branch: <branch>
  Failed check: <name>
  Failure excerpt: <log tail>
  
  Apply the minimum diff to make CI green. Do not change
  semantics. Push to the same branch — do NOT open a new PR.
  ```
  The fix-up task carries `original_task_id` pointing at the
  original developer task, so the audit trail is connected.
- **Concurrency.** Only one fix-up task per `(project, pr_url)` at a
  time. Concurrent CI failures during a fix-up retry are coalesced.
- **Bounded retries.** A `ci_fix_attempts` counter on the
  `pr_to_task_map` row caps at `MAX_CI_FIX_ATTEMPTS` (default 3).
  After exhaustion, the watcher writes an `audit_events.action =
  ci_fix_loop.escalated` row with the PR URL and the surviving
  failure excerpt; an admin/operator queue (existing from 0041
  escalations) surfaces it.

### Stage 2 — Admin surface

A new card on the existing admin panel's RunDetail / TaskDetail
view shows the CI fix-up history for a PR: the original task, each
fix-up attempt's task id + outcome, current attempt counter, and
the last failure excerpt if escalated. Behind
`VITE_CI_FIX_LOOP_ENABLED`.

### In scope — config + flags

- `coder_ci_fix_loop_enabled: bool = False` (fleet master switch;
  default off until pre-flight stabilises)
- `projects.ci_fix_loop_enabled BOOLEAN NULL` (per-project
  tri-state, NULL inherits)
- `ci_fix_max_attempts: int = 3`
- `ci_fix_log_tail_lines: int = 200`

### In scope — schema

- `pr_to_task_map` table (migration 0057):
  `(pr_url PRIMARY KEY, original_task_id, current_fix_task_id,
   ci_fix_attempts, last_failure_kind, last_failure_excerpt,
   escalated_at, created_at, updated_at)`
- `tasks.original_task_id` already exists (per [task.py:383](coder-core/src/coder_core/domain/task.py)) — re-use it
  for fix-up tasks; no new column needed there.

### Out of scope

- Fixing semantic pytest failures (existing internal fix loop
  handles those during testing stage)
- Auto-merge of fix-up commits (manual merge posture preserved)
- Cross-CI providers beyond GitHub Actions
- Fix-up tasks bundled across multiple PRs
- Pre-flight on non-developer roles (PM/architect/TM don't open
  PRs to coder-core; out of scope)

## Acceptance criteria

- **AC1. Pre-flight on developer worker.** The developer worker
  runs `uv run ruff format` and `uv run ruff check --fix` against
  the working copy after its own tests pass and before `git push`.
  If either command exits non-zero AFTER attempted auto-fix, the
  worker re-prompts itself once with the failure context; if the
  error survives re-prompt, opens the PR anyway with a body note.
  Test: a worker task whose code triggers a ruff format issue
  produces a CI-clean PR (the pre-flight applied the fix before
  push).

- **AC2. CI watcher subscribes to check_run.** A new endpoint on
  coder-core (`POST /v1/_internal/github/check-run-webhook`)
  receives GitHub Actions `check_run` events; verifies the
  GitHub webhook signature; filters to managed-worker PRs;
  short-circuits when `coder_ci_fix_loop_enabled` is False (returns
  204 No Content without writing state).

- **AC3. CI failure triggers fix-up dispatch.** When a managed PR
  has any `check_run.completed` with `conclusion == failure`, the
  watcher dispatches a developer task on the PR's repo+branch with
  prompt header `# CI fix-up`, fix_context populated with the
  failure excerpt, and `original_task_id` pointing at the original
  task. Test: green-then-red transition produces exactly one
  fix-up task; the same red event arriving twice produces zero
  additional dispatches (concurrency dedupe via `pr_to_task_map`).

- **AC4. Fix-up task pushes to the same branch.** The fix-up
  worker's prompt explicitly forbids opening a new PR; it pushes
  to the original PR's branch via the worker's existing branch-
  push helper. Test: after a fix-up succeeds, the PR's commit
  count increased by exactly one and no new PR was opened.

- **AC5. Bounded retries + escalation.** After
  `MAX_CI_FIX_ATTEMPTS` (default 3) consecutive fix-up failures
  on the same PR, the watcher writes
  `audit_events.action = ci_fix_loop.escalated` with the PR URL
  and surviving failure excerpt; the next CI-red event for the
  same PR is a no-op (won't re-dispatch). The operator queue
  (0041) surfaces the escalation as a CI-stuck PR.

- **AC6. Per-project opt-out.**
  `projects.ci_fix_loop_enabled` (NULL / true / false tri-state).
  When false explicitly, the watcher skips the project entirely
  even if the fleet flag is on. PATCH endpoint to toggle.

- **AC7. Audit.** Every state change writes an `audit_events` row:
  `ci_fix_loop.dispatched`, `ci_fix_loop.succeeded`,
  `ci_fix_loop.failed`, `ci_fix_loop.escalated`. `actor_type='system'`
  for watcher-driven actions.

- **AC8. Admin surface.** RunDetail / TaskDetail view shows a
  CI Fix Loop card with: original task id, list of fix-up
  attempts (each with its task id + outcome), current attempt
  counter, last failure excerpt if escalated. Behind
  `VITE_CI_FIX_LOOP_ENABLED`.

- **AC9. Flag-gated fleet-wide on
  `CODER_CI_FIX_LOOP_ENABLED`** (default off on first deploy).
  When off, the watcher endpoint returns 204; the pre-flight
  (AC1) still runs because it's worker-side and cheap.

## Metrics

- **Pre-flight save rate** — `% of dev tasks where pre-flight
  applied a fix that would have failed CI`. Headline KPI for
  Stage 0; target: > 50% of mechanical issues caught here.
- **Fix-loop dispatch rate** — `% of managed PRs that triggered
  at least one fix-up task`. Trends over time; should drop as
  pre-flight matures.
- **Fix-loop success rate** — `% of fix-up tasks that produce a
  CI-green PR within MAX_CI_FIX_ATTEMPTS`.
- **Escalation rate** — `% of CI-failed PRs that exhaust the loop
  and require operator intervention`. Should be < 10% of dispatch
  rate; sustained higher means the worker's prompt or capability
  needs work.
- **Wall-clock to CI green** — `time from PR open to all checks
  green, per PR`. Tracks user-visible "is the system done with
  this?" experience.

## Decisions

Resolved 2026-04-27 at spec creation.

- **Two stages, one spec.** Pre-flight (Stage 0) and post-PR loop
  (Stage 1) are two halves of the same problem; bundled in one
  spec for narrative coherence. They land as separate PRs.
- **Webhook over polling.** GitHub `check_run` webhooks are real-
  time and avoid the rate-limit hassle of polling. The webhook
  endpoint is mounted at `/v1/_internal/github/check-run-webhook`
  with HMAC verification (same shape as 0052's receiver).
- **Re-use `original_task_id` for the link, not a new column.**
  The existing field already supports the fix-up → original
  relationship.
- **Fix-up worker pushes to the same branch.** A new PR per
  fix-up would balloon the review queue. Same-branch push keeps
  the original PR's review thread intact.
- **MAX_CI_FIX_ATTEMPTS = 3.** Matches the existing internal
  `MAX_FIX_ATTEMPTS` for testing-stage retries (consistency with
  spec 0025's contract).
- **Escalation goes through 0041 (escalations) infrastructure**,
  not a parallel notification path. Re-uses the existing on-call
  routing.

## Open questions

- **Should the watcher also act on `workflow_run` events as a
  belt-and-braces backup?** check_run is the granular signal but
  some custom Actions emit workflow-level conclusions only. v1
  is check_run-only; revisit if a real workflow_run-only failure
  shows up.
- **Pre-flight commands for non-Python repos.** The default list
  (`ruff format`, `ruff check --fix`) is Python-specific. For a
  TypeScript repo (e.g. coder-admin) the worker needs prettier +
  eslint. The `system/repos/<repo>.md` `preflight_commands:`
  frontmatter list defers per-repo customisation to the project.
  But the *defaults* for new repos need a sensible list. Punt to
  design.
- **Escalation noise.** A genuinely-broken main branch will
  cascade-escalate every fix-up attempt across every in-flight
  PR. Should the watcher detect and pause the loop fleet-wide
  when N PRs escalate within a window? Probably yes; design to
  specify the threshold (e.g. 5 escalations in 1h → fleet pause
  with audit row).
- **Cost ceiling per PR.** The fix-up loop can burn tokens. A
  per-PR cost ceiling (say 100k tokens across all attempts)
  prevents a runaway loop on a hard-to-fix CI issue. Probably
  yes; needs design specification.

## Links

- Designs: [0053](../../designs/wip/0053-post-pr-ci-fix-loop.md) (pending architect review)
- Related specs:
  [developer-worker](../active/developer-worker.md),
  [reviewer-worker](../active/reviewer-worker.md),
  [task-orchestration](../active/task-orchestration.md),
  [audit-log](../active/audit-log.md),
  [admin-panel](../active/admin-panel.md)
- Related to: [0025](../../adrs/) worker output compliance
  (internal fix loop), [0027](../../adrs/) transient-failure
  retry, [0041](../active/escalations.md) escalations
