---
id: '0087'
title: Lint pre-flight as a hard worker gate before PR open
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

# Lint pre-flight as a hard worker gate before PR open

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

The developer worker runs a pre-flight lint pass (`ruff format`, `ruff check --fix`) before committing. If the pre-flight reports surviving failures, the worker today **logs them as a PR comment and commits anyway**. CI's `check` job then catches the same failures and fails the PR. The operator has to manually patch (typically a one-line import-sort fix) and push.

Memory's gap #5 documents the pattern: "Worker reports 'Pre-flight surviving failures: ruff format (exit 2); ruff check --fix (exit 2)' as a PR comment but commits anyway. CI's check job then fails. Pattern: worker adds a new `domain/__init__.py` import without re-sorting → I001 violation. Cheap manual fix every time, but should be a hard gate in the worker's commit path."

Every Phase A push hit this several times. The pattern is consistent: the worker's pre-flight successfully detects the lint failure (the comment proves it), the worker just doesn't act on the signal. Phase B's autopilot multiplies the volume — every failed pre-flight burns a CI cycle and an operator manual-patch.

The fix is intentionally narrow: convert the pre-flight surviving-failure log line into a hard gate. The worker re-runs the auto-fix (`ruff format` + `ruff check --fix`); if surviving failures remain, the worker spends one more iteration on the lint (the existing fix-loop already handles this for test failures) before opening the PR. If the lint still fails after that, surface as `failure_kind=lint_preflight_failed` and let the operator decide whether to re-dispatch or hand-fix.

## Users / personas

- **Operators waiting on PRs to go green.** Today they pay a CI roundtrip (~5-10 minutes) plus a manual patch for every worker-introduced lint failure. Bounded but cumulative cost.
- **The developer worker.** Spends a slot producing work that's immediately rejected at the next stage. Net throughput would improve if the worker fixed lint internally rather than relying on CI to catch it.
- **The CI pipeline.** Carries lint-failure builds that the worker could have prevented. Cheap to fix at source.

## Goals

- The developer worker's pre-flight lint pass becomes a hard gate: surviving failures block PR-open until the worker has tried at least one fix-loop iteration.
- The fix-loop iteration runs the worker's existing remediation surface (re-prompt with the lint errors as context) and re-runs lint. Bounded retries — one attempt by default, two on the fix-loop budget.
- If lint still fails after the worker's fix-loop exhausts, the task surfaces `failure_kind=lint_preflight_failed` with the surviving lint output. Operator can override (`skip_to_stage=executing` to retry) or hand-patch.
- The existing PR-comment surface stays (operator can see what the lint was complaining about), but the comment is now a record of what was fixed, not a notice of an unfixed failure.

## Non-goals

- Changing the lint configuration (ruff rules, mypy strictness). The fix is in the worker's reaction to lint, not in the rules.
- Adding a CI-side gate. The check job already gates merge; this spec just shifts catch-time leftward.
- Expanding the gate beyond lint (e.g., to mypy or pytest). Those have different signal characteristics and belong in separate specs.
- Removing the existing pre-flight pass for non-developer workers (PM, architect, reviewer). Their lint surface is different and out of scope here.

## Scope

One surface, narrow change:

**Developer-worker commit path** (`coder-core` `coder_core/workers/developer.py` — the pre-commit / pre-PR section after the existing pre-flight ruff calls). Today, after `ruff format` and `ruff check --fix` complete, the worker logs surviving failures and proceeds to PR-open. Replace that proceed-anyway path with:

1. If the second-pass exit codes are zero, proceed (today's clean path).
2. If non-zero, run one fix-loop iteration: re-prompt with the lint errors injected into the worker's context, re-stage files, re-run pre-flight. If now zero, proceed.
3. If still non-zero after the fix-loop iteration, exit with `failure_kind=lint_preflight_failed`. Populate `failure_detail` with the surviving lint output (truncated to ~2KB for the failure_detail column). No PR opened. Worker run terminates.

Fix-loop iteration count is bounded by the existing `developer.fix_attempts` budget (today 150 turns post-#211). Lint fix is typically a 1-2 turn task, so it stays well inside budget.

## Acceptance criteria

- **AC1.** Developer worker adds a new `domain/__init__.py` import without re-sorting. Pre-flight first-pass `ruff check --fix` reports `I001` surviving. The fix-loop iteration re-prompts with the lint output; the worker rewrites with imports sorted; pre-flight second-pass is clean. PR is opened with the fix included. No PR comment about surviving failures.
- **AC2.** Developer worker introduces a lint failure that the fix-loop can't resolve in one attempt (e.g., a complex rule the worker keeps getting wrong). After the fix-loop iteration the lint is still failing. Task exits with `failure_kind=lint_preflight_failed`, `failure_detail` populated with the surviving output, no PR opened. Pipeline list shows the chip.
- **AC3.** Operator-side recovery for AC2 case: `POST /v1/projects/{id}/tasks/{task_id}/override` with `{"action": "retry"}` re-runs the worker with the lint context preserved. If the worker fixes it on the retry, AC1 path proceeds.
- **AC4.** Developer worker writes code that's clean on first pre-flight. The fix-loop iteration does not run. PR opens normally. (Regression guard for the clean path.)
- **AC5.** The fix-loop iteration uses the existing `developer.fix_attempts` budget. With a 150-turn budget per #211, a typical lint fix consumes 1-2 turns; the budget visibly drops in the task's turn counter. If a lint-fix loop somehow burns >10 turns, surface `failure_kind=lint_preflight_failed` early (budget guard).

## Open questions

- The `failure_detail` truncation budget (~2KB) — is that enough for the typical ruff output, or does the long-form output of `ruff check --no-fix` overflow? Sample a few real cases; if 2KB feels tight, bump to 4KB.
- Should the fix-loop iteration also try `ruff check --fix --unsafe-fixes` if the safe-fix pass didn't resolve? Risk: unsafe fixes can change semantics. Lean conservative: stick to safe fixes by default; operator override path remains for the residual cases.
- Should the same gate apply to mypy errors? Memory mentions "mypy `dict`/`Task` missing type args, mypy `Optional` reassignment after `assert`" as common failure modes. The signal characteristic (deterministic, fixable in 1-2 turns) is similar, but mypy errors are often architectural rather than mechanical. Recommend deferring to a separate spec to scope properly.

## Links

- Related operator memory: orchestrator-side gap #5 in the Phase A tracking note. Documents the recurrence and the `domain/__init__.py` I001 example.
- Related: PR [coder-core#211](https://github.com/coder-devx/coder-core/pull/211) bumped the developer turn cap to 150 and added the `turn_cap_exceeded` failure_kind tag. This spec adds a sibling tag for lint.
- Related spec: `developer-worker` (active) — extends the worker's commit-path gate semantics.
