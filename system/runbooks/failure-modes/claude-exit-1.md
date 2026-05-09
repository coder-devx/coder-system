---
id: claude-exit-1
title: Claude exited with code 1
type: runbook
subtype: failure-mode
status: active
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
failure_kind: claude_exit_1
signal: 'failure_detail =~ "claude exited with code 1"'
suggested_action: retry
owning_role: developer
related_runbooks:
  - coder-task-deadline-exceeded
  - dispatching-developer-tasks
---

# Claude exited with code 1

## What it is

The worker subprocess running `claude` exited with status 1 before
producing the artifact the role contract requires. The orchestrator
catches the non-zero exit and writes `failure_kind: claude_exit_1`
on the task row. Operators see this on Now as "claude exited code
1" and on the task page as a stuck row with no PR.

By volume this is the most common stuck-task failure shape in the
fleet — 6 of the 27 stuck tasks observed in the 2026-05-09 walk
of `coder` were this kind, with the oldest sitting 15 days.

## Why it happens

In rough order of frequency:

1. **Prompt mid-stream cutoff.** The model produced content but the
   process was killed by the runner's SIGKILL before the worker
   wrote the artifact. Cloud Run instance churn is the usual cause —
   see [project_cloud_run_orphan_dispatches](../../adrs/) lineage.
2. **Tool failure inside the session.** A tool the agent called
   (Bash, Edit, Write) returned an error the agent couldn't recover
   from, and the agent exited rather than ask. Often a permission
   denied on a sandboxed Bash command or a missing file in an Edit.
3. **Stale prompt context.** The dispatched prompt referenced files
   or a branch state that no longer matches the repo (e.g. a
   teammate landed an overlapping PR). The agent realises it cannot
   do the work as specified and bails. Most useful retry shape is
   `retry_with_edit` (spec 0072 stage 2) so the operator can refresh
   the prompt before the next attempt.
4. **Out-of-budget mid-task.** If the per-task budget gate trips
   while a tool is mid-call, the wrapper kills the process and
   surfaces as exit 1 on the runner.

## How to detect

- Now: a row labeled "claude exited code 1" with `failure_kind:
  claude_exit_1`.
- TaskDetail: stage timeline ends red on `executing`; tool-uses
  panel shows partial activity; logs link points at the Cloud Run
  execution.
- Aggregate: ≥3 rows with the same `failure_kind` in one project
  collapse into a `stuck-group` row (spec 0071 Stage 2).

## Suggested action

1. **Open the most recent stuck task.** Read the last few tool uses
   on the TaskDetail tool-uses panel — that usually shows the
   immediate cause (which tool, which file, which error).
2. **If the prompt looks stale** (referenced files have moved,
   referenced branch was force-pushed, AC has changed since dispatch):
   click `replay with edit`, refresh the prompt, dispatch.
3. **If the prompt still looks fresh and the tool error was
   transient** (timeout, 502, missing token): click `retry`. Most
   single retries succeed when the cause was instance churn.
4. **If the same task fails the same way twice**: stop retrying.
   That's now a `manual_only` situation — read the worker code path
   and the agent contract; the prompt might be asking the worker
   to do something it cannot do.

## When to escalate

- ≥3 of the same `failure_kind` open in one project for ≥6h: the
  watchdog rule (spec 0071 Stage 3) opens an escalation; an oncall
  human picks it up.
- A single task at this `failure_kind` for ≥48h with no operator
  action: the same watchdog rule.
- Any project where the count of `claude_exit_1` doubles in 24h:
  an oncall human pages, since that pattern usually means a
  systemic change (model regression, runner-image issue) not a
  per-task problem.

## Related runbooks

- [coder-task-deadline-exceeded](./coder-task-deadline-exceeded.md)
- [dispatching-developer-tasks](../dispatching-developer-tasks.md)
