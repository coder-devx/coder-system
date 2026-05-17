---
id: post-pr-ci-fix-loop
title: Post-PR CI fix loop
type: design
status: active
owner: ro
created: '2026-04-27'
updated: '2026-05-17'
last_verified_at: '2026-05-17'
summary: Bounded CI-failure fix loop after Developer PRs land.
implements_specs: []
decided_by:
- '0017'
related_designs:
- managed-repo-action-distribution
- worker-roles
- worker-communication
- escalations
affects_services:
- coder-core
affects_repos:
- coder-core
- coder-system
parent: pipeline-operations
---

# Post-PR CI fix loop

## What it does today

When external GitHub CI completes with `failure | timed_out |
action_required` on a managed-repo PR, the
`check-run-ci-fixup.yml` workflow POSTs an HMAC-signed payload to
coder-core. The receiver routes it to `ci_watcher.handle_check_run`,
which dedupes on `(task_id, head_sha)`, increments per-task
`ci_fix_attempts`, dispatches a Developer fix-up task if attempts < 3
(pushes to the existing branch, no new PR), or opens an escalation if
the attempt budget is exhausted.

## Architecture

```mermaid
flowchart TB
  gh[(GitHub check_run:completed)] --> wf["check-run-ci-fixup.yml<br/>(in every managed repo)"]
  wf -->|HMAC-signed POST| recv["managed_repo_callbacks receiver"]
  recv -->|verify HMAC, flag, project| handler["ci_watcher.handle_check_run"]
  handler -->|conclusion ∈ failure/timeout/action_required| route{Route}
  route -->|success/cancelled/skipped| noop[no-op]
  route -->|select original task<br/>by branch_name| dedup{ci_fix_dedupes<br/>(task_id, head_sha) gate}
  dedup -->|first arrival| budget{attempts < 3?}
  dedup -->|duplicate| idem[200 deduped]
  budget -->|yes| disp["dispatch fix-up<br/>(push to same branch)"]
  budget -->|no| esc["open escalation<br/>(trigger=ci_fix_exhausted)"]
  disp --> audit[(audit_events)]
  esc --> audit
```

### Parts

- **`coder_core/workers/ci_watcher.py`** — `handle_check_run`; dedupes, tracks `ci_fix_attempts`, dispatches or escalates. Module-level `MAX_CI_FIX_ATTEMPTS = 3`. Registers itself at import via `register_handler("check-run-ci-fixup", …)`.
- **`coder_core/integrations/managed_repo_callbacks.py`** — receiver scaffold; HMAC verify → fleet-flag check → project resolution → registered handler.
- **`ci_fix_dedupes` table** — composite PK `(task_id, head_sha)`; transactional `INSERT … ON CONFLICT DO NOTHING` is the correctness barrier.
- **`tasks.ci_fix_attempts`** — counter, distinct from orchestrator's `fix_attempts`; capped at `MAX_CI_FIX_ATTEMPTS`.
- **`check-run-ci-fixup.yml`** — workflow installed in every managed repo via [managed-repo-action-distribution](./../knowledge/managed-repo-action-distribution.md); triggers on `check_run:completed`.

### Data flow

GitHub fires `check_run:completed` → workflow POSTs HMAC-signed
payload to the receiver. Receiver verifies signature, resolves the
project, gates on the fleet `ci_fix_loop_enabled` flag, and invokes
`handle_check_run`. Handler parses payload (head_sha, check name,
conclusion), routes by conclusion: triggering conclusions (failure /
timeout / action_required) proceed; success / cancelled / skipped
no-op. On trigger: select original task by `branch_name`, dedupe on
`(task_id, head_sha)`, check attempt budget → dispatch new Developer
fix-up OR open escalation. Audit row in both paths.

### Invariants

- **HMAC verified before any DB write** — receiver rejects unsigned / mismatched payloads.
- **One fix-up per `(task_id, head_sha)`** — `ci_fix_dedupes` PK is the gate; concurrent webhooks race atomically.
- **Same branch, same PR** — fix-up dispatches push to `task.branch_name`; `gh pr create` is forbidden in the fix-up prompt.
- **Attempt cap is per task, not per check** — `ci_fix_attempts` counts distinct SHAs, not individual failing checks on one SHA.
- **Escalation is terminal for the task** — once `ci_fix_attempts >= MAX_CI_FIX_ATTEMPTS`, further check_run events return cleanly without dispatch.
- **No bespoke notification surface** — exhaustion uses the existing 0041 escalation ladder; no Slack format owned here.

## Interfaces

| Surface | Effect |
|---|---|
| `check_run:completed` (GitHub webhook) | Workflow POSTs HMAC-signed payload on triggering conclusions |
| `POST /v1/managed-workflows/callbacks/check-run-ci-fixup` | Receiver entry; returns `{status: disabled \| no_op \| deduped \| escalated \| dispatched}` |
| `tasks.ci_fix_attempts` (column) | Per-task counter; cap `MAX_CI_FIX_ATTEMPTS=3` |
| `ci_fix_dedupes` (table) | PK `(task_id, head_sha)` gate |
| `escalation.trigger = ci_fix_exhausted` | Opens escalation per the 0041 ladder |
| `projects.ci_fix_loop_enabled` (column) | Per-project tri-state flag |

## Where in code

- `src/coder_core/workers/ci_watcher.py` — `handle_check_run` + `MAX_CI_FIX_ATTEMPTS` + import-time registration
- `src/coder_core/integrations/managed_repo_callbacks.py` — receiver + HMAC/flag/project resolution
- `src/coder_core/workers/_preflight.py` — Stage 0a pre-flight (re-prompt on hard failures before dispatch)
- `src/coder_core/domain/escalation.py` — `EscalationTrigger.CI_FIX_EXHAUSTED`
- `coder-system/template/.github/workflows/check-run-ci-fixup.yml` — workflow template
- `migrations/0054-ci-fix.sql` — `ci_fix_attempts` column, `ci_fix_dedupes` table, `ci_fix_loop_enabled`, widened `ck_escalations_trigger_kind`

## Evolution

Stage 0a (pre-flight) shipped in coder-core #36; Stage 1 (this design's
dispatch + exhaustion paths) in #55. Stage 0b (re-prompt on hard
failures) lives in spec 0025's `validate_and_retry`. Admin UI card
(Stage 2) is a follow-on.

## Links

- Spec: [0053-post-pr-ci-fix-loop](../../../product-specs/wip/0053-post-pr-ci-fix-loop.md)
- ADR: [0017](../../../adrs/0017-ci-fixup-one-per-sha.md) (one fix-up per failing SHA)
- Designs: [managed-repo-action-distribution](../knowledge/managed-repo-action-distribution.md), [worker-roles](../worker-roles.md), [worker-communication](./worker-communication.md), [escalations](./escalations.md)
- Repos: coder-core, coder-system
