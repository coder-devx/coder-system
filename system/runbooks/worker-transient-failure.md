---
id: worker-transient-failure
title: Worker transient failure — diagnose and remediate
type: runbook
status: active
owner: ro
created: 2026-04-15
updated: 2026-04-15
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [anthropic]
---

# Worker transient failure

Operational guide for tasks that fail with
``failure_kind = "transient"``. The retry loop lives in
[task-orchestration](../product-specs/active/task-orchestration.md)
and the per-worker integrations in
[pm-worker](../designs/active/pm-worker.md),
[architect-worker](../designs/active/architect-worker.md),
[team-manager-worker](../designs/active/team-manager-worker.md), and
[worker-roles](../designs/active/worker-roles.md) (Developer +
Reviewer). Rationale in ADR
[0013](../adrs/0013-worker-level-transient-retry.md).

## When to run this

- A task appears in the admin panel with the yellow **Transient
  failure** panel.
- `worker_transient_retry.exhausted` events spike in the structured
  log feed.
- Multiple tasks across roles land with `failure_kind="transient"`
  within a short window — likely an Anthropic provider incident.

## Who can run this

Operator with admin JWT. If the incident is an Anthropic-side outage,
remediation is "wait and re-dispatch"; no code change needed.

## What the failure means

`failure_kind="transient"` is set only when the worker classified a
subprocess failure as transient **and** exhausted its retry budget.
The in-worker retry loop already tried the full budget with
exponential backoff. The task has **no side effects**: no knowledge
file, no commit, no `task_plans` row, no pipeline-chain trigger.

`failure_detail` holds:

```json
{
  "error_kind": "overloaded" | "rate_limited" | "timeout" | "connection_reset" | "dns" | "unknown",
  "attempts": 4,
  "delays_ms": [1423, 3781, 7234],
  "last_stderr": "truncated stderr (≤4 KB)"
}
```

`attempts` is always `budget + 1` (the original spawn plus the
retries). `delays_ms` has `budget` entries — the backoff sleeps
between attempts.

A task that **succeeded** after transient retries shows a yellow
chip "recovered after N transient retries" in the admin detail; the
retry history lives in `tasks.transient_retry_history`. No action
needed; the chip is informational.

## Triage

1. **Open the task in the admin panel** (`/tasks/{id}`). The yellow
   transient panel shows `error_kind`, `attempts`, `delays_ms`, and
   the truncated `last_stderr` inline.
2. **Check `error_kind`.** Classifies the upstream fault:
   - `overloaded` / `rate_limited` — Anthropic-side capacity issue.
     Check [Anthropic status](https://status.anthropic.com).
   - `timeout` — response body didn't complete within the CLI's
     per-request budget. Usually capacity; occasionally a very long
     tool-use trajectory.
   - `connection_reset` / `dns` — network-layer issue between Cloud
     Run and Anthropic; typically transient.
   - `unknown` — classifier saw a pattern it doesn't know about yet.
     **File a ticket** with the raw stderr so the taxonomy can be
     extended in the next classifier PR (`src/coder_core/workers/_transient.py`).
3. **Scope the incident.** Query the admin task list for
   `failure_kind=transient` in the last hour. One-off → retry the
   task (step below). Many across roles → likely provider incident;
   wait it out, re-dispatch in a batch once the provider recovers.
4. **Check `delays_ms`.** If the retries were fast (all under 2 s)
   and all failed the same way, budget was insufficient for the
   incident duration. Noted; budget tuning is a config change
   (`WORKER_TRANSIENT_RETRY_BUDGET`) not a runbook step.

## Remediation paths

### 1. Re-dispatch (single task, provider recovered)

First response when the task is isolated and the provider is healthy
again.

```sh
curl -X POST -H "Authorization: Bearer $ADMIN_JWT" \
  "$CORE_URL/v1/projects/$PROJECT_ID/tasks/$TASK_ID/override" \
  -d '{"action": "retry"}'
```

The re-dispatch starts the task fresh — a new subprocess, a fresh
transient-retry budget, a fresh schema-retry budget.

### 2. Wait and batch re-dispatch (provider incident)

When the admin list shows many `failure_kind=transient` within a
window, assume an Anthropic incident. Do NOT re-dispatch each task
— you'll pile onto an already-degraded provider.

- Confirm status.anthropic.com.
- Wait for "resolved".
- Batch-retry via admin ("Retry all failed" button, scoped to
  `failure_kind=transient`). If the button isn't available for the
  active scope, retry tasks one-by-one; there's no bulk SQL fallback
  authorized for this runbook.

### 3. Raise the retry budget (recurring under-retries)

If post-incident data shows the default budget of 3 is consistently
insufficient (provider incidents exceeding ~42 s of backoff), bump
the env var:

```
WORKER_TRANSIENT_RETRY_BUDGET=5
```

Apply in the Cloud Run env. Do not exceed 8 — the worker subprocess
deadline (architect 900 s, others 600 s) otherwise starts eating
into useful task time. Open an incident if the budget needs to go
higher — the signal is that the provider is degraded enough that
retrying inside a single task is the wrong shape of response.

### 4. Extend the classifier (`error_kind="unknown"`)

When `failure_detail.error_kind == "unknown"`, the subprocess failed
in a way the classifier substring table doesn't recognise.

- Copy the `last_stderr` snippet from `failure_detail`.
- Open a PR against `src/coder_core/workers/_transient.py` adding
  the substring to the transient table (or, if it's clearly a
  permanent failure, documenting why it should stay `unknown` →
  `permanent`-surfaced).
- Add a fixture to `tests/test_transient_classify.py` so future
  regressions are caught.

## Escalation

- Step 1 fails repeatedly → provider is still degraded or there's a
  real bug. Open an incident.
- Step 3 crosses 8 → file an incident; we are masking a systemic
  provider problem.
- `unknown` classifications exceed 10% of transient events in a
  week → the taxonomy is stale. Priority-level PR to extend it.

## Related

- Spec: [task-orchestration](../product-specs/active/task-orchestration.md)
  (retry capability lives in the orchestrator's Worker transient-failure
  retry section).
- Designs: [pm-worker](../designs/active/pm-worker.md),
  [architect-worker](../designs/active/architect-worker.md),
  [team-manager-worker](../designs/active/team-manager-worker.md),
  [worker-roles](../designs/active/worker-roles.md)
  (Developer + Reviewer),
  [worker-communication](../designs/active/worker-communication.md)
  (`tasks.transient_retry_history` column).
- ADR: [0013 — worker-level transient retry](../adrs/0013-worker-level-transient-retry.md)
- Adjacent: [worker-schema-failure](./worker-schema-failure.md) —
  content-level retry exhaustion (spec 0025, different `failure_kind`).
