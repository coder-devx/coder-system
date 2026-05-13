---
id: '0091'
title: Diagnose and fix the caplog inter-test pollution affecting 4 tests
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
- developer-worker
parent: pipeline-operations
---

# Diagnose and fix the caplog inter-test pollution affecting 4 tests

**Phase:** wip
**Progress:** 0 / 4 acceptance criteria

## Problem

Four pytest tests on `coder-core` exhibit deterministic flake: they pass when run in isolation (or on their own file alone) but fail when run as part of the full suite. The failure mode is identical across all four: a `caplog` assertion of the form `assert any(... for r in caplog.records)` or `assert len(records) == N` evaluates against an empty `caplog.records` even though the application code clearly emits the expected log line (verified by adding a `print()` shim and observing it in stdout).

The four tests:

1. `tests/test_auto_approve_api.py::test_plan_create_shadow_mode_logs_but_writes_no_row` — asserts a "shadow plan" log record is present.
2. `tests/test_broker.py::test_local_broker_issue_records_audit_log` — asserts the `broker_issued` audit log fires on `LocalBroker.issue()`.
3. `tests/test_workers.py::test_parse_review_verdict_heuristic_fires_warning` — asserts a `WARNING` log when the heuristic fallback parses an ambiguous review verdict.
4. `tests/workers/test_dispatcher_preloads.py::test_preload_index_skips_on_404_and_logs` — asserts an `INFO` log when the dispatcher preload step skips on a 404.

