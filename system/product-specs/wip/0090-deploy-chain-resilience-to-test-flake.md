---
id: '0090'
title: Deploy chain must not be hostage to a single flaky test
type: spec
status: wip
owner: ro
created: '2026-05-13'
updated: '2026-05-13'
last_verified_at: '2026-05-13'
deprecated_at: null
reason: null
served_by_designs: []
related_specs:
- continuous-deployment
- self-healing
parent: pipeline-operations
---

# Deploy chain must not be hostage to a single flaky test

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

On 2026-05-13 around 04:00 UTC, four pre-existing flaky tests on `coder-core` (all `caplog`-record assertions failing only under the full pytest suite, passing in isolation) blocked the `check` job. Because `build` and `deploy` jobs `needs: check`, both were `skipped` — which means **no image was built, no migrate job ran, no traffic shifted**. The operator's prod-recovery hotfix ([coder-core#251](https://github.com/coder-devx/coder-core/pull/251)) merged correctly but its main-branch deploy never executed. Prod sat wedged for another ~30 minutes while the operator skipped the 4 tests manually via [coder-core#252](https://github.com/coder-devx/coder-core/pull/252).

This pattern compounds under Phase B's autopilot:

1. **Single point of failure.** Any test that becomes deterministically flaky in the full suite blocks every subsequent deploy. The deploy chain has no "redeploy without check" lever for the operator.
2. **Recovery requires code change.** The only way out is to land a code-level skip/xfail/fix and re-trigger the workflow. For an operator dealing with a prod-wedge incident, that's a 10-minute hands-on cycle minimum, and it requires the original CI to be unblocked at that exact moment.
3. **Cascades amplify.** When the deploy chain is already broken (e.g., from a migration wedge — see [spec 0085](https://github.com/coder-devx/coder-system/blob/main/system/product-specs/wip/0085-adr-id-allocation-race-under-concurrent-dispatch.md), [spec 0088](https://github.com/coder-devx/coder-system/blob/main/system/product-specs/wip/0088-worker-prod-creds-isolation.md)), the test-flake gate turns a one-step recovery into a two-step recovery: fix migrations, then fix flake, then redeploy.
4. **Operator hack debt.** The 2026-05-13 recovery skipped 4 real tests with `pytest.mark.skip`. Those tests now silently don't run. The original assertions they verified are no longer guarded. Phase B's autopilot inherits the gap.

## Users / personas

- **Operators recovering from a production wedge.** Today the deploy chain blocks them at the test gate even when the test failure is unrelated to the wedge. Recovery cycles compound.
- **The reviewer worker.** Currently cannot triage "is this flake or a real failure" without manual operator inspection. Phase B needs a deterministic signal.
- **Phase B autopilot.** Depends on the deploy chain being able to ship code even when a non-deploy-critical test is flaking.

## Goals

- The operator has a documented, runbook-driven path to **redeploy without re-running the `check` job**, valid for the recovery-incident class.
- The CI pipeline distinguishes between "deploy-critical failure" (build, terraform, migration smoke-test) and "general test failure" (the broader pytest suite). The first hard-blocks deploy; the second emits a warning but allows the deploy with a structured approval.
- Skipped or xfailed tests are tracked in a registry the operator can inspect, so the "operator hack debt" doesn't pile up invisibly. Each skip carries a forced-expiry date.
- Phase B autopilot includes a self-heal pattern: when a `check` job fails N consecutive times on `main` with the same test-failure signature, automatically tag the failing tests as `flake` and surface to the operator with a structured remediation TODO.

## Non-goals

- Removing the `check` job entirely or making it optional for every PR. The default-PR path stays unchanged; this spec adds an **operator-recovery lever**, not a general bypass.
- Auto-skipping flaky tests in CI silently. Skips are operator-explicit, dated, and tracked.
- Replacing pytest with a different test runner.
- Diagnosing the specific 2026-05-13 caplog flake. That's [spec 0091](system/product-specs/wip/0091-conftest-log-pollution-root-cause.md).

## Scope

Three surfaces:

1. **CI workflow** (`coder-core/.github/workflows/ci.yml`). Split the existing `check` job into `check-deploy-critical` (the deploy-blocking subset — build, terraform, migration smoke-test, isolation manifest, capability matrix) and `check-full-suite` (the broader pytest run). `deploy` now `needs: check-deploy-critical` only. `check-full-suite` runs in parallel and emits its result to a separate status surface.

2. **Operator-recovery runbook** (`coder-system/system/runbooks/redeploy-bypassing-test-suite.md`). Step-by-step for the recovery class: re-trigger the `deploy` job alone via `gh workflow run`, attach an explicit "bypass reason" comment to the resulting deploy event, fire an audit event. Discourages routine use; documents the safe-use path.

3. **Skip registry** (`coder-core/tests/SKIPPED.yml`). Every `pytest.mark.skip` / `pytest.mark.xfail(strict=False)` in the suite must be registered in this file with `test_id`, `reason`, `skip_date`, `expiry_date` (default +30 days), `owner`. A CI check fails if a skipped test isn't in the registry or its expiry has passed.

## Acceptance criteria

- **AC1.** `check-deploy-critical` job exists and passes on a known-good main commit. It runs in <2 minutes. Includes: terraform validate, isolation-manifest drift check, capability-matrix drift check, alembic-heads single-head check, smoke test (the migration round-trip + a single API endpoint). Excludes the rest of the pytest suite.
- **AC2.** `check-full-suite` runs the broader pytest suite as today. Failures emit a GitHub Check status on the PR but do NOT block `deploy`.
- **AC3.** The runbook `redeploy-bypassing-test-suite.md` exists with operator-followable steps. Re-triggering the deploy via the runbook for the recovery scenario writes an audit event `deploy.bypass_test_suite` with operator + bypass-reason.
- **AC4.** Skip registry (`tests/SKIPPED.yml`) is enforced. A new `pytest.mark.skip` without a corresponding entry fails the `check-deploy-critical` job. An entry whose `expiry_date` has passed fails the check, forcing the operator to either re-enable the test or extend the expiry.
- **AC5.** Self-heal pattern: when `check-full-suite` fails the same test 3 consecutive times on `main`, the orchestrator opens an issue tagged `flake` with the test path, recent failure outputs, and a 7-day TODO. The issue auto-closes when the test passes 5 consecutive runs.

## Open questions

- The `check-deploy-critical` subset — what counts as deploy-critical? Memory's recovery muscle memory suggests: terraform, isolation manifest, alembic single-head, capability matrix. Are there more? Recommend operator-driven inventory in design phase.
- Should the registry's default expiry be 30 days, 14 days, or something shorter? 30 days matches the operator's calibration window; <30 risks expiry-thrash. 30 it is unless design says otherwise.
- The self-heal pattern (AC5) — open issue or insert a Now item? The Now-item path matches existing self-heal infrastructure; the issue path is more standard for engineering teams. Operator's call.
- The 4 currently-skipped tests from 2026-05-13's recovery should land in the registry on day one with `expiry_date: 2026-06-13`. Forces a real fix within a month.

## Links

- [coder-core#251](https://github.com/coder-devx/coder-core/pull/251) — the prod-recovery hotfix whose deploy chain got blocked by the flake.
- [coder-core#252](https://github.com/coder-devx/coder-core/pull/252) — the test-skip hotfix that unblocked the deploy chain.
- Related: [spec 0091](system/product-specs/wip/0091-conftest-log-pollution-root-cause.md) — the actual root-cause fix for the 4 skipped tests. Pairs with this spec.
- Related: `continuous-deployment` (active) — extends its job-graph semantics. Needs an ADR if the deploy-critical / full-suite split grows beyond a single workflow.
- Related: `self-healing` (active) — adds the flake-detection pattern as a new self-heal mode.
