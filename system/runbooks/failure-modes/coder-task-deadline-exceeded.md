---
id: coder-task-deadline-exceeded
title: Coder task deadline exceeded — process ran past 2400s
type: runbook
subtype: failure-mode
status: active
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
failure_kind: coder_task_deadline_exceeded
signal: 'failure_detail =~ "coder task deadline exceeded after"'
suggested_action: retry_with_edit
owning_role: developer
related_runbooks:
  - claude-exit-1
  - dispatching-developer-tasks
---

# Coder task deadline exceeded after 2400s

## What it is

The runner kills a worker that runs longer than the dispatch
deadline (currently 2400s = 40min for developer tasks). The
orchestrator records `failure_kind: coder_task_deadline_exceeded`.
Operators see this on Now as "deadline exceeded" or
`coder-task-deadline-exceeded` and on the task page as a stuck row
with no PR.

By volume the second-most-common stuck-task failure shape in the
fleet — 3 of 27 stuck tasks observed in the 2026-05-09 walk of
`coder` were this kind, with the oldest sitting 12 days.

## Why it happens

In rough order of frequency:

1. **Spec scope too large.** The dispatched task asks for >3
   deliverables in one developer turn — the agent fans out and
   doesn't finish. Memory note
   [feedback_large_task_workers_timeout](../../../../-Users-ro-Projects-coder-coder-system/memory/feedback_large_task_workers_timeout.md)
   confirms this pattern.
2. **Search loop blowing the budget.** The agent gets stuck doing
   broad codebase scans without making progress. Symptom on the
   tool-uses panel: many `Grep`/`Read` calls, no `Edit` / `Write`
   calls past the first 10 minutes.
3. **External dependency hang.** A `gh` call, a network fetch, or a
   slow tool waits past the deadline. Symptom: long quiet stretch
   in the tool-uses panel near the deadline.
4. **Pre-flight ruff format hung.** Spec 0053 Stage 0a runs `ruff
   format` before commit; on a very large diff this can sometimes
   exceed the agent's working budget.

## How to detect

- Now: a row labeled "deadline exceeded" with `failure_kind:
  coder_task_deadline_exceeded`.
- TaskDetail: stage timeline ends red on `executing`; total wall
  time pinned at ~2400s; last tool use shortly before the
  termination point.

## Suggested action

1. **Look at the tool-uses panel.** Was the agent making forward
   progress (writing code) or spinning (broad searches, repeated
   reads of the same files)?
2. **If the prompt was too big**: click `replay with edit`, split
   the work — keep one deliverable in the new prompt, log the rest
   as follow-ups.
3. **If the agent was spinning**: replay with edit and add a
   constraint — name the files explicitly, give the agent a smaller
   target. The default 2400s deadline doesn't change; the prompt
   needs to fit it.
4. **If the agent was waiting on an external call**: retry once.
   If it fails the same way, escalate — this is probably an outage
   in the dependency, not a worker bug.

## When to escalate

- ≥3 deadline-exceeded tasks open in one project for ≥6h: spec
  0071 Stage 3 watchdog rule fires.
- A single task at this `failure_kind` for ≥48h with no operator
  action: same rule.
- Repeated same-prompt deadline-exceeded after replay-with-edit:
  the spec may genuinely be too big; mark the spec for re-scoping
  rather than continuing to retry.

## Related runbooks

- [claude-exit-1](./claude-exit-1.md)
- [dispatching-developer-tasks](../dispatching-developer-tasks.md)
