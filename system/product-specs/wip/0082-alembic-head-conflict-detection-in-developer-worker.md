---
id: '0082'
title: Alembic head-conflict detection in the developer worker
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
- continuous-deployment
parent: pipeline-operations
---

# Alembic head-conflict detection in the developer worker

**Phase:** wip
**Progress:** 0 / 6 acceptance criteria

## Problem

Two developer workers running in parallel for the same `coder-core` release wave can both author Alembic migrations with the same revision id and the same `down_revision` parent, without seeing each other's commits. When both PRs merge to `main`, `alembic upgrade head` exits non-zero with **"Multiple head revisions are present"**, the CI deploy job fails at the migrate step, and traffic-shift never runs — so production silently freezes on the last revision while build/check keep going green and image artefacts keep landing in artifact registry.

This happened on 2026-05-10. PRs [coder-core#213](https://github.com/coder-devx/coder-core/pull/213) (the `now_items` migration) and [coder-core#214](https://github.com/coder-devx/coder-core/pull/214) (the `idea_queue_entries` migration) both authored alembic revision `0078` with `down_revision = "0077"` without rebasing. From #214's merge at 17:03 UTC on 2026-05-10 through 2026-05-12 16:50 UTC, **17 main-branch deploys failed silently at the migrate step**. The operator only discovered the issue on 2026-05-12 when flipping `STUDIO_ENABLED=true` via `gcloud run services update` + `update-traffic --to-latest` (bypassing the stuck CI path) put the latest image into prod for the first time since 5/10 — and the first `idea_scan` immediately threw `UndefinedTableError: relation "idea_queue_entries" does not exist` because four pending Studio migrations (0078×2, 0079, 0080) had never been applied.

This is a **silent failure** of the CI deploy contract. Build, check, and terraform all passed every time; the only failed step was inside the deploy job, behind a Slack notification nobody reads. Production drift accumulated invisibly. Phase B's autopilot story breaks if the only signal of a broken deploy is a manual operator-side spot check days later.

[coder-core#235](https://github.com/coder-devx/coder-core/pull/235) resolved the immediate symptom by renaming the second migration to revision 0081 chained after 0080. That fix is one-off; the gap that allowed two workers to author the same revision id is still open.

## Users / personas

- **The developer worker authoring a migration.** Needs to know at commit time that its chosen revision id will not collide with a peer worker's migration on `main`.
- **The operator running the orchestrator.** Needs to know that a parallel-dev-task release wave can't silently break the deploy pipeline.
- **The reviewer worker.** Needs a deterministic signal to reject a PR whose migration would produce a dual-head state on merge.

## Goals

- A developer worker that adds a new file under `migrations/versions/` runs `alembic heads` against the post-commit tree as part of its pre-commit gate and refuses to open a PR if the result is more than one head.
- The CI `check` job runs the same `alembic heads` invariant on every PR diff that touches `migrations/versions/` and fails the check if `>1`.
- When two workers in the same release wave both touch `migrations/versions/`, the second-merging PR's CI fails on its own diff (no rebase race) and the developer worker rebases and renumbers before retrying.
- Deploy-step migrate failures escalate visibly: a failed migrate step pages the on-call operator instead of just landing in Slack.

## Non-goals

- Forcing serialization of migration authorship. Two workers can still draft migrations in parallel; we just refuse to land two heads on `main`.
- Generic Alembic schema review (column types, index choices, FK shape). This spec only catches the dual-head structural failure.
- Backfilling the fix into older PRs. The one-off rename in #235 is sufficient for the historical drift.
- Changing the deploy job's failure-handling semantics (still fail-and-page); this spec adds an earlier detection point, not a recovery mechanism.

## Scope

Three surfaces:

1. **Developer-worker pre-commit gate** (`coder-core` `coder_core/workers/developer.py` and the worker subprocess prompt). After staging migration files, run `uv run alembic heads`. If the output contains more than one revision id, refuse to open the PR, log a structured `developer.migration_head_conflict_refusal` event, and surface the conflict to the operator via the existing `failure_kind` mechanism (new code: `migration_head_conflict`).

2. **CI `check` job invariant** (`coder-core` `.github/workflows/ci.yml`). When the PR diff touches `migrations/versions/`, add an explicit step that runs `uv run alembic heads | wc -l` and fails the job if the count is greater than one. This catches the case where a developer worker bypasses or pre-dates the worker-side gate, or where a human author missed it.

3. **Deploy-step paging** (`coder-core` `.github/workflows/ci.yml`). The `Run database migrations` step's failure path currently emits a Slack `deploy failed` notification. Add a second action that pages the on-call rotation (existing PagerDuty integration per spec `escalations`) with severity `high` when the migrate step specifically fails. Distinguishes migrate failures from generic deploy failures so the on-call operator knows to expect a stuck-prod situation, not a flaky test.

## Acceptance criteria

- **AC1.** Developer worker simulating two parallel migration authors against `0077` head — the second worker's pre-commit gate detects two `alembic heads` and refuses to open its PR. The task's `failure_kind` is `migration_head_conflict`, the task page shows the conflict, and the operator's existing override path (`skip_to_stage=accepted` or `action: retry` with rebase) remains usable.
- **AC2.** Developer worker authoring a migration off `main` runs `alembic heads` post-stage and observes exactly one head. The PR is opened normally. (Regression guard: single-migration case unchanged.)
- **AC3.** PR opened with a migration that introduces a second head fails the CI `check` job at the new `alembic-heads` step. The PR is non-mergeable until the migration is rebased or renumbered. (Catches the bypass case.)
- **AC4.** PR with no changes to `migrations/versions/` does not run the new step. (Performance guard: don't pay alembic init on every CI run.)
- **AC5.** Deploy-step migrate failure on `main` pages the on-call rotation via the existing escalation surface with a structured payload identifying the migrate-job execution name and the alembic error. The existing Slack notification still fires; paging is additive.
- **AC6.** Re-running the 2026-05-10 scenario (two PRs against `0077` head with the same revision id) end-to-end on a feature branch produces the AC1 and AC3 outcomes — the second PR cannot land. Verified via integration test, not live re-run.

## Open questions

- Should the developer-worker gate also detect a soft conflict — same revision id but different file? Today, two workers picking the same revision id but different file content would both think they're authoring `0078`; if one is `0078_a.py` and the other is `0078_b.py`, the gate catches it via the `wc -l > 1` check. Worth confirming this in AC1's test case to make sure the gate fires regardless of filename.
- The PagerDuty page payload — should it include a one-click "investigate" link to the latest migrate-job execution in Cloud Run, or just the run URL? Probably both.
- Should the worker pre-commit gate also block when a migration file is added without a corresponding `down_revision` update? Could flag the same family of structural breakage. Likely out of scope for this spec — separate concern, separate AC.

## Links

- [coder-core#235](https://github.com/coder-devx/coder-core/pull/235) — the one-off fix for the 2026-05-10 conflict (rename to 0081).
- Related operator memory entry: orchestrator-side gap #10 in the Phase A tracking note. Documents the 17-deploy silent-failure window and the discovery path.
- Cross-link to spec `escalations` (active) — this spec's deploy-paging addition lives on top of the existing escalation surface, not separate to it.
- Cross-link to spec `developer-worker` (active) — adds a pre-commit gate to that worker's commit path; needs an ADR if the gate framework grows beyond migrations.
