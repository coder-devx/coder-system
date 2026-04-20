---
id: '0041'
title: Escalation policies & on-call routing
type: design
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
implements_specs: ['0041']
related_designs:
  - system-overview
  - worker-communication
  - observability-and-cost-tracking
  - audit-log
affects_services:
  - coder-core
  - coder-admin
---

# 0041 — Escalation policies & on-call routing (design)

## Context

Spec [0041](../../product-specs/wip/0041-escalation-policies.md)
scopes pipeline-run-shaped escalations (stall / failure-streak /
SLA-breach) routed through a 3-rung Slack → DM → PagerDuty ladder
with per-project on-call rotation. This design describes the
watcher, the data model, the dispatch fan-out, the ack/resolve
endpoints, and the admin surface.

Architectural choices that shape the shape:

1. **The watcher is a tick, not an event subscriber.** It scans DB
   state every minute. Event-driven triggers (e.g. subscribe to
   `pipeline_run.gate_blocked` SSE) would be lower latency but
   brittle on restart, on missed events, on clock skew between
   workers. A scan-every-minute loop against authoritative DB state
   recovers automatically from any of the above. Same pattern as
   0032 regression detector, 0038 rotator, 0040 auto-approve tick.

2. **Rungs are owned by the watcher, not a per-escalation timer.**
   The watcher scans open escalations and advances any whose
   `next_rung_due_at ≤ now`. No in-process schedulers, no per-row
   async tasks; the loop is the clock.

3. **Dispatchers are per-destination functions, not a trait
   hierarchy.** Three dispatch functions —
   `dispatch_slack_channel`, `dispatch_slack_dm`,
   `dispatch_pagerduty` — each consume an `EscalationContext` and
   post. A rung config names one. Adding Teams later adds one
   function; no refactor.

4. **Ack is eventually-consistent across destinations.** L0
   survives in the Slack channel history; the interactive button
   just marks the row. If the row is already `acknowledged` when a
   Slack button press arrives (e.g. via a second click), the
   handler returns success without re-audit. Idempotent by design.

## Goals / non-goals

### Goals

- 1-min detection floor from trigger crossing threshold to first
  dispatch.
- Single DB row is the source of truth for an escalation's state.
- Reuse existing Slack plumbing (0032, observability) — no new
  Slack client.
- Zero new queues, no Redis, no pub/sub. Postgres + Cloud Scheduler
  ticks.

### Non-goals

- Per-rung retry of failed dispatches (a Slack outage during L1
  dispatch is logged + retried on next tick; a PagerDuty outage
  same).
- Backfill of pre-existing stalls on first deploy. Watcher scans
  forward from boot.

## Architecture

```mermaid
flowchart TB
  subgraph state [Postgres]
    pr[(pipeline_runs<br/>blocked_since, started_at)]
    t[(tasks<br/>status, stage, updated_at)]
    tm[(task_messages)]
    esc[(escalations)]
    ocs[(on_call_schedules)]
    proj[(projects<br/>sla_* + policy + slack/PD IDs)]
    ae[(audit_events)]
  end

  subgraph job ["Cloud Run Job:<br/>coder-core-escalation-watch"]
    tick[1-min tick]
    scan[scan_triggers]
    open[open_escalation]
    advance[advance_rungs]
  end

  tick --> scan
  scan --> pr
  scan --> t
  scan --> tm
  scan --> proj
  scan -->|dedupe via| esc
  scan --> open
  open --> esc
  open --> dispatch
  tick --> advance
  advance --> esc
  advance --> dispatch

  subgraph dispatch [Dispatchers]
    s0[dispatch_slack_channel]
    s1[dispatch_slack_dm]
    s2[dispatch_pagerduty]
  end

  dispatch --> slack[Slack webhook/API]
  dispatch --> pd[PagerDuty Events API v2]
  dispatch --> ae

  subgraph api ["Coder-core HTTP"]
    ack[POST /escalations/:id/ack]
    resolve[POST /escalations/:id/resolve]
    slackhook[POST /v1/_hooks/slack/escalation_ack]
    ocsget[GET/PATCH /projects/:id/on-call]
  end

  slack -. Ack button .-> slackhook
  slackhook --> esc
  slackhook --> ae
  ack --> esc
  ack --> ae
  resolve --> esc
  resolve --> ae
  ocsget --> ocs

  subgraph admin [coder-admin]
    list[/admin/escalations]
    proj_tab[/projects/:id/escalations]
  end

  list --> esc
  proj_tab --> esc
  proj_tab --> ocs

  classDef pg fill:#fff3e0,stroke:#e65100
  class pr,t,tm,esc,ocs,proj,ae pg
```

