---
id: test-harness-reliability
title: Test harness reliability
type: spec
status: active
owner: ro
created: 2026-05-14
updated: 2026-05-14
last_verified_at: 2026-05-14
summary: Caplog pollution diagnosis tooling and regression guards for the coder-core test suite.
served_by_designs: []
related_specs: [continuous-deployment, tenant-isolation]
parent: delivery-and-infra
---

# Test harness reliability

## What it is

Infrastructure and guards that keep the `coder-core` pytest suite
deterministic — specifically, tooling to diagnose and permanently fix
intra-process logging-state pollution that causes `caplog` assertions
to flake under full-suite runs even when the same tests pass in
isolation.

The component ships three permanent artifacts:

1. **Bisect script** (`coder-core/scripts/bisect_caplog_flake.py`) —
   a pytest harness that snapshots `logging.root.handlers`,
   `logging.Logger.manager.disable`, and per-logger `propagate` flags
   before and after each test in a pre-failing sequence, diffs the
   snapshots, and bisects the pre-failing test set by halving until the
   single polluting test or fixture is identified. Output is a structured
   report naming the file, test name, and specific state mutation.

2. **Root-cause fix** — the identified polluter cleaned up after itself
   (preferred: autouse fixture restoring logging state on teardown;
   fallback: `tests/conftest.py` snapshot-and-restore). The four
   previously-skipped tests (`test_plan_create_shadow_mode_logs_but_writes_no_row`,
   `test_local_broker_issue_records_audit_log`,
   `test_parse_review_verdict_heuristic_fires_warning`,
   `test_preload_index_skips_on_404_and_logs`) are un-skipped and pass
   under the full suite.

3. **Regression tripwire** (`coder-core/tests/test_caplog_harness.py`)
   — a standalone test that reproduces the polluting state mutation in
   isolation and asserts `caplog.records` continues to capture log
   records correctly across that mutation. If the leak re-introduces,
   this test fails first.

## Capabilities

- `scripts/bisect_caplog_flake.py` runs against any branch, identifies
  the polluting test or fixture within one bisect pass, and emits a diff
  of the logging-state changes (file path, test name, specific
  mutation).
- Full pytest suite (`uv run pytest tests/`) passes with zero failures
  and no `pytest.mark.skip` on the four previously-flaky caplog tests.
- `tests/test_caplog_harness.py` passes green and acts as a canary —
  caplog pollution re-introductions fail this test before they surface
  as flaky full-suite runs.
- `tests/SKIPPED.yml` entries for the four tests (added by the
  spec-0090 CI-resilience mechanism) are removed once the real fix is
  confirmed green.

## Interfaces

- **Script:** `coder-core/scripts/bisect_caplog_flake.py` —
  `uv run python scripts/bisect_caplog_flake.py --failing-test
  <test_id>` invocation; self-contained, no extra deps beyond the
  existing test virtualenv.
- **Regression test:** `coder-core/tests/test_caplog_harness.py` —
  part of the standard `uv run pytest tests/` run; no separate
  invocation needed.
- **Conftest guard (if used):** `tests/conftest.py` autouse fixture
  restoring `logging.root.handlers`, `logging.Logger.manager.disable`,
  and per-logger `propagate` flags before each test.
- **SKIPPED.yml:** entries for the four tests deleted after fix
  verification (spec-0090 mechanism cleans up automatically on
  deletion).

## Dependencies

- `coder-core` pytest harness (`pytest`, `pytest-asyncio`).
- `coder_core.observability.configure_logging()` — the handler-install
  path; fix must remain compatible with its sentinel-based idempotence
  check.
- Spec 0090 (`deploy-chain-resilience-to-test-flake`) — introduced
  `tests/SKIPPED.yml` as a temporary resilience mechanism; this
  component removes the four entries once the real fix is verified.

## Troubleshooting

**Symptom:** `caplog.records` is empty for a test that passes in
isolation.  
**First step:** `uv run python scripts/bisect_caplog_flake.py
--failing-test <test_id>` — identifies which earlier test mutates
logging state.  
**Most likely causes:**
- `logging.disable(level)` called without a matching
  `logging.disable(logging.NOTSET)` reset.
- A handler installed on `logging.root` that swallows records (e.g.,
  `NullHandler`, a handler with a filter that drops the target logger
  name).
- `propagate = False` set on a logger whose hierarchy sits above the
  caplog handler's attachment point.
- A structlog or third-party library configuring the stdlib root logger
  during its own test setup without teardown.

## Evolution

- **0091** (2026-05-14) — Component shipped. Bisect script, root-cause
  fix (logging-state leak isolated and patched), regression tripwire in
  `tests/test_caplog_harness.py`, four tests un-skipped, `SKIPPED.yml`
  entries removed. Originated from the 2026-05-13 prod-recovery
  incident where four flaky caplog tests combined with a migration wedge
  kept prod down ~9 hours; [coder-core#252](https://github.com/coder-devx/coder-core/pull/252)
  was the test-skip hotfix this component replaces.

## Links

- Related components: [continuous-deployment](./continuous-deployment.md),
  [tenant-isolation](./tenant-isolation.md)
- Incident context: [coder-core#252](https://github.com/coder-devx/coder-core/pull/252)
