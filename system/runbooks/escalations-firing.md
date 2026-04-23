---
id: escalations-firing
title: Escalations — operator guide
type: runbook
status: active
owner: ro
created: 2026-04-23
updated: 2026-04-23
last_verified_at: 2026-04-23
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [gcp, slack]
---

# Escalations — operator guide

The escalations component (shipped coder-core `c992a7b`, 2026-04-22) opens
a row and walks a three-rung paging ladder whenever a pipeline run stalls,
fails repeatedly, or breaches SLA. This runbook covers operator day-2 tasks:
tuning thresholds, reading the admin pages, rolling out the flag, and
handling failures. Product view: [escalations spec](../product-specs/active/escalations.md).
Technical design: [escalations design](../designs/active/escalations.md).

## What fires an escalation

The watcher (`coder-core-escalation-watch` Cloud Run Job, 1-minute tick)
scans three trigger kinds:

| Trigger | What's checked | Default threshold |
|---------|----------------|-------------------|
| `stall` | `pipeline_runs.blocked_since` | older than `sla_stall_minutes` (60 min) |
| `failure_streak` | consecutive `tasks.status='failed'` within window | ≥ `failure_streak_n` (3) in `failure_streak_window_minutes` (30 min) |
| `sla_breach` | `pipeline_runs` open longer than wall-clock limit | `sla_wall_clock_minutes` (720 min = 12 h) |

DispatcherQueue-blocked tasks (`stage='queued'`) are excluded — queueing is
not a stall. Dedupe is DB-enforced: a second signal on the same open
escalation bumps `last_observed_at` without re-opening or re-dispatching.
Different trigger kinds on the same run coexist independently.

## The three-rung ladder

| Rung | Destination | `standard` timer | `aggressive` timer |
|------|-------------|------------------|--------------------|
| L0 | Project Slack channel | — (immediate on open) | — |
| L1 | Slack DM to on-call | 5 min after L0 | (skipped) |
| L2 | PagerDuty Events API v2 | 10 min after L1 | 2 min after L0 |

Policy `off` means the watcher skips that project entirely. Policies are
defined in `coder-core/src/coder_core/escalations/escalation_policies.yaml`.
Rungs advance monotonically — acking stops further advancement; resolving
closes the row.

## Acknowledging and resolving

An operator can acknowledge via:

- **Slack interactive button** — in the L0/L1 message; verifies the
  `SLACK_SIGNING_SECRET`, maps Slack user ID → internal user (falls back to
  `acknowledged_by_type='slack_external'` with the raw handle).
- **API**: `POST /v1/projects/{id}/escalations/{esc_id}/ack`
- **Admin panel**: `/admin/escalations` or `/projects/:id/escalations` → Ack
  button on the row.

Ack freezes the ladder (`next_rung_due_at=NULL`) but keeps `status='open'`.
Resolve closes it: `POST /v1/projects/{id}/escalations/{esc_id}/resolve`.
Both are idempotent — a second call on a non-`open` row returns 200 and does
not re-audit.

## Reading the admin pages

`/admin/escalations` (fleet) and `/projects/:id/escalations` (per-project)
both sit behind `VITE_ESCALATIONS_ENABLED`. Key columns:

| Column | Meaning |
|--------|---------|
| `trigger_kind` | `stall`, `failure_streak`, or `sla_breach` |
| `current_rung` | last rung dispatched: L0, L1, L2 |
| `status` | `open` / `acknowledged` / `resolved` / `expired` |
| `last_observed_at` | last watcher re-detection (bumped on dedupe) |
| `rung_history` | JSONB array of `{rung, dispatched_at, outcome}` |

Click the pipeline run ID link to jump to the run detail. The on-call
identity shown in the row is resolved live via
`GET /v1/projects/{id}/on-call`. Check `rung_history[].outcome` for
`skipped:<reason>` or `error:<detail>` on any rung that didn't reach
its destination.