## Parts

### 1. `escalations` table (migration 0046)

```sql
CREATE TYPE escalation_trigger AS ENUM (
    'stall',
    'failure_streak',
    'sla_breach'
);

CREATE TYPE escalation_status AS ENUM (
    'open',
    'acknowledged',
    'resolved',
    'expired'
);

CREATE TABLE escalations (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            text NOT NULL REFERENCES projects(project_id),
    trigger_kind          escalation_trigger NOT NULL,
    pipeline_run_id       uuid REFERENCES pipeline_runs(id),
    task_id               uuid REFERENCES tasks(id),
    status                escalation_status NOT NULL DEFAULT 'open',
    policy_name           text NOT NULL,          -- 'standard', 'aggressive', etc
    current_rung          text NOT NULL,          -- 'L0' | 'L1' | 'L2'
    rung_history          jsonb NOT NULL DEFAULT '[]'::jsonb,
    -- [{rung, fired_at, destination, outcome, detail}]
    next_rung_due_at      timestamptz,            -- NULL if terminal rung or ack/resolved
    opened_at             timestamptz NOT NULL DEFAULT now(),
    last_observed_at      timestamptz NOT NULL DEFAULT now(),
    acknowledged_at       timestamptz,
    acknowledged_by_type  text,                   -- 'user' | 'slack_external' | 'system'
    acknowledged_by_id    text,
    ack_note              text,
    resolved_at           timestamptz,
    resolved_by_type      text,
    resolved_by_id        text,                   -- user id, or 'self_healing' for 0042
    resolution            text,
    CONSTRAINT one_target CHECK (
        (pipeline_run_id IS NOT NULL) OR (task_id IS NOT NULL)
    )
);

CREATE UNIQUE INDEX escalations_open_dedupe_run_idx
    ON escalations (project_id, trigger_kind, pipeline_run_id)
    WHERE status = 'open' AND pipeline_run_id IS NOT NULL;

CREATE UNIQUE INDEX escalations_open_dedupe_task_idx
    ON escalations (project_id, trigger_kind, task_id)
    WHERE status = 'open' AND task_id IS NOT NULL;

CREATE INDEX escalations_watcher_idx
    ON escalations (next_rung_due_at)
    WHERE status = 'open' AND next_rung_due_at IS NOT NULL;
```

The partial unique indexes give us dedupe for free: insert of a
second open stall escalation on the same run violates the
constraint, caught by `ON CONFLICT DO NOTHING` in the watcher's
`open_escalation` path. The watcher then just bumps
`last_observed_at` on the existing row.

### 2. `on_call_schedules` table (migration 0047)

```sql
CREATE TABLE on_call_schedules (
    id                  uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id          text NOT NULL REFERENCES projects(project_id),
    slack_user_id       text NOT NULL,
    pagerduty_user_id   text,
    starts_at           timestamptz NOT NULL,
    ends_at             timestamptz NOT NULL,
    timezone            text NOT NULL DEFAULT 'UTC',
    CONSTRAINT ends_after_start CHECK (ends_at > starts_at)
);

CREATE INDEX on_call_schedules_project_window_idx
    ON on_call_schedules (project_id, starts_at, ends_at);
```

Overlapping rotations are allowed (bench + handoff); the resolver
picks the most recently created row whose window covers `now`.

### 3. Per-project columns (migration 0048)

```sql
ALTER TABLE projects
    ADD COLUMN escalation_policy           text NOT NULL DEFAULT 'off',
    ADD COLUMN sla_stall_minutes           integer NOT NULL DEFAULT 60,
    ADD COLUMN sla_wall_clock_minutes      integer NOT NULL DEFAULT 720,
    ADD COLUMN failure_streak_n            integer NOT NULL DEFAULT 3,
    ADD COLUMN failure_streak_window_minutes integer NOT NULL DEFAULT 30,
    ADD COLUMN escalation_slack_channel_id text,
    ADD COLUMN pagerduty_routing_key       text;
```

