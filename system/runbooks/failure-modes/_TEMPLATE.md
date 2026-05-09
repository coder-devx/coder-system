---
id: my-failure-kind
title: Short title — what happens, what to do
type: runbook
subtype: failure-mode
status: active
owner: ro
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_verified_at: YYYY-MM-DD
failure_kind: my_failure_kind
signal: 'failure_detail =~ "regex over the failure_detail string"'
suggested_action: retry         # retry | retry_with_edit | escalate | manual_only
owning_role: developer          # developer | pm | architect | reviewer | team_manager
related_runbooks: []
---

# {Title}

## What it is
One paragraph explaining the failure mode in operator terms — what
the row on Now actually means.

## Why it happens
The known causes, ordered by frequency. Cite incidents, dispatch
sessions, or audit rows where you can.

## How to detect
The signal regex above is the machine-readable version. Spell out the
human signal here too: which UI surfaces this row, which logs to look
at, which dashboards to check.

## Suggested action
What the operator should do, in order. Each step short. Cross-link to
other runbooks when the right move is "go run X first, then come
back."

## Why this can't auto-resolve (if applicable)
If `suggested_action: manual_only`, explain what human judgement is
required. Otherwise omit.

## When to escalate
The threshold past which this stops being a routine retry and
becomes an incident. Cross-link to the escalation rule that fires.

## Related runbooks
- …
