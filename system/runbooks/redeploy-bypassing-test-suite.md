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

## When to use

Use this runbook only when **all** of the following are true:

1. The current `main` HEAD is production-wedged — a deploy is needed urgently.
2. `check-deploy-critical` passed on the target SHA (the fast gate is green).
3. Only `check-full-suite` is red — the slow test suite has a flaky or
   unrelated failure that is blocking the deploy job.

> **Stop if `check-deploy-critical` is also failing.** This runbook does not
> help you there. A red critical gate means the SHA has a real problem; fix
> the issue first and let CI run normally. Bypassing the full suite while the
> critical gate is red will deploy broken code and make the incident worse.

This lever is scoped to the **incident-recovery class** — a production wedge
where the code is known good (critical checks green) but a flaky or unrelated
test is blocking the path to prod. It is not a shortcut for shipping code that
fails real tests.

## Prerequisites

Before running the steps below, confirm all three:

- [ ] **`check-deploy-critical` is green** on the target SHA in GitHub Actions
      ([`coder-devx/coder-core` Actions](https://github.com/coder-devx/coder-core/actions)).
      Do not proceed if this job is red or has not run.
- [ ] **Incident / bypass reason identified** — you need a short, clear
      description of why you are bypassing (e.g. `"flaky integration test
      blocking prod fix for incident-42"`). This is stored in the audit trail;
      vague reasons make post-incident review harder.
- [ ] **`gh` CLI authenticated** with write access to `coder-devx/coder-core`
      — run `gh auth status` to confirm. You need at least
      `repo` scope and write permission on the repo.

## Steps

### 1. Trigger the bypass workflow run

```sh
gh workflow run ci.yml \
  -R coder-devx/coder-core \
  -r main \
  -f bypass_reason="<your incident description here>"
```

This re-triggers the full `ci.yml` workflow on the current `main` HEAD with
`bypass_reason` set. The workflow:

- Runs `check-deploy-critical` again — **this must still pass**; if it
  fails the deploy job is skipped and nothing reaches prod.
- Runs the `deploy` job with the `bypass_reason` input set, which causes
  the `check-full-suite` gate to be skipped for this run.
- Writes an audit event `deploy.bypass_test_suite` with `actor`, `sha`,
  and `bypass_reason`.

Replace `<your incident description here>` with the actual reason. Keep it
human-readable — it surfaces verbatim in the admin audit log.

### 2. Monitor the triggered run

```sh
gh run list -R coder-devx/coder-core --workflow=ci.yml --limit=3
```

Identify the run you just triggered (it will be the most recent). Watch it:

```sh
gh run watch <run-id> -R coder-devx/coder-core
```

Wait for `check-deploy-critical` to go green and `deploy` to complete.

### 3. Verify prod health

Once the deploy job shows green:

```sh
curl https://<prod-url>/v1/health
```

Expected response:

```json
{"ok":true,"service":"coder-core","version":"X.Y.Z","environment":"prod"}
```

If the health check is not returning `"ok":true`, treat this as a failed
deploy and follow the [deploy-coder-core rollback procedure](./deploy-coder-core.md#rollback).

## Success condition

- `check-deploy-critical` passed in the triggered run.
- `deploy` job completed green.
- `curl https://<prod-url>/v1/health` returns `{"ok":true,...}`.
- The audit event `deploy.bypass_test_suite` appears in the admin panel
  audit log (see below).

## Audit trail

Every bypass run writes an audit event with the following fields:

| Field | Value |
|---|---|
| `event` | `deploy.bypass_test_suite` |
| `actor` | GitHub identity of the user who triggered the workflow run |
| `sha` | The `main` HEAD SHA that was deployed |
| `bypass_reason` | The string you passed as `bypass_reason` in step 1 |

To find the event in the admin panel: **Audit Log → filter by event
`deploy.bypass_test_suite`**. Each bypass is individually searchable. This
trail is the evidence chain for post-incident review; make sure your
`bypass_reason` is specific enough to reconstruct the decision context.

## Guardrails — do not use this routinely

> **This lever is scoped to the incident-recovery class.** Using it to ship
> code that fails real tests degrades the signal value of `check-full-suite`
> across the entire project. Every routine bypass makes it harder to catch
> regressions before they reach prod.
>
> If `check-full-suite` is red on a non-incident push, **fix the tests before
> merging**. The right response to a consistently red suite is to either fix
> the tests or explicitly skip the specific flaky test with a tracking ticket
> — not to reach for the bypass lever.
>
> Repeated non-incident bypasses will be flagged in the monthly audit review.
