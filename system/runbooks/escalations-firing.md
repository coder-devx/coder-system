---
id: escalations-firing
title: Escalations — watcher operation, rollout, and tuning
type: runbook
status: active
owner: ro
created: 2026-04-23
updated: 2026-04-23
last_verified_at: 2026-04-23
affects_repos: [coder-core, coder-admin]
---

# Escalations — watcher operation, rollout, and tuning

The escalation watcher is deployed (shipped 2026-04-22, `coder-core`
`c992a7b`), flag-gated on `CODER_ESCALATIONS_ENABLED`, default off
fleet-wide. This runbook covers day-to-day operation, the remaining
rollout stages, and how to tune per-project settings.

For the product view see the
[escalations spec](../product-specs/active/escalations.md).
For tables, endpoints, and the ladder state machine see the
[escalations design](../designs/active/escalations.md).

## What fires an escalation

The watcher runs every minute and scans three trigger queries:

| Kind | Column | Default threshold |
|---|---|---|
| `stall` | `pipeline_runs.blocked_since` older than `projects.sla_stall_minutes` | 60 min |
| `failure_streak` | ≥ `failure_streak_n` consecutive `tasks.status='failed'` within `failure_streak_window_minutes` | 3 failures / 30 min window |
| `sla_breach` | `pipeline_runs` open longer than `projects.sla_wall_clock_minutes` | 720 min (12 h) |

DispatcherQueue-blocked tasks are excluded — queuing is not a stall.
The same run can trigger multiple kinds (e.g. stall + sla_breach);
they open as separate rows. A second stall signal on the same open run
bumps `last_observed_at` without re-dispatching.

## The three-rung ladder

Each escalation row has a `policy_name` drawn from
`config/escalation_policies.yaml`:

| Policy | Rungs |
|---|---|
| `off` | No rungs; watcher skips the project entirely |
| `standard` | L0 post to project Slack channel → 5 min → L1 DM on-call → 10 min → L2 PagerDuty |
| `aggressive` | L0 → 2 min → L2 PagerDuty (no DM rung) |

Rungs advance monotonically. Once a rung fires, `current_rung` only
increases. `next_rung_due_at=NULL` removes the row from the advance
query — this happens after the final rung fires, or on ack/resolve.

## Acknowledging an escalation

Ack stops further rungs but leaves the row open (`status='acknowledged'`).
Resolve closes it (`status='resolved'`). Both are idempotent.

Three paths to ack:

1. **Slack interactive button** — the L0 and L1 Slack messages carry
   an Ack button. Clicking it posts to `POST /v1/_hooks/slack/escalation_ack`
   (verified via `SLACK_SIGNING_SECRET`). The button is the fastest path
   for the on-call.
2. **API directly:**
   ```sh
   curl -X POST -H "Authorization: Bearer $ADMIN_JWT" \
     https://coder-core-<hash>.a.run.app/v1/projects/<project_id>/escalations/<esc_id>/ack
   ```
3. **Admin panel** — click Acknowledge on `/admin/escalations` or
   `/projects/:id/escalations`.

To resolve (close the incident):
```sh
curl -X POST -H "Authorization: Bearer $ADMIN_JWT" \
  https://coder-core-<hash>.a.run.app/v1/projects/<project_id>/escalations/<esc_id>/resolve
```

Resolving via the admin panel is also available. A PagerDuty ack
does _not_ propagate back — you must ack in Coder separately (v1 gap,
tracked in the design open questions).

## Reading the escalations views

`/admin/escalations` shows the fleet view; `/projects/:id/escalations`
shows the per-project view. Both are behind `VITE_ESCALATIONS_ENABLED`.

Key columns:
- **Age** — `now() - opened_at`. Long age + status `open` = rungs have
  already fired or nobody has acked.
- **Rung** — `current_rung` (`L0`/`L1`/`L2`). Shows the last rung
  that fired.
- **On-call** — the Slack user ID or fallback identity that received
  L1. Clicking through goes to the project's
  `/projects/:id/escalations/:id` detail.
- **Run link** — links directly to the `pipeline_runs` row. From there
  you can see every task and message for the stalled or failing run.
- **`rung_history` (API only)** — `GET /v1/projects/{id}/escalations/{id}`
  returns this as JSON; each entry has `rung`, `fired_at`,
  `dispatcher`, and `outcome`. Use it to confirm dispatchers fired
  and check for `error:` outcomes.

To find the current on-call identity without an open escalation:
```sh
curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
  https://coder-core-<hash>.a.run.app/v1/projects/<project_id>/on-call
```

## Tuning per-project thresholds