## Tuning per-project thresholds

All four threshold columns accept a `PATCH /v1/projects/{id}`:

```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "sla_stall_minutes": 90,
    "failure_streak_n": 5,
    "failure_streak_window_minutes": 60,
    "sla_wall_clock_minutes": 1440
  }' https://coder-core-<hash>.a.run.app/v1/projects/<project-id>
```

Guidance: raise `sla_stall_minutes` for projects with long human-approval
stages (spec/design reviews can legitimately block 2–4 hours). Raise
`failure_streak_n` if two transient failures in a row are normal; lower it
if two is already anomalous. Changes take effect on the next 1-minute tick.

## Setting policy and routing

```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "escalation_policy": "standard",
    "escalation_slack_channel_id": "C0XXXXXXXXX",
    "pagerduty_routing_key": "xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
  }' https://coder-core-<hash>.a.run.app/v1/projects/<project-id>
```

L2 (PagerDuty) requires `pagerduty_routing_key`. Without it, the L2 rung
records `outcome='skipped:no_routing_key'` and logs a structured warning;
the rung is not re-tried.

## Managing the on-call schedule

The resolver picks the most-recently-created `on_call_schedules` entry
whose `[starts_at, ends_at)` window covers `now()`. No matching entry →
falls back to the project owner identity.

```sh
# Who is on-call right now
curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
  https://coder-core-<hash>.a.run.app/v1/projects/<id>/on-call

# List all schedule windows
curl -sS -H "Authorization: Bearer $ADMIN_JWT" \
  https://coder-core-<hash>.a.run.app/v1/projects/<id>/on-call/schedule

# Replace schedule (PATCH replaces all rows for the project)
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '[
    {"slack_user_id": "U0XXXXXXXXX", "pagerduty_user_id": "PXXXXXXX",
     "starts_at": "2026-04-28T00:00:00Z", "ends_at": "2026-05-05T00:00:00Z",
     "timezone": "Europe/Amsterdam"}
  ]' https://coder-core-<hash>.a.run.app/v1/projects/<id>/on-call/schedule
```

Overlapping windows are allowed; the most-recently-created wins. There is no
gap-fill — if no window covers `now()`, the project owner is the fallback.

## Stage 2 rollout — L0-only fleet

Prerequisites: migrations 0046/0047/0048 applied; Cloud Run Job
`coder-core-escalation-watch` and its Scheduler trigger wired (same gcloud
shape as the secret-rotation-scheduler runbook); `CODER_ESCALATIONS_ENABLED`
is `false` on both service and Job.

Cap every project at L0 to avoid Slack DMs or PagerDuty pages during
threshold tuning. Two options:

- **Policy cap via config**: edit
  `coder-core/src/coder_core/escalations/escalation_policies.yaml` to
  strip L1/L2 rungs from `standard` and `aggressive` before flipping the
  flag, then restore them when Stage 3 begins.
- **Per-project opt-in control**: leave all projects at
  `escalation_policy='off'` and opt in only the canary while the flag is on.

Flip the fleet flag:

```sh
gcloud run services update coder-core \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_ESCALATIONS_ENABLED=true

gcloud run jobs update coder-core-escalation-watch \
  --project=vibedevx --region=europe-west1 \
  --update-env-vars=CODER_ESCALATIONS_ENABLED=true
```

**Soak checklist** — watch `/metrics` `escalations` block for ≥ 48 h:

| Metric | Healthy |
|--------|---------|
| `open` | stable count, not growing unbounded |
| `mean_ack_minutes_7d` | < 30 min |
| `rung2_rate_7d` | 0 (expected while capped at L0) |
| `false_positive_rate_7d` | < 0.10 |
| `by_trigger_7d` | distribution matches known stall patterns |

Revert trigger: `false_positive_rate_7d > 0.30`, `open` count growing
unbounded (dedupe bug), or any L1/L2 rung firing while the cap is in place.

