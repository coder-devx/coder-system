---
id: redeploy-bypassing-test-suite
title: Redeploy coder-core bypassing the full test suite
type: runbook
status: active
owner: ro
created: 2026-05-14
updated: 2026-05-14
last_verified_at: 2026-05-14
applies_to_services: [coder-core]
applies_to_integrations: [github]
---

# Redeploy coder-core bypassing the full test suite

## When to use this

**Recovery class only.** This runbook applies when both of the following are
true:

1. `check-deploy-critical` passed on the target SHA (build, terraform
   validate, alembic single-head, isolation-manifest drift, capability-matrix
   drift, migration smoke-test — all green).
2. `check-full-suite` is red (one or more tests in the broader pytest suite are
   failing or flaking).

The typical trigger is a production-wedge incident where a flaky or broken
non-critical test has blocked the `deploy` job even though the deploy-critical
checks are satisfied. See [spec 0090](../product-specs/wip/0090-deploy-chain-resilience-to-test-flake.md).

> **Stop here if `check-deploy-critical` is also failing.**
> This runbook does not help. A failing `check-deploy-critical` means the build
> is broken, migrations are inconsistent, or a deploy-critical check has
> regressed. Fix the real issue first — bypassing the full suite won't unblock
> you and will deploy broken code.

## Prerequisites checklist

Before running any commands, confirm all three:

- [ ] **`check-deploy-critical` is green** on the target SHA. Verify on GitHub
  Actions: `gh run list -R coder-devx/coder-core --workflow=ci.yml --limit=5`
  — find the run for your SHA and confirm the `check-deploy-critical` job shows
  ✅.
- [ ] **Incident / bypass reason identified.** You need a short description of
  why you are bypassing (e.g. `"prod wedge: caplog flake blocking hotfix
  coder-core#251"`). This is written to the audit log and is required.
- [ ] **`gh` CLI authenticated with write access to `coder-devx/coder-core`.**
  Run `gh auth status` and confirm the token covers the `coder-devx` org with
  `repo` scope (or equivalent Actions write access).

## Steps

### 1. Re-trigger the workflow with a bypass reason

```sh
gh workflow run ci.yml \
  -R coder-devx/coder-core \
  -r main \
  -f bypass_reason="<your incident description here>"
```

Replace `<your incident description here>` with the reason you identified in
the prerequisites (e.g. `"prod wedge: caplog flake blocking hotfix
coder-core#251"`).

What this does:

- Triggers a fresh CI run on the current `main` HEAD.
- `check-deploy-critical` runs again and **must still pass** — the workflow
  does not skip it; it re-validates.
- `deploy` runs with `bypass_reason` set. The step that ordinarily gates on
  `check-full-suite` passing is skipped when `bypass_reason` is non-empty.
- The deploy step writes an audit event `deploy.bypass_test_suite` with
  `actor`, `sha`, and `bypass_reason` before the traffic shift.

### 2. Monitor the triggered run

```sh
gh run list -R coder-devx/coder-core --workflow=ci.yml --limit=3
```

Identify the new run ID (most recent). Then watch it:

```sh
gh run watch <run-id> -R coder-devx/coder-core
```

Or open the Actions tab in the browser:
<https://github.com/coder-devx/coder-core/actions/workflows/ci.yml>

Wait for `check-deploy-critical` to go green and `deploy` to complete.

### 3. Verify prod health

Once the `deploy` job shows green:

```sh
curl https://<prod-url>/v1/health
```

Expected response:

```json
{"ok":true,"service":"coder-core","version":"<new-sha>","environment":"prod"}
```

If `ok` is not `true`, or the version does not reflect the new SHA, the
canary health check may have failed mid-deploy — check the run logs.

## Audit trail

The `bypass_reason` value is captured by the deploy job and written as an
audit event:

| Field | Value |
|---|---|
| Event type | `deploy.bypass_test_suite` |
| `actor` | GitHub Actions actor (the authenticated user who triggered `gh workflow run`) |
| `sha` | The `main` HEAD SHA at time of deploy |
| `bypass_reason` | The string you supplied via `-f bypass_reason` |

This event is searchable in the admin panel's audit log. Filter by event type
`deploy.bypass_test_suite` to find all historical bypasses.

## Success condition

- `check-deploy-critical` green on the triggered run.
- `deploy` job green.
- `curl /v1/health` returns `{"ok":true}` with the new SHA.
- Audit event `deploy.bypass_test_suite` visible in the admin panel.

## Discouraging routine use

> **This lever is scoped to the incident-recovery class.**
>
> Using it to ship code that fails real tests degrades the signal that
> `check-full-suite` provides. If `check-full-suite` is red on a non-incident
> push, fix the tests before merging. Every bypass that isn't tied to a
> production-wedge incident is operator hack debt — it silently widens the gap
> between what CI validates and what runs in prod.
>
> If you find yourself reaching for this runbook outside of a production
> incident, stop and ask whether the failing tests should instead be entered
> into the skip registry (`tests/SKIPPED.yml`) with an expiry date, or fixed
> outright. Those paths preserve the signal; this one erodes it.

## If something goes wrong

| Symptom | Likely cause | Action |
|---|---|---|
| `check-deploy-critical` fails on the triggered run | A real deploy-blocking regression exists | Stop. Do not re-trigger with bypass. Fix the underlying issue first. |
| `gh workflow run` returns 404 or "workflow not found" | `ci.yml` path wrong or `gh` token lacks `actions:write` | Confirm `gh auth status` shows correct scopes; check the exact workflow filename in the repo. |
| `deploy` job skipped despite bypass trigger | `bypass_reason` input not wired in the workflow version on `main` | Check that spec 0090's CI changes are merged; if not, the old workflow doesn't accept the input. |
| Health check returns old SHA | Traffic shift didn't complete or canary health check failed | Check the `deploy` job logs for the canary step; roll back with `gcloud run services update-traffic` if needed (see [deploy-coder-core runbook](./deploy-coder-core.md#rollback)). |
| Audit event not visible in admin panel | Audit write step failed silently | Check the deploy job's "Write audit event" step output; escalate to System Admin if the audit ledger is unreachable. |