`PATCH /v1/projects/{id}` gains these fields (reusing the same
tri-state tolerance for nullable ones; the `sla_*` ints are
non-null with defaults so PATCH is simple overwrite).

### 4. Policy file: `config/escalation_policies.yaml`

Loaded once at process start, cached in memory:

```yaml
policies:
  off:
    rungs: []
  standard:
    rungs:
      - rung: L0
        destination: slack_channel
        wait_minutes_to_next: 5
      - rung: L1
        destination: slack_dm_oncall
        wait_minutes_to_next: 10
      - rung: L2
        destination: pagerduty
        wait_minutes_to_next: null  # terminal
  aggressive:
    rungs:
      - rung: L0
        destination: slack_channel
        wait_minutes_to_next: 2
      - rung: L2
        destination: pagerduty
        wait_minutes_to_next: null
```

Parsed into a typed `EscalationPolicy` dataclass at boot. A
policy-validation script runs on every build (`pytest` target or
standalone) to ensure every listed `destination` has a registered
dispatcher.

### 5. Trigger scan: `scan_triggers(db, now)`

Three SQL queries, run in sequence in each tick:

**Stall:**
```sql
-- pipeline_runs stalled on blocked_since
SELECT pr.id, pr.project_id
FROM pipeline_runs pr
JOIN projects p ON p.project_id = pr.project_id
WHERE pr.blocked_since IS NOT NULL
  AND pr.blocked_since <= now() - make_interval(mins => p.sla_stall_minutes)
  AND p.escalation_policy <> 'off'
  AND NOT EXISTS (
      SELECT 1 FROM escalations e
      WHERE e.pipeline_run_id = pr.id
        AND e.trigger_kind = 'stall'
        AND e.status = 'open'
  );
```

A parallel query checks _task_-level stalls: tasks in non-terminal
status whose most-recent `task_stage_runs` or `task_messages` row
is older than `sla_stall_minutes`. DispatcherQueue-blocked tasks
(0028) are excluded via `tasks.status='queued'` — queueing isn't a
stall per spec open-question.

**Failure streak:**
```sql
SELECT project_id, count(*) AS n, max(updated_at) AS last
FROM tasks
WHERE status = 'failed'
  AND updated_at >= now() - make_interval(mins => :window)
GROUP BY project_id
HAVING count(*) >= :threshold;
```

Threshold and window come from the project settings; this query
actually joins with `projects` for the per-project thresholds.

**SLA wall-clock breach:**
```sql
SELECT pr.id, pr.project_id
FROM pipeline_runs pr
JOIN projects p ON p.project_id = pr.project_id
WHERE pr.step NOT IN ('accepted', 'rejected', 'failed', 'cancelled')
  AND pr.started_at <= now() - make_interval(mins => p.sla_wall_clock_minutes)
  AND p.escalation_policy <> 'off'
  AND NOT EXISTS (
      SELECT 1 FROM escalations e
      WHERE e.pipeline_run_id = pr.id
        AND e.trigger_kind = 'sla_breach'
        AND e.status = 'open'
  );
```

Each hit from these queries is funnelled through `open_escalation`.

### 6. `open_escalation(db, trigger, target)`

```python
def open_escalation(db, trigger_kind, project_id, *, pipeline_run_id=None, task_id=None):
    project = db.get(ProjectRow, project_id)
    policy = POLICIES[project.escalation_policy]
    if not policy.rungs:
        return  # 'off' policy

    first = policy.rungs[0]
    now = datetime.now(UTC)
    next_due = now + timedelta(minutes=first.wait_minutes_to_next) if first.wait_minutes_to_next else None

    row = EscalationRow(
        project_id=project_id,
        trigger_kind=trigger_kind,
        pipeline_run_id=pipeline_run_id,
        task_id=task_id,
        policy_name=project.escalation_policy,
        current_rung=first.rung,
        next_rung_due_at=next_due,
    )
    try:
        db.add(row)
        db.flush()
    except IntegrityError:
        # Dedupe hit — partial unique index caught a duplicate. Bump last_observed_at instead.
        db.rollback()
        existing = _find_open_escalation(db, trigger_kind, project_id,
                                         pipeline_run_id=pipeline_run_id, task_id=task_id)
        existing.last_observed_at = now
        db.commit()
        return existing

    # Dispatch the first rung
    outcome = _dispatch(db, row, first, actor_type='system', actor_id='escalation-watch')
    row.rung_history = [{"rung": first.rung, "fired_at": now.isoformat(),
                          "destination": first.destination, "outcome": outcome}]
    record_audit_event(
        db=db, actor_type="system", actor_id="escalation-watch",
        action="escalation.opened", target_type="escalation", target_id=str(row.id),
        project_id=project_id,
        before=None,
        after={"trigger_kind": trigger_kind, "policy": row.policy_name,
               "pipeline_run_id": str(pipeline_run_id) if pipeline_run_id else None,
               "first_rung": first.rung, "first_outcome": outcome},
    )
    db.commit()
    return row
```