## Stage 3 rollout — per-project full ladder

Before opting a project in, verify:

- `on_call_schedules` has at least one entry covering the next 7 days.
- `escalation_slack_channel_id` is set.
- `pagerduty_routing_key` is set if the policy will use L2.

Start with `coder` as dogfood:

```sh
curl -X PATCH -H "Authorization: Bearer $ADMIN_JWT" \
  -H "Content-Type: application/json" \
  -d '{"escalation_policy": "standard"}' \
  https://coder-core-<hash>.a.run.app/v1/projects/coder
```

Watch `mean_ack_minutes_7d` and `rung2_rate_7d` for a week before opting in
the next project. Use `aggressive` only for projects where a 2-minute
response window is genuinely expected; most start with `standard`.

## Back-out / kill-switch

In order of increasing blast radius:

1. **Redirect noise**: set `escalation_slack_channel_id` to a throwaway
   channel while tuning thresholds. No code change, takes effect next tick.
2. **Per-project disable**: `PATCH /v1/projects/{id}` with
   `escalation_policy='off'`. Watcher skips the project from the next tick.
3. **Fleet kill-switch**:
   ```sh
   gcloud run services update coder-core \
     --project=vibedevx --region=europe-west1 \
     --update-env-vars=CODER_ESCALATIONS_ENABLED=false
   gcloud run jobs update coder-core-escalation-watch \
     --project=vibedevx --region=europe-west1 \
     --update-env-vars=CODER_ESCALATIONS_ENABLED=false
   ```
   Existing `open` rows persist; no new rungs fire.

Manual DB intervention: use `UPDATE escalations SET status='expired' WHERE
id=...` only when a row is genuinely stuck and the business context is
resolved — not for bulk silencing. If the underlying run is still open, the
watcher will re-detect after the next tick, which is often the right
behaviour rather than expiring.

## Common failure modes

**Slack Ack button returns an error** — signing secret mismatch. The hook
verifies `SLACK_SIGNING_SECRET` on every inbound request. Check that the env
var is set on the service:
```sh
gcloud run services describe coder-core \
  --project=vibedevx --region=europe-west1 \
  --format='value(spec.template.spec.containers[0].env)' \
  | grep SLACK_SIGNING
```
If missing, set it and redeploy.

**PagerDuty rung silently skipped** — `rung_history[].outcome` will read
`skipped:no_routing_key`. Set the project's `pagerduty_routing_key`. If the
key is present but the outcome is `error:rate_limit`, PagerDuty's Events API
is being throttled (120 req/min per integration key) — escalations fire at
most one event per rung, so a sustained rate-limit usually means multiple
projects share a routing key and are all firing simultaneously.

**Dispatcher errors in rung_history** — `error:<detail>` holds the exception
message. Common causes: Slack bot token revoked, `PAGERDUTY_EVENTS_API_URL`
misconfigured, network timeout. Search Cloud Logging for
`jsonPayload.event="escalation.dispatch_error"` to see the full context.

**DispatcherQueue tasks appearing as stalls** — should not happen; the stall
detector excludes tasks with `stage='queued'`. If you observe a stall
escalation on a run that is genuinely only waiting for dispatcher capacity,
the exclusion query may have drifted — file a bug.

## Self-healing integration

When the 0042 self-healing watchdog remediates a stalled or failed run before
a human responds, it calls
`POST /v1/projects/{id}/escalations/{esc_id}/resolve` with
`resolved_by_id='self_healing'`. The row then shows:

- `status='resolved'`
- `resolved_by_id='self_healing'`, `resolved_at=<timestamp>`
- Audit event `escalation.resolved` with `actor_method='system'` and
  `after.resolved_by_id='self_healing'`.

Compare `resolved_by_id='self_healing'` vs human-resolved counts in
`/admin/escalations` or the audit log to measure the watchdog capture rate
over time.