All four threshold columns are writeable via `PATCH /v1/projects/{id}`:

```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "sla_stall_minutes": 45,
    "failure_streak_n": 5,
    "failure_streak_window_minutes": 60,
    "sla_wall_clock_minutes": 480
  }' \
  https://coder-core-<hash>.a.run.app/v1/projects/<project_id>
```

Guidance: start with defaults (60/3/30/720). Lower `sla_stall_minutes`
only for projects with tight SLAs and fast human response. Raise
`failure_streak_n` if a project's tasks are frequently flaky and
you're seeing false positives. The watcher picks up new thresholds on
the next tick.

## Setting escalation policy and notification identifiers

```sh
# Set policy + Slack channel + PagerDuty routing key in one call.
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "escalation_policy": "standard",
    "escalation_slack_channel_id": "C0XXXXXXXXX",
    "pagerduty_routing_key": "abcdef1234567890abcdef1234567890"
  }' \
  https://coder-core-<hash>.a.run.app/v1/projects/<project_id>
```

- `escalation_policy`: `off` | `standard` | `aggressive`.
- `escalation_slack_channel_id`: the Slack channel ID (not name) where
  L0 notifications land. Point it at a throwaway channel while you tune
  thresholds — zero code change, instant effect.
- `pagerduty_routing_key`: Events API v2 routing key. Required for any
  policy that includes L2. Absent → `skipped:no_routing_key` in
  `rung_history.outcome` and a structured warning log. No L2 fires.

## Managing on-call schedules

The on-call resolver picks the most-recently-created `on_call_schedules`
row whose `[starts_at, ends_at)` window covers `now()`. Gaps fall back
to the project owner identity.

List current schedule:
```sh
curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
  https://coder-core-<hash>.a.run.app/v1/projects/<project_id>/on-call/schedule
```

Replace with a new rotation:
```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "entries": [
      {
        "slack_user_id": "U0AAAAAAAA",
        "pagerduty_user_id": "PXXXXXXX",
        "starts_at": "2026-04-28T00:00:00Z",
        "ends_at": "2026-05-05T00:00:00Z",
        "timezone": "Europe/London"
      }
    ]
  }' \
  https://coder-core-<hash>.a.run.app/v1/projects/<project_id>/on-call/schedule
```

