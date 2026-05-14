---
id: redeploy-bypassing-test-suite
title: Redeploy bypassing the full test suite
type: runbook
status: active
owner: ro
created: 2026-05-14
updated: 2026-05-14
last_verified_at: 2026-05-14
applies_to_services: [coder-core]
applies_to_integrations: [github]
---

# Redeploy bypassing the full test suite

## When to run this

Use this runbook **only** when both of the following are true:

1. `check-deploy-critical` passed on the target SHA (the fast job that
   gates deploy safety — compilation, migrations, smoke tests).
2. `check-full-suite` is red (the slow job covering the wider regression
   surface — flaky tests, slow integration tests, etc.).

This lever exists for the **production-wedge recovery class**: a known-
good deploy is blocked solely by an unrelated or flaky full-suite failure,
and waiting for a fix or re-run would extend an active incident.

> **Stop if `check-deploy-critical` is also failing.** That job covers the
> invariants that protect production. A red `check-deploy-critical` means
> the change is not safe to ship. Fix the real issue first — this runbook
> does not help you in that case.

**Do not use this runbook for routine bypasses.** If `check-full-suite` is
red on a non-incident push, fix the tests before merging. Using this lever
to ship code that fails real tests degrades the signal quality for
everyone. Every use is audited; unexplained bypass events will be reviewed.

## Who can run this

An operator with `gh` CLI write access to `coder-devx/coder-core`.

## Prerequisites

- [ ] Confirm the target SHA's `check-deploy-critical` job is **green** on
      GitHub Actions. Navigate to the Actions tab of `coder-devx/coder-core`
      and verify the job status for the relevant commit.
- [ ] Identify the incident or bypass reason. This is **required** for the
      audit trail — the `bypass_reason` field is stored as an audit event and
      is searchable in the admin panel. A one-sentence description is
      sufficient (e.g. `"Incident INC-4821: full-suite flaky on unrelated
      network mock, deploy-critical green, prod wedged"`).
- [ ] Verify that `gh` CLI is authenticated with write access to
      `coder-devx/coder-core`:
      ```sh
      gh auth status
      gh repo view coder-devx/coder-core
      ```

## Steps

1. **Trigger the bypass workflow** — this re-triggers `ci.yml` on the
   current `main` HEAD. `check-deploy-critical` runs again (must still
   pass); the `deploy` job runs with `bypass_reason` set, and the audit
   event `deploy.bypass_test_suite` is written.

   ```sh
   gh workflow run ci.yml \
     -R coder-devx/coder-core \
     -r main \
     -f bypass_reason="<your incident description here>"
   ```

   Replace `<your incident description here>` with your incident or bypass
   reason. Do not leave it blank — an empty reason is rejected by the
   workflow input validation.

2. **Monitor the triggered run:**

   ```sh
   gh run list -R coder-devx/coder-core --workflow=ci.yml --limit=3
   ```

   Watch the most recent run. Wait for `check-deploy-critical` to finish
   green before expecting `deploy` to proceed. If `check-deploy-critical`
   turns red on this run, the deploy will not proceed — do not attempt to
   re-trigger; fix the underlying issue instead.

3. **Verify production health** once the `deploy` job shows green:

   ```sh
   curl https://<prod-url>/v1/health
   ```

   Expected response:
   ```json
   {"ok":true,"service":"coder-core","version":"...","environment":"prod"}
   ```

## Success condition

- The triggered run's `check-deploy-critical` job is green.
- The `deploy` job completes successfully.
- `GET /v1/health` returns `{"ok":true,...}`.
- An audit event `deploy.bypass_test_suite` appears in the admin panel's
  audit log with the correct `actor`, `sha`, and `bypass_reason`.

## Audit trail

Every bypass triggers the audit event `deploy.bypass_test_suite`, storing:

| Field | Value |
|---|---|
| `actor` | The GitHub identity that triggered the workflow run |
| `sha` | The `main` HEAD commit SHA that was deployed |
| `bypass_reason` | The string passed as `bypass_reason` in step 1 |

This event is searchable via the admin panel's audit log. Bypasses without
a meaningful `bypass_reason` will appear in the log and will be flagged
during incident retrospectives.

## If something goes wrong

| Symptom | Action |
|---|---|
| Workflow run not appearing after step 1 | Verify `gh auth status` and that you have write access to `coder-devx/coder-core`; re-run step 1 |
| `check-deploy-critical` fails on the new run | Do not bypass further — the change is not deploy-safe; fix the issue |
| `deploy` job fails mid-run | Check the Actions log for the specific step; see [deploy-coder-core](deploy-coder-core.md) for detailed troubleshooting |
| `/v1/health` returns non-`ok` after deploy | Follow rollback steps in [deploy-coder-core](deploy-coder-core.md#rollback) |
