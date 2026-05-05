---
id: "0065"
title: Reviewer scope cut + turn cap
type: spec
status: wip
owner: ro
created: 2026-05-05
updated: 2026-05-05
last_verified_at: 2026-05-05
served_by_designs: []
related_specs:
  - reviewer-worker
  - observability
parent: worker-roles
---

# Reviewer scope cut + turn cap

## Problem

The Reviewer worker today runs as an open-ended agentic loop: average
325 turns per review, max 729 over the last 7 days. It re-reads
unchanged source files, re-derives context the Developer already
established, and consumes 4-15M cache_read tokens per single review
to produce a verdict.

Quantitatively (from `tasks` + `task_turns`, 7-day window ending
2026-05-05):

- 18 reviewer tasks → **$137.94 in compute** (turn-level, true cost).
- 50% (9 of 18) died with `failure_kind=orchestrator_died` mid-loop —
  the longer the loop, the higher the chance of Cloud Run instance
  churn killing it. Lost ~$67 of that $137 to deaths alone.
- A single review of "cold-start scanner and batcher" consumed 17M
  cache_read + 446K output tokens over 576 turns. The corresponding
  Developer task that produced the diff used fewer turns.

The Reviewer is structurally a second Developer pass over the same
context, not a focused gate on the diff. Two consequences:

1. **Cost.** Per the data above, capping reviews at 30 turns with
   diff-only context would drop reviewer spend from $137.94 → $12.45
   over the same 7-day window — ~$18/day saved.
2. **Failure rate.** A 30-turn loop completes in ~20-60s; instance
   churn becomes a non-issue. Reviewer death rate would drop from 50%
   toward the dev-task baseline of ~11%.

## Users / personas

- **Project owners** waiting on PR reviews. Today a review takes
  2-12 min and has a 1-in-2 chance of dying and needing requeue.
  After: 30-60s, deterministic.
- **Operators** who manually retry dead reviewers via the orphan
  reaper today. After: significantly fewer rescues.
- **Developers** (the worker role) whose work currently gets gated
  by a reviewer that re-derives context and second-guesses design.
  After: a focused diff-level gate that catches regressions, schema
  drift, and missing tests — not a re-litigation of the design.

## Goals

- Reviewer task completes in ≤ 30 assistant turns for a typical PR.
- Reviewer prompt and context window contain only: the PR diff, the
  spec's acceptance criteria, the design's edge-cases section, and
  the test report.
- Reviewer cannot read source files outside the changed paths
  without explicit escalation.
- 7-day reviewer compute cost drops by ≥ 80% from the
  $137.94 / 7-day baseline measured 2026-05-05.
- Reviewer `orchestrator_died` rate drops to ≤ 15% (from 50%).

## Non-goals

- **Not** removing the Reviewer role. The gate is real and catches
  things the Developer self-test misses (regressions, schema drift,
  missing tests).
- **Not** changing what reviews block (the verdict shape stays
  `approved` / `request_changes` / `comment`).
- **Not** adding a "deep review" mode for cross-cutting changes —
  defer; current data shows the audit cycle catches those within
  hours anyway.
- **Not** tackling the underlying Cloud Run orphan-death issue
  (tracked separately — this spec mitigates exposure by cutting
  loop length, not by changing the dispatch infrastructure).

## Scope

In-scope:

- New `reviewer/tasks/review.md` task contract with diff-first
  framing and explicit "do not browse the repo" instruction.
- Dispatcher change to assemble the reviewer's user prompt as
  `{diff} + {spec ACs} + {design edge cases} + {CI report}`,
  pre-loaded — not as a "find the PR and review it" task.
- `--max-turns 30` hard cap on the Reviewer subprocess invocation.
- Tool allowlist for the Reviewer: read-only `gh api` for the
  changed paths only, no `Glob` / `Grep` of unchanged files.
- New `failure_kind=turn_cap_exceeded` surfaced when the cap
  triggers, with an admin-panel chip distinguishing it from
  `orchestrator_died`.
- Telemetry: per-review turn count, cache_read total, and a derived
  `expected_turns` field on the task row for trend analysis.

Out-of-scope:

- Architect / Developer / TM turn caps (separate spec — dev cap is
  more nuanced because some legitimate dev tasks need 200+ turns).
- Replacing Reviewer with a deterministic linter / static analyzer.

## Acceptance criteria

- [ ] AC1: Reviewer task contract in
      `system/roles/reviewer/tasks/review.md` rewritten to forbid
      browsing the repo and require operating only on pre-loaded
      diff + ACs + edge-cases + CI report.
- [ ] AC2: Dispatcher pre-loads the four blocks into the Reviewer
      user prompt before subprocess spawn (in
      `coder_core/workers/reviewer.py` and friends).
- [ ] AC3: Reviewer subprocess invoked with `--max-turns 30`.
- [ ] AC4: 7-day average reviewer turn count drops from 325 to
      ≤ 25, measured by SQL on `task_turns` aggregated by `task_id`
      with `tasks.role='reviewer'`.
- [ ] AC5: 7-day reviewer compute cost drops by ≥ 80% vs the
      $137.94 / 7-day baseline (turn-level cost from `task_turns`,
      Sonnet 4.x pricing). Tracked on the observability dashboard.
- [ ] AC6: Reviewer `orchestrator_died` rate drops to ≤ 15% over a
      7-day window post-rollout.
- [ ] AC7: A new `failure_kind=turn_cap_exceeded` value is added,
      written by the dispatcher when the cap triggers, and rendered
      in the admin panel as a distinct chip from `orchestrator_died`.
- [ ] AC8: Verdict-quality regression test — pick 10 reviews that
      `request_changes`'d under the old contract; the new contract
      must reach the same verdict on at least 8 (gut-check, not a
      formal eval). Documented in the rollout note.

## Metrics

- **Cost recovery.** Reviewer $/week, computed from `task_turns`,
  before/after. Target: ≥ 80% drop.
- **Reliability.** % of reviewer tasks ending in `succeeded` (not
  `orchestrator_died` or `turn_cap_exceeded`). Target: ≥ 80%.
- **Latency.** P50 / P95 of `(finished_at - started_at)` for
  reviewer tasks. Target: P95 ≤ 60s.
- **Verdict quality.** Manual spot-check of 10 reviews per week for
  the first 4 weeks; flag any that the old contract would have
  caught and the new one missed.

## Open questions

- What's the right escalation path when the cap is hit? Options:
  (a) auto-retry once with the cap raised to 60, (b) fail outright
  and let the human decide, (c) downgrade to "comment" verdict and
  let the PR proceed. Initial preference: (b) — turn-cap-exceeded
  is a signal that the reviewer prompt is too vague, not that the
  model needs more rope.
- Should the Reviewer get the test report from CI or run tests
  itself? Current data suggests Developer tasks already include a
  testing stage — the reviewer should consume its output rather
  than re-run.
- Does the same scope cut apply to ship-mode reviews (spec 0044)?
  Probably yes, but a ship review also touches the merges array;
  needs its own AC.

## Links

- Designs: TBD (architect to design after spec accept)
- Related specs:
  - [reviewer-worker](../active/reviewer-worker.md) — current
    reviewer role contract
  - [observability](../active/observability.md) — where the
    cost/latency dashboards live
- Related findings:
  - Cloud Run orphan dispatches (50% reviewer death rate cited
    here) — tracked in coder-system memory as the larger
    structural issue.
- Data source: `tasks` + `task_turns` in `coder-core-db`,
  7-day window ending 2026-05-05.