### 7. `advance_rungs(db, now)`

```python
def advance_rungs(db, now):
    rows = db.execute(
        select(EscalationRow)
        .where(EscalationRow.status == 'open')
        .where(EscalationRow.next_rung_due_at <= now)
        .with_for_update(skip_locked=True)
    ).scalars().all()

    for row in rows:
        policy = POLICIES[row.policy_name]
        current_idx = next(i for i, r in enumerate(policy.rungs) if r.rung == row.current_rung)
        if current_idx + 1 >= len(policy.rungs):
            # terminal rung reached; stop
            row.next_rung_due_at = None
            continue
        next_rung = policy.rungs[current_idx + 1]
        outcome = _dispatch(db, row, next_rung, actor_type='system', actor_id='escalation-watch')
        row.current_rung = next_rung.rung
        row.rung_history = row.rung_history + [{
            "rung": next_rung.rung, "fired_at": now.isoformat(),
            "destination": next_rung.destination, "outcome": outcome
        }]
        row.next_rung_due_at = (now + timedelta(minutes=next_rung.wait_minutes_to_next)
                                if next_rung.wait_minutes_to_next else None)
        record_audit_event(
            db=db, actor_type='system', actor_id='escalation-watch',
            action='escalation.rung_fired', target_type='escalation', target_id=str(row.id),
            project_id=row.project_id,
            before={"rung": row.current_rung},
            after={"rung": next_rung.rung, "destination": next_rung.destination,
                   "outcome": outcome},
        )
    db.commit()
```

### 8. Dispatchers

Each takes an `EscalationContext` (project, run/task, trigger,
rung-history so far, ack-link URL) and returns an
`DispatchOutcome` (`ok` | `skipped:<reason>` | `error:<detail>`).

**`dispatch_slack_channel`** reuses the existing fleet Slack client
(used by 0032 regression detector + observability). Posts a
structured message block with project + trigger + run link + an
interactive **Ack** button whose `action_id` carries the
escalation ID signed by the existing Slack signing secret.

**`dispatch_slack_dm_oncall`** resolves the current on-call via
`on_call_schedules`, then uses the Slack Web API
`chat.postMessage` with `channel=<user_id>` to DM them. Same
interactive button. If no on-call resolves and the project has no
owner fallback, returns `skipped:no_oncall`.

**`dispatch_pagerduty`** posts a PagerDuty Events API v2 trigger
against `project.pagerduty_routing_key`. If the key is unset,
returns `skipped:no_routing_key` and emits a structured warning.

The ack-link URL embedded in the payload points to
`/admin/escalations/{id}` so a click jumps straight to the
admin-panel detail.

### 9. Ack / resolve endpoints

`api/escalations.py` exposes:

```python
@router.post("/escalations/{escalation_id}/ack")
def ack(escalation_id: UUID, body: AckBody,
        project_id: str = Depends(require_project_auth),
        user_id: str = Depends(current_user),
        db: Session = Depends(db_session),
        correlation_id: str = Depends(get_correlation_id)):
    row = db.execute(
        select(EscalationRow).where(EscalationRow.id == escalation_id)
        .where(EscalationRow.project_id == project_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not_found")
    if row.status != 'open':
        return EscalationResponse.model_validate(row)  # idempotent
    row.status = 'acknowledged'
    row.acknowledged_at = datetime.now(UTC)
    row.acknowledged_by_type = 'user'
    row.acknowledged_by_id = user_id
    row.ack_note = body.note
    row.next_rung_due_at = None
    record_audit_event(
        db=db, actor_type='user', actor_id=user_id,
        action='escalation.acknowledged', target_type='escalation',
        target_id=str(row.id), project_id=project_id, correlation_id=correlation_id,
        before={"status": "open", "rung": row.current_rung},
        after={"status": "acknowledged", "rung": row.current_rung, "note": body.note},
    )
    db.commit()
    return EscalationResponse.model_validate(row)
```