PATCH replaces the schedule for the project (doesn't append).
Overlapping windows are allowed; the resolver always picks the
most-recently-created one that covers `now()`.

## Stage 2 rollout — fleet flag on, all projects capped at L0

Stage 1 (shadow) is already running — the watcher logs
`escalation.would_open` events without writing rows.

Stage 2 flips the fleet flag so the watcher starts opening real rows,
but all projects remain at `escalation_policy='off'` except for one
canary you promote to `standard` while capping actual rungs at L0 only.

The cleanest L0 cap is via `config/escalation_policies.yaml` in
`coder-core` — comment out the L1/L2 rungs from the `standard` and
`aggressive` policies so the file has only L0 entries. Deploy that
change before flipping the flag.

Flip the fleet flag (service + Job):
```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_ESCALATIONS_ENABLED=true

gcloud run jobs update coder-core-escalation-watch \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_ESCALATIONS_ENABLED=true
```

Alternatively, leave all projects at `escalation_policy='off'` and
only opt in the `coder` project at `policy=standard` — this naturally
caps the fleet at L0 because non-`coder` projects won't dispatch.

**Soak checklist** — watch `/metrics` escalations block for at least
72 hours before advancing to Stage 3:

| Metric | Healthy threshold | Revert signal |
|---|---|---|
| `open` | Steady (not climbing unbounded) | Monotonically rising → tick may be stuck |
| `mean_ack_minutes_7d` | < 30 min | > 60 min signals thresholds too tight or on-call gap |
| `rung2_rate_7d` | 0.0 (cap in effect) | Any non-zero → L0 cap not working |
| `false_positive_rate_7d` | < 0.20 | > 0.30 → thresholds too sensitive, tune before Stage 3 |
| `by_trigger_7d.stall` | Non-zero but bounded | Spike → DispatcherQueue exclusion may be broken |

If `rung2_rate_7d > 0` while the cap is supposed to be in place,
confirm the policy YAML deployed correctly and that the Job image was
updated.

## Stage 3 rollout — per-project full-ladder opt-in

Prerequisites per project before switching from `off` to `standard` or
`aggressive`:

1. `on_call_schedules` has at least one entry covering the next 7 days.
2. `escalation_slack_channel_id` is set to a real, monitored channel.
3. `pagerduty_routing_key` is set (required if policy includes L2).

Remove the L0-only cap from `escalation_policies.yaml` (or restore
the full rung list), deploy, then opt in the `coder` project first:

```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"escalation_policy": "standard"}' \
  https://coder-core-<hash>.a.run.app/v1/projects/coder
```

Watch `rung2_rate_7d` and `mean_ack_minutes_7d` for the canary project
for one week. If metrics are healthy, repeat for other projects.

## Back-out and kill-switch

**Fleet kill-switch:**
```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_ESCALATIONS_ENABLED=false

gcloud run jobs update coder-core-escalation-watch \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_ESCALATIONS_ENABLED=false
```

Flag off → watcher short-circuits every tick. Existing `open` rows stay
open in the DB but no new rungs fire and no new rows open. They will
eventually age as `expired` when cleaned up, or you can resolve them
manually.

**Per-project silence** (faster than a deploy):
```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"escalation_policy": "off"}' \
  https://coder-core-<hash>.a.run.app/v1/projects/<project_id>
```

**Redirect noise while tuning:**
Set `escalation_slack_channel_id` to a throwaway channel — the watcher
picks it up on the next tick with no restart.

**When to force-expire rows in the DB:**
Only necessary if you need to clear the admin view immediately after a
back-out and don't want to wait for natural expiry. Use with care:
```sql
UPDATE escalations SET status='expired', resolved_at=now()
WHERE status='open' AND project_id='<project_id>';
```
If you can let them ride, do so — the watcher's dedupe indexes prevent
re-opening the same target while an open row exists.

## Common failure modes

**Slack signing-secret mismatch on the ack hook** — the hook returns
HTTP 403 and logs `slack_signing_secret_mismatch`. Verify that
`SLACK_SIGNING_SECRET` on the service matches the value in the Slack
app's "App Credentials" page. The same secret is shared with the
regression-detector hook; changing it affects both.

**PagerDuty L2 silently skipped** — look for `skipped:no_routing_key`
in `rung_history.outcome` for the escalation row (`GET
/v1/projects/{id}/escalations/{id}`). The project's
`pagerduty_routing_key` is null or wrong. Fix via PATCH; the next
tick's `advance_rungs` won't re-fire an already-fired rung (rungs are
monotonic), so you may need to resolve and let the next stall reopen.

**Dispatcher errors in `rung_history.outcome`** — `error:<detail>`
entries mean the dispatcher threw. Check structured logs for
`escalation.dispatch_error` with the same escalation ID. Common causes:
Slack token expired (re-mint via the admin OAuth flow), PagerDuty API
rate limit (transient; next tick retries if `next_rung_due_at` is
still in the past — but rung monotonicity means it won't re-fire a
completed rung on the same row).

**DispatcherQueue tasks misreported as stalls** — they shouldn't be.
The stall query explicitly excludes `pipeline_runs` whose only blocked
tasks are in `DispatcherQueue` state. If you see a queued-task run
triggering a stall escalation, check that the migration 0046 landed
with the correct exclusion predicate.

**Tick executions going red** — a per-row error is captured in
`rung_history` and the watcher moves on; the Job still exits 0. A
systemic red (every execution fails) usually means DB connectivity or
Cloud SQL IAM. Check `gcloud run jobs executions describe
<exec-id> --region=europe-west1` for the exit reason.

## Relationship with self-healing (0042)

When the self-healing watchdog remediates a stuck or failing run before
a human acks, it calls `.../resolve` with `resolved_by_id='self_healing'`.
The escalation row transitions to `resolved` with `resolved_by`
identifying the self-healing actor and `resolved_at` set. Further rungs
stop immediately. The `audit_events` row has
`action='escalation.resolved'` with `actor_method='system'` and
`after.resolved_by_id='self_healing'`.

On the admin panel the row appears under the "resolved" filter with the
on-call identity blank and the resolved-by field showing the system
actor. The `/metrics` `false_positive_rate_7d` counts these as
non-false-positive (the stall was real; self-healing just beat the
human). A high proportion of self-healing-resolved escalations in
`by_trigger_7d` is a positive signal for 0042 capture rate.

## Related

- Spec: [escalations](../product-specs/active/escalations.md)
- Design: [escalations](../designs/active/escalations.md)
- Adjacent runbooks:
  [pipeline-run-blocked](./pipeline-run-blocked.md) (manual triage
  of a stalled run before escalation fires),
  [secret-rotation-scheduler](./secret-rotation-scheduler.md) (same
  Cloud Run Job + Scheduler pattern),
  [auto-approve-rollout](./auto-approve-rollout.md) (same staged
  flag-rollout pattern).