[coder-core#252](https://github.com/coder-devx/coder-core/pull/252) skipped all four with `pytest.mark.skip` to unblock the prod-recovery deploy chain on 2026-05-13. That's a hack; the original assertions they verify are no longer guarded. This spec is the real fix.

## Investigations done so far (in the recovery push)

1. **All four pass in isolation.** Running each test alone, or running its parent file alone, passes. Confirmed locally.
2. **All four fail under the full suite locally and in CI** (consistent across environments). The failure isn't CI-specific.
3. **No `logging.disable()`, `propagate = False`, or `removeHandler` calls** appear in any test or non-observability source file (grep clean).
4. **`coder_core.observability.configure_logging()`** is invoked by `create_app()` and sets root logger level to INFO + installs a JsonFormatter handler with a `ProjectIdFilter`. The handler has a sentinel attribute so re-invoking is idempotent.
5. **An autouse fixture restoring `propagate=True` on every `coder_core.*` logger** before each test (landed in #252's conftest change) does NOT fix the flake. So propagation isn't the leak path.
6. **No `pytest-xdist` in use.** Tests run serial in a single process — pollution is intra-process state mutation, not worker isolation.

## Hypotheses worth testing

- **`caplog.LogCaptureHandler` removed by `configure_logging`.** Even though configure_logging's sentinel check should skip the caplog handler, there might be a code path that uses a different remove mechanism. Worth bisecting.
- **`logging.root.handlers` mutated mid-suite.** Some test installs a custom handler that swallows records without re-raising. Bisect by inserting a `logging.root.handlers` snapshot at the start of each failing test.
- **`logging.Logger.manager.disable` is set non-zero.** A test calls `logging.disable(WARNING)` somewhere and doesn't reset. Easy to detect.
- **`pytest_caplog` plugin disabled or replaced.** Some conftest fixture loads a plugin that overrides caplog. Less likely but worth a `pytest --trace-config` confirmation.
- **`structlog` configuration installed by `coder_core.observability` interferes with stdlib `caplog`.** If structlog wraps loggers in a way that bypasses propagation to caplog's handler.

## Goals

- Identify the **specific polluting test** (or fixture) that causes the 4 tests to fail under full-suite run.
- Restore the 4 tests with the root cause fixed — un-skip them in the suite. Their original assertions guard real behavior that should not regress silently.
- Add a regression test that exercises the previously-polluting state path in isolation, asserting caplog continues to work even after that state mutation.
- Document the failure mode in the test-harness troubleshooting docs so future occurrences are diagnosed in minutes, not hours.

## Non-goals

- Migrating to `pytest-rerunfailures` or `pytest-flake-finder` as a workaround. Those are escape hatches; this spec finds and fixes the actual leak.
- Rewriting the affected tests to use a different assertion pattern (e.g., reading stdout instead of `caplog`). The assertion pattern is correct; the harness is broken.
- Splitting the test suite by directory (running `tests/test_broker.py` separately). Adds CI complexity without fixing the leak.

## Scope

Three surfaces:

1. **Bisect script** (`coder-core/scripts/bisect_caplog_flake.py`). pytest harness that:
   - Runs the suite up to but not including one of the 4 failing tests
   - Snapshots `logging.root.handlers`, `logging.Logger.manager.disable`, and the per-logger `propagate` flag
   - Runs the failing test
   - Diffs against a known-good (early-suite) snapshot
   - Reports the change-deltas that occurred between the snapshots
   - Bisects by halving the pre-failing-test set until the polluter is isolated to a single test or fixture

2. **Root-cause fix.** Once the polluter is identified, either:
   - **Source fix**: change the polluter to clean up after itself (autouse fixture that restores state on teardown). Preferred path; localizes the fix.
   - **Conftest fix**: an autouse fixture in `tests/conftest.py` that snapshots logging state at session start and restores it before every test. Higher-overhead but works for unknown future leaks.

3. **Regression test** (`coder-core/tests/test_caplog_harness.py`). New test that reproduces the polluting state mutation in isolation and asserts `caplog.records` still functions across that mutation. Acts as a tripwire if the leak re-introduces.

After the fix lands, remove the four `pytest.mark.skip` markers from #252 and verify the tests pass under the full suite. Also remove the autouse `_reset_coder_core_log_propagation` fixture if it proves unnecessary.

## Acceptance criteria

- **AC1.** `scripts/bisect_caplog_flake.py` runs against current `main`, identifies a single test or fixture as the polluter, and prints a diff of the logging-state changes that test/fixture causes. The report includes file path, test name, and the specific state mutation.
- **AC2.** The root-cause fix lands and is verified by running the full suite locally: `uv run pytest tests/` returns zero failures with all 4 previously-skipped tests un-skipped.
- **AC3.** `tests/test_caplog_harness.py` exists and reproduces the previously-polluting state mutation in isolation, asserting `caplog.records` continues to capture log records correctly across the mutation. The test passes; if the leak ever re-introduces, this test fails first.
- **AC4.** The four `pytest.mark.skip` markers from [coder-core#252](https://github.com/coder-devx/coder-core/pull/252) are removed. The corresponding entries in `tests/SKIPPED.yml` (from [spec 0090](https://github.com/coder-devx/coder-system/pull/125)) are deleted. CI's full pytest run is green.

## Open questions

- Should the bisect script be permanent infrastructure or a one-off recovery tool? Permanent has long-tail value (future caplog leaks find it useful); one-off keeps the repo lean. Lean permanent — pin under `scripts/`.
- The fix might require modifying a third-party library's logger setup (e.g., `httpx`, `uvicorn`, `sqlalchemy`). If so, document the workaround and consider upstreaming.
- The autouse `_reset_coder_core_log_propagation` fixture from #252 is harmless but adds a per-test overhead. Once the real fix lands, decide whether to remove it (preferred) or keep as defense-in-depth.

## Links

- [coder-core#252](https://github.com/coder-devx/coder-core/pull/252) — the test-skip hotfix this spec replaces.
- [spec 0090](system/product-specs/wip/0090-deploy-chain-resilience-to-test-flake.md) — the CI-resilience spec that handles "deploy must not be hostage to test flake" at the workflow level. This spec handles "fix the underlying flake" at the test-harness level.
- The 2026-05-13 prod-recovery timeline: a single migration wedge + four flaky tests combined to keep prod down for ~9 hours. Both contributing factors are addressed by 0090 + this spec together.