`resolve` follows the same shape, setting `status='resolved'`
plus `resolution` + `resolved_by_*`. The 0042 self-healing
watchdog will call the same endpoint with `actor_type='system'`
and `resolved_by_id='self_healing'`.

### 10. Slack interactive hook

`POST /v1/_hooks/slack/escalation_ack` — no project-auth decorator;
verifies Slack signing secret, decodes the `action_id` payload to
recover the escalation ID + project ID, maps Slack user ID →
internal user ID (fallback: store the Slack handle in
`acknowledged_by_id` with `acknowledged_by_type='slack_external'`),
calls the same ack logic.

### 11. On-call schedule endpoints

```
GET   /v1/projects/{id}/on-call            # current on-call (derived)
GET   /v1/projects/{id}/on-call/schedule   # full schedule
PATCH /v1/projects/{id}/on-call/schedule   # set/replace
```

The `current` endpoint returns the resolver's pick — most recently
created schedule row where `starts_at ≤ now < ends_at`. Missing →
falls back to `projects.owner_slack_user_id` (a column added if not
already present) → 404.

### 12. Admin surfaces

- `/admin/escalations` — fleet list, filters on status (open /
  acknowledged / resolved) and trigger kind. Columns: project, run,
  trigger, rung, age, ack status, actions.
- `/projects/{id}/escalations` — per-project tab under the project
  overview. Shows this project's escalations + the current on-call
  (with Slack handle + PagerDuty user if set).
- Both behind `VITE_ESCALATIONS_ENABLED`.

### 13. Terraform

```hcl
# coder-core/infra/terraform/escalations.tf
resource "google_cloud_run_v2_job" "escalation_watch" {
  name     = "coder-core-escalation-watch"
  location = var.region
  template {
    template {
      service_account = google_service_account.escalation_watch.email
      containers {
        image = var.coder_core_image
        args  = ["python", "-m", "coder_core.escalations.watch"]
      }
    }
  }
}

resource "google_cloud_scheduler_job" "escalation_watch" {
  name     = "coder-core-escalation-watch"
  schedule = "* * * * *"  # every minute
  http_target { ... }
}

resource "google_service_account" "escalation_watch" { ... }
# SA needs: cloudsql.client, secretmanager.secretAccessor (slack/pd secrets), logging.logWriter
```

### 14. Observability wiring

`/metrics` grows a new `escalations` block:

```json
"escalations": {
  "open": 4,
  "mean_ack_minutes_7d": 6.2,
  "rung2_rate_7d": 0.12,
  "false_positive_rate_7d": 0.08,
  "by_trigger_7d": {"stall": 11, "failure_streak": 3, "sla_breach": 2}
}
```

Structured-log events:
- `escalation.opened`
- `escalation.rung_fired`
- `escalation.dispatch_skipped`
- `escalation.dispatch_error`
- `escalation.acknowledged`
- `escalation.resolved`

## Data flow

### Scenario A — standard stall → L0 Slack → ack

1. Project `acme` has `sla_stall_minutes=60`,
   `escalation_policy=standard`, Slack channel configured.
2. Pipeline run `abc` sits at `spec_approval` with
   `blocked_since=T`. At `T+60min+ε`, the next 1-min watcher tick
   runs `scan_triggers`.
3. Stall query hits; `open_escalation` inserts a row with
   `current_rung='L0'`, `next_rung_due_at=T+65min`.
4. `dispatch_slack_channel` posts to `#coder-acme` with run link +
   Ack button. Returns `ok`. Audit row written.
5. At `T+63min`, operator clicks Ack in Slack.
6. `POST /v1/_hooks/slack/escalation_ack` fires, resolves Slack
   user → internal user, takes `FOR UPDATE` on the row, sets
   `status='acknowledged'`, `next_rung_due_at=NULL`. Audit row.
7. Next watcher tick sees no open escalations with due rungs.

### Scenario B — unacknowledged, ladder all the way to PagerDuty

