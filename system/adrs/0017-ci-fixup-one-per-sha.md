---
id: "0017"
title: One CI fix-up dispatch per failing SHA, not one per failing check
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ["post-pr-ci-fix-loop"]
---

# ADR 0017 — One CI fix-up dispatch per failing SHA, not one per failing check

## Context

When a PR's HEAD SHA has N failing `check_run`s — e.g. `ruff-format`,
`ruff-lint`, and `mypy` all fail at once — the 0053 CI watcher receives N
`check_run.completed` webhook events with triggering conclusions. The
design must decide how many fix-up developer tasks to dispatch in
response.

The two natural options are:

1. **One fix-up per SHA** — aggregate all failing checks on the same SHA
   into a single fix-up task. The dedupe key is `(task_id, head_sha)`.
2. **One fix-up per failing check** — dispatch a separate fix-up task for
   each failing check, keyed on `(task_id, head_sha, check_name)`.

## Options considered

1. **One fix-up per SHA** (deduped on `(task_id, head_sha)`)
   - Pros:
     - Single developer task sees all failures; can address them in one
       coherent diff rather than N overlapping diffs.
     - No branch conflict: a single worker pushes one commit; N parallel
       workers on the same branch would race and produce merge conflicts or
       force-push each other's work.
     - Token cost is bounded at `MAX_CI_FIX_ATTEMPTS` per PR regardless of
       how many checks fail simultaneously.
     - Simpler DB schema: `ci_fix_dedupes(task_id, head_sha)` PRIMARY KEY
       gives the dedupe guarantee in one table, one constraint.
   - Cons:
     - The fix-up prompt lists only the first-arriving check's details
       (whichever webhook arrived first); later checks' excerpts are not
       aggregated unless the handler collects them. Mitigated by truncating
       `output.summary` and `output.text` for the first check and noting
       in the prompt that additional checks may also be failing — the
       worker can inspect the PR's check status directly.
     - A check that is hard to fix (e.g. a mypy error requiring a semantic
       change) blocks retry budget for all checks on that SHA.

2. **One fix-up per failing check** (keyed on `(task_id, head_sha, check_name)`)
   - Pros:
     - Each fix-up task gets a tightly scoped prompt (one check, one
       excerpt).
     - Checks that auto-fix quickly (format) don't share retry budget with
       hard semantic checks (mypy).
   - Cons:
     - N parallel workers push to the same branch. The second push will
       non-fast-forward fail unless each worker does a pull-rebase first.
       The developer worker's completion contract does not currently
       include `git pull --rebase`; adding it risks introducing conflicts.
     - `ci_fix_attempts` semantics become ambiguous: is it attempts per
       check or attempts across all checks for the task?
     - Token and Cloud Run slot cost scales with N failing checks rather
       than being bounded.
     - Complexity: the dedupe table needs a `check_name` dimension; the
       exhaustion logic needs to aggregate across checks rather than
       counting total dispatches.

3. **One fix-up per SHA, but with aggregated failure list in the prompt**
   — a variant of option 1 where the handler collects all check_run
   conclusions for the SHA (via the GitHub API or by buffering webhook
   events) before dispatching.
   - Adds latency (need to wait for all checks to complete before
     dispatching) and requires a secondary GitHub API call, which
     complicates the otherwise stateless handler path.
   - Deferred to a future iteration once the basic loop is stable.

## Decision

**Option 1: one fix-up dispatch per `(task_id, head_sha)` pair.**

The dedupe gate in `ci_fix_dedupes` uses `PRIMARY KEY (task_id, head_sha)`.
The first webhook to arrive for a given SHA wins and triggers the dispatch;
subsequent arrivals for the same SHA are no-ops.

## Rationale

Branch conflict avoidance is the deciding factor. N parallel workers on
the same branch require coordinated `git pull --rebase` logic that the
current developer worker does not have and that would be complex to
introduce safely. A single worker addressing all visible failures in one
pass is simpler, cheaper, and avoids the race condition entirely.

The single-prompt limitation (only one check's excerpt surfaces) is
acceptable at v1 because the worker can call `gh pr checks` or browse
the PR's Actions tab to see the full failure list. The prompt note
("additional checks may also be failing") keeps the worker from thinking
the listed check is the only problem.

## Consequences

- **Positive:** Simple dedupe schema; no branch-conflict risk; bounded
  token cost; `ci_fix_attempts` has an unambiguous meaning (one
  increment per SHA transition).
- **Negative:** When three checks fail simultaneously, the fix-up prompt
  shows only one check's excerpt. The worker must discover the others
  independently.
- **Follow-ups:** Option 3 (aggregated multi-check prompt via a brief
  wait + GitHub API call) can replace option 1 once the basic loop is
  proven stable. The dedupe key is backward-compatible — aggregation
  is an internal change to `handle_check_run` that doesn't affect the
  table schema.