1. Same start as A.
2. L0 fires at `T+60min`. No click.
3. At `T+65min`, watcher `advance_rungs` locks the row, dispatches
   L1 (Slack DM to on-call). `current_rung='L1'`,
   `next_rung_due_at=T+75min`.
4. Still no ack. At `T+75min`, L2 dispatches to PagerDuty.
   `current_rung='L2'`, `next_rung_due_at=NULL` (terminal).
5. PagerDuty pages on-call's phone. They ack via PagerDuty (not via
   our ack endpoint). Our row stays `open` — PagerDuty
   acknowledgement doesn't propagate back in v1. That's fine: the
   ladder won't fire further, and the admin panel still shows the
   escalation as open until the operator either closes it manually
   or the underlying run resolves (see E).

### Scenario C — two triggers fire on the same run

1. Run `abc` is stalled _and_ hit SLA wall-clock at roughly the
   same tick.
2. `scan_triggers` returns two hits: `stall` and `sla_breach`.
   Partial unique indexes are on `(project_id, trigger_kind,
   pipeline_run_id)`, so both insert successfully.
3. Two independent escalations open; each has its own ladder.
   Operator sees two entries in the admin panel and can ack both
   independently.

### Scenario D — dedupe: same trigger fires again

1. L0 fired on run `abc`'s stall escalation but operator hasn't
   acked yet.
2. Next tick's scan finds the same stalled run.
3. `open_escalation` hits the partial unique index → `IntegrityError`.
4. Handler catches, updates `last_observed_at` on the existing row,
   doesn't re-dispatch, doesn't re-audit.

### Scenario E — 0042 self-healing closes the escalation

1. L0 has fired. Auto-remediation watchdog (future, 0042) detects
   the same stall, attempts remediation (e.g. retry a stuck task),
   and succeeds.
2. 0042 posts `POST /v1/projects/{id}/escalations/{id}/resolve`
   with `resolved_by_id='self_healing'`,
   `resolution='auto-retried stuck task abc'`.
3. Row transitions to `resolved`. Audit row
   (`escalation.resolved`, `actor_type='system'`,
   `actor_id='self-healing-watchdog'`). Further rungs stopped.

## Invariants

1. **An open escalation has at most one due rung at a time.** Rungs
   advance monotonically via `current_rung`; the watcher's
   `FOR UPDATE SKIP LOCKED` ensures two concurrent ticks can't
   both advance the same row.
2. **Dedupe is enforced by the DB.** No app-level check can race:
   the partial unique index catches concurrent inserts.
3. **Ack / resolve is idempotent.** A second ack on an already-
   acked row returns success without re-auditing. Prevents
   double-fires from a Slack client retry.
4. **Terminal rungs never re-fire.** `next_rung_due_at=NULL`
   excludes the row from the watcher's advance query.
5. **The watcher is stateless.** Crashing mid-tick leaves correct
   DB state (every transition is in its own transaction);
   next tick resumes from DB state.

## Interfaces

### New files

- `coder-core/src/coder_core/escalations/__init__.py`
- `coder-core/src/coder_core/escalations/watch.py` (Cloud Run Job)
- `coder-core/src/coder_core/escalations/models.py`
- `coder-core/src/coder_core/escalations/policies.py`
- `coder-core/src/coder_core/escalations/dispatchers/slack.py`
- `coder-core/src/coder_core/escalations/dispatchers/pagerduty.py`
- `coder-core/src/coder_core/api/escalations.py`
- `coder-core/src/coder_core/api/slack_hooks.py`
- `coder-core/src/coder_core/api/on_call.py`
- `coder-core/config/escalation_policies.yaml`
- `coder-core/migrations/0046-escalations.sql`
- `coder-core/migrations/0047-on-call-schedules.sql`
- `coder-core/migrations/0048-project-sla-columns.sql`
- `coder-core/infra/terraform/escalations.tf`
- `coder-admin/src/admin/escalations/EscalationsPage.tsx`
- `coder-admin/src/admin/escalations/EscalationDetail.tsx`
- `coder-admin/src/projects/OnCallTab.tsx`

### Modified files

- `coder-core/src/coder_core/api/projects.py::patch_project` —
  accept SLA + policy + Slack channel + PD routing-key fields.
- `coder-core/src/coder_core/api/audit.py::ALLOWED_ACTIONS` — five
  new `escalation.*` actions.
- `coder-core/app.py::Settings` — `CODER_ESCALATIONS_ENABLED`,
  `CODER_ESCALATION_WATCH_TICK_BUDGET_SECONDS` (default 55).
- `coder-admin/src/routes.tsx` — `/admin/escalations/*` routes,
  project-tab addition.
- `system/runbooks/escalations-firing.md` — new runbook (added
  under repo `system/runbooks/`).

### New endpoints

- `POST /v1/projects/{id}/escalations/{id}/ack`
- `POST /v1/projects/{id}/escalations/{id}/resolve`
- `GET  /v1/projects/{id}/escalations`
- `GET  /v1/projects/{id}/escalations/{id}`
- `GET  /v1/_admin/escalations?status=&trigger=`
- `POST /v1/_hooks/slack/escalation_ack`
- `GET  /v1/projects/{id}/on-call`
- `GET  /v1/projects/{id}/on-call/schedule`
- `PATCH /v1/projects/{id}/on-call/schedule`

### Environment flags

- `CODER_ESCALATIONS_ENABLED` — master switch (default `false`).
- `VITE_ESCALATIONS_ENABLED` — frontend visibility.
- `SLACK_SIGNING_SECRET` — existing, reused for the interactive hook.
- `PAGERDUTY_EVENTS_API_URL` — defaults to the standard endpoint.

## Open questions

- **PagerDuty ack → our ack.** Spec Scenario B notes PagerDuty
  acknowledgement doesn't propagate back in v1. PagerDuty supports
  webhooks on incident state changes; wiring them adds one more
  hook endpoint and a user-mapping concern. Leaning: phase-2 when
  we see how often it matters.

- **Slack-user-ID mapping to internal user_id.** Today we don't
  store a Slack user ID on `users`. Either (a) add a column and
  populate lazily on first interaction, (b) always record
  `acknowledged_by_type='slack_external'` with the raw handle.
  Leaning: (b) for v1, (a) when we do the admin panel auth
  polish in phase-2.

- **Task-level escalation target.** Do stall escalations target
  the `pipeline_runs` row or the stuck `task` row? Design
  supports both via the `CHECK (run OR task)` constraint. For v1
  stalls open against the run; task-level is reserved for the
  0042 self-healing watchdog's signals.

- **Rung-wait precision.** A 1-min tick means a "5-min" wait
  actually fires in [5, 6) minutes. Acceptable. If tighter
  precision is needed later, bump the tick to 30s (Cloud
  Scheduler supports, cost trivial).

## Rollout

### Stage 1 — schema + scan (shadow), week 1

Migrations land. Watcher deployed but
`CODER_ESCALATIONS_ENABLED=false`. Scan queries run; matched rows
log a structured event (`escalation.would_open`) but no rows
written, no Slack / PD posts. 3-day soak confirms scan queries
are cheap and the hit-rate is sane.

### Stage 2 — enable writes + L0 only, week 2

Flip fleet flag. Override the policy file to cap every policy at
L0 (Slack channel) for all projects. No DMs, no PagerDuty.
7-day soak on real stalls to tune thresholds (`sla_stall_minutes`,
`failure_streak_n`) per-project.

### Stage 3 — enable L1 + L2 per project, week 3+

Per-project opt-in: flip `escalation_policy=standard` (or
`aggressive` if requested) on each project once its on-call
schedule is populated and its Slack channel / PD routing key are
set. `coder` project first as dog-food.

### Stage 4 — self-healing integration (with 0042), later

When 0042 ships, 0042's remediation attempts call
`/escalations/{id}/resolve` with `self_healing` actor. Metrics
track capture rate.

## Backout plan

- Flip `CODER_ESCALATIONS_ENABLED=false`. Watcher short-circuits;
  existing open escalations stop advancing. Resolve any still
  open via the API or by `UPDATE escalations SET status='expired'`.
- Per-project opt-out: `PATCH /v1/projects/{id}` with
  `escalation_policy=off`. Immediate; next tick respects.
- Slack channel noisy? Point `escalation_slack_channel_id` to a
  per-project throwaway while tuning; no code change needed.
- Tables, columns, and the Cloud Run Job can be dropped wholesale
  at major-version cleanup if the feature is abandoned.
