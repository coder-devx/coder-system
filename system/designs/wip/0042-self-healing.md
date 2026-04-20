---
id: '0042'
title: Self-healing stuck pipelines
type: design
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
implements_specs: ['0042']
related_designs:
  - system-overview
  - worker-communication
  - worker-roles
  - observability-and-cost-tracking
  - audit-log
  - '0041'
affects_services:
  - coder-core
  - coder-admin
---

# 0042 — Self-healing stuck pipelines (design)

## Context

Spec [0042](../../product-specs/wip/0042-self-healing.md) scopes a
watchdog that remediates three specific stuck-pipeline patterns
(stuck-queued, zombie-executing, orphan-chain-hook), with strict
safety caps, flag gating per pattern, and integration with the
0041 escalation ladder. This design describes the watchdog, the
pattern-registry abstraction, the three v1 remediators, the
heartbeat wiring workers need to grow, and the admin surface.

Architectural priors that shape the shape:

1. **Zero-diagnosis, catalog-only.** The watchdog does not try to
   figure out _what's wrong_. It pattern-matches known shapes.
   Unfamiliar stalls are someone else's problem (0041).
2. **Remediation must be idempotent.** Every `remediate` call on a
   target that's already healed is a no-op. Protects against tick
   races, double-runs, and operator-plus-watchdog concurrency.
3. **Every remediation is reversible or moot.** `stuck_queued` is
   re-enqueue (no-op on already-queued). `zombie_executing` is
   clone-and-retry (same shape as `/tasks/{id}/retry`, reversible
   by reject on the clone). `orphan_chain_hook` is replay-hook
   (pure-function, no-op when next-step exists).
4. **Flag-gated end-to-end, per pattern.** A patch that breaks one
   remediator never escapes its own flag.

## Goals / non-goals

### Goals

- A `Remediator` protocol so adding a pattern in phase-2 is a
  one-file change.
- Detection + remediation in separate methods so `dry_run` works
  without code duplication.
- Tick-by-tick fairness across projects: the watchdog iterates
  projects in a stable order and budgets per project per tick so
  a heavy project can't starve a lighter one.
- Shared test harness: every Remediator ships with a test that
  constructs the stuck state, runs detect+remediate, asserts
  outcome + audit + escalation-close.

### Non-goals

- A diagnosis/planning step. No LLM-in-the-loop for remediation.
- Cross-pattern ordering (e.g. "remediate zombies before
  retrying the chain"). Each pattern stands alone.
- Re-opening remediated escalations if the remediation didn't
  actually work. If a `stuck_queued` remediation failed to
  unstick, the 0041 watchdog's next tick will fire a new
  escalation — the prior one stays closed for audit.

## Architecture

```mermaid
flowchart TB
  subgraph state [Postgres]
    t[(tasks<br/>status, heartbeat_at, deadline_at)]
    pr[(pipeline_runs<br/>step, started_at)]
    esc[(escalations)]
    sh[(self_heal_attempts)]
    ae[(audit_events)]
    proj[(projects)]
  end

  subgraph job ["Cloud Run Job:<br/>coder-core-self-heal-watch"]
    tick[5-min tick]
    loop[for each enabled<br/>project × pattern]
    detect[Remediator.detect]
    cap[check daily cap]
    remedy[Remediator.remediate]
    close[close matching<br/>0041 escalations]
  end

  subgraph registry [REMEDIATORS registry]
    r1[stuck_queued]
    r2[zombie_executing]
    r3[orphan_chain_hook]
  end

  tick --> loop
  loop --> detect
  detect --> r1
  detect --> r2
  detect --> r3
  detect --> cap
  cap -->|cap ok| remedy
  cap -->|cap hit| skip[record skipped_cap]
  remedy --> sh
  remedy --> ae
  remedy --> close
  close --> esc
  skip --> sh

  subgraph workers [Role workers]
    hb[heartbeat every 30s]
  end

  hb --> hbep[PATCH /tasks/:id/heartbeat]
  hbep --> t

  subgraph admin [coder-admin]
    page[/admin/self-heal]
  end

  page --> sh
  page --> ae
```

## Parts

### 1. Remediator protocol

```python
# coder_core/self_heal/protocol.py
@dataclass(frozen=True)
class Target:
    project_id: str
    target_type: Literal["task", "pipeline_run"]
    target_id: str
    detail: dict  # pattern-specific diagnostic context

@dataclass(frozen=True)
class RemediationOutcome:
    status: Literal["succeeded", "failed", "dry_run"]
    detail: dict
    escalation_trigger_kinds: list[str]   # which 0041 triggers this remediation relates to
    audit_action: str                     # e.g. "self_heal.remediated"

class Remediator(Protocol):
    name: str               # e.g. "stuck_queued"
    target_type: str        # "task" | "pipeline_run"

    def detect(self, db: Session, project_id: str, now: datetime) -> list[Target]: ...
    def remediate(self, db: Session, target: Target, *, mode: Literal["dry_run", "apply"]) -> RemediationOutcome: ...
```

The protocol is intentionally minimal: detect is cheap (one query
per project), remediate is a one-shot transition that either
succeeds or raises. The watchdog handles caps, auditing, and
escalation-close uniformly.

### 2. The watchdog loop

`coder_core/self_heal/watch.py`:

```python
def tick(db_factory, now, *, settings: Settings) -> TickResult:
    if not settings.self_healing_enabled:
        return TickResult(skipped=True, reason="flag_off")

    result = TickResult()
    for project in _active_projects(db_factory()):
        for rem in REMEDIATORS:
            mode = settings.pattern_mode(rem.name)  # 'off' | 'dry_run' | 'apply'
            if mode == "off":
                continue
            with db_factory() as db:
                try:
                    targets = rem.detect(db, project.project_id, now)
                except Exception:
                    structured_log.exception("self_heal.detect_failed",
                                             project=project.project_id, pattern=rem.name)
                    continue
                for target in targets:
                    if _cap_hit(db, target, rem.name, now):
                        _record_skipped(db, target, rem.name, "daily_cap_hit")
                        db.commit()
                        continue
                    try:
                        outcome = rem.remediate(db, target, mode=mode)
                    except Exception as exc:
                        outcome = RemediationOutcome(
                            status="failed", detail={"exc": repr(exc)},
                            escalation_trigger_kinds=[], audit_action="self_heal.failed",
                        )
                    attempt = _record_attempt(db, target, rem.name, outcome)
                    audit = _record_audit(db, target, rem.name, outcome, attempt)
                    if outcome.status == "succeeded":
                        _close_matching_escalations(db, target, rem.name, outcome)
                    db.commit()
                    result.bump(outcome.status)
    return result
```

Per-project per-pattern transaction boundary: a failure in one
remediator never dirties another project's state. Cap lookup +
attempt record + audit + escalation-close all happen in the
same transaction so they commit atomically with the remediation
itself.

### 3. Cap enforcement

```python
def _cap_hit(db, target, pattern_name, now):
    since = now - timedelta(days=1)
    count = db.execute(
        select(func.count(SelfHealAttemptRow.id))
        .where(SelfHealAttemptRow.pattern == pattern_name)
        .where(SelfHealAttemptRow.target_type == target.target_type)
        .where(SelfHealAttemptRow.target_id == target.target_id)
        .where(SelfHealAttemptRow.outcome.in_(["succeeded", "failed", "dry_run"]))
        .where(SelfHealAttemptRow.attempted_at >= since)
    ).scalar()
    return count >= 1
```

One attempt per 24 h per target per pattern. `skipped_cap` rows
don't count toward the cap themselves (otherwise a cap hit would
permanently lock the target out).

### 4. Pattern: `stuck_queued`

```python
class StuckQueued(Remediator):
    name = "stuck_queued"
    target_type = "task"

    def detect(self, db, project_id, now):
        threshold = now - timedelta(minutes=settings.stuck_queued_min_minutes)
        rows = db.execute(
            select(TaskRow)
            .where(TaskRow.project_id == project_id)
            .where(TaskRow.status == "queued")
            .where(TaskRow.created_at <= threshold)
        ).scalars().all()
        # filter: only if DispatcherQueue depth for this project is 0
        depth = _queue_depth(db, project_id)
        if depth != 0:
            return []
        return [Target(project_id=project_id, target_type="task",
                        target_id=str(r.id),
                        detail={"queued_for_minutes": (now - r.created_at).total_seconds() // 60})
                 for r in rows]

    def remediate(self, db, target, *, mode):
        if mode == "dry_run":
            return RemediationOutcome(status="dry_run", detail={}, escalation_trigger_kinds=["stall"],
                                       audit_action="self_heal.remediated")
        task = db.get(TaskRow, UUID(target.target_id))
        if task.status != "queued":
            return RemediationOutcome(status="succeeded",
                                       detail={"noop_reason": f"status={task.status}"},
                                       escalation_trigger_kinds=["stall"],
                                       audit_action="self_heal.remediated")
        dispatch_queue.enqueue(task.id)  # idempotent via task-id key
        return RemediationOutcome(status="succeeded",
                                   detail={"re_enqueued_at": datetime.now(UTC).isoformat()},
                                   escalation_trigger_kinds=["stall"],
                                   audit_action="self_heal.remediated")
```

Zero state mutation on the task row itself; the only side effect
is a re-enqueue which DispatcherQueue collapses to a no-op if the
id is already queued.

### 5. Pattern: `zombie_executing`

```python
class ZombieExecuting(Remediator):
    name = "zombie_executing"
    target_type = "task"

    def detect(self, db, project_id, now):
        stale_cutoff = now - timedelta(seconds=settings.zombie_heartbeat_staleness_seconds)
        rows = db.execute(
            select(TaskRow)
            .where(TaskRow.project_id == project_id)
            .where(TaskRow.status == "executing")
            .where(TaskRow.heartbeat_at < stale_cutoff)
            .where(TaskRow.deadline_at < now)
        ).scalars().all()
        # filter: skip during fleet rollouts
        if _fleet_rollout_in_progress():
            return []
        return [Target(project_id=project_id, target_type="task",
                        target_id=str(r.id),
                        detail={"heartbeat_staleness_seconds": (now - r.heartbeat_at).total_seconds(),
                                "deadline_elapsed_minutes": (now - r.deadline_at).total_seconds() // 60})
                 for r in rows]

    def remediate(self, db, target, *, mode):
        if mode == "dry_run":
            return RemediationOutcome(status="dry_run", detail={},
                                       escalation_trigger_kinds=["stall", "failure_streak"],
                                       audit_action="self_heal.remediated")
        task = db.get(TaskRow, UUID(target.target_id), with_for_update=True)
        if task.status != "executing" or task.heartbeat_at > (datetime.now(UTC) - timedelta(seconds=60)):
            # task recovered; no-op
            return RemediationOutcome(status="succeeded",
                                       detail={"noop_reason": "task_recovered"},
                                       escalation_trigger_kinds=["stall", "failure_streak"],
                                       audit_action="self_heal.remediated")
        # Transition to failed with zombie kind
        task.status = "failed"
        task.failure_kind = "zombie"
        task.failure_detail = {"heartbeat_staleness_seconds": target.detail["heartbeat_staleness_seconds"]}
        # Spawn clone via existing retry endpoint's internal helper
        clone = _clone_for_retry(db, task,
                                  initiator_type="system",
                                  initiator_id="self-healing-watchdog")
        return RemediationOutcome(status="succeeded",
                                   detail={"cloned_task_id": str(clone.id)},
                                   escalation_trigger_kinds=["stall", "failure_streak"],
                                   audit_action="self_heal.remediated")
```

Note: uses `_clone_for_retry` (the helper `POST /tasks/{id}/retry`
already calls) rather than hitting the HTTP endpoint — we're
inside the DB transaction.

### 6. Pattern: `orphan_chain_hook`

```python
class OrphanChainHook(Remediator):
    name = "orphan_chain_hook"
    target_type = "pipeline_run"

    STEP_EXPECTED_NEXT_ROLE = {
        "spec_approval":            "architect",
        "design_approval":          "team_manager",
        "plan_approval":            "developer",
        "all_dev_tasks_accepted":   "pm_accept",
    }

    def detect(self, db, project_id, now):
        cutoff = now - timedelta(minutes=settings.orphan_chain_hook_min_minutes)
        candidates = db.execute(
            select(PipelineRunRow)
            .where(PipelineRunRow.project_id == project_id)
            .where(PipelineRunRow.step.in_(list(self.STEP_EXPECTED_NEXT_ROLE)))
            .where(PipelineRunRow.step_started_at < cutoff)
        ).scalars().all()
        targets = []
        for run in candidates:
            expected_role = self.STEP_EXPECTED_NEXT_ROLE[run.step]
            # orphan if: step advanced past gate, next-role task doesn't exist
            if _next_role_task_exists(db, run.id, expected_role):
                continue
            targets.append(Target(
                project_id=project_id, target_type="pipeline_run",
                target_id=str(run.id),
                detail={"step": run.step, "expected_next_role": expected_role,
                        "step_age_minutes": (now - run.step_started_at).total_seconds() // 60},
            ))
        return targets

    def remediate(self, db, target, *, mode):
        if mode == "dry_run":
            return RemediationOutcome(status="dry_run", detail={},
                                       escalation_trigger_kinds=["stall"],
                                       audit_action="self_heal.remediated")
        run = db.get(PipelineRunRow, UUID(target.target_id), with_for_update=True)
        expected_role = self.STEP_EXPECTED_NEXT_ROLE.get(run.step)
        if expected_role is None:
            return RemediationOutcome(status="succeeded",
                                       detail={"noop_reason": f"step={run.step}"},
                                       escalation_trigger_kinds=["stall"],
                                       audit_action="self_heal.remediated")
        if _next_role_task_exists(db, run.id, expected_role):
            return RemediationOutcome(status="succeeded",
                                       detail={"noop_reason": "next_task_exists"},
                                       escalation_trigger_kinds=["stall"],
                                       audit_action="self_heal.remediated")
        # Replay the chain hook (pure function; creates next task if absent)
        new_task = replay_chain_hook(db, run,
                                      initiator_type="system",
                                      initiator_id="self-healing-watchdog")
        return RemediationOutcome(status="succeeded",
                                   detail={"created_task_id": str(new_task.id)},
                                   escalation_trigger_kinds=["stall"],
                                   audit_action="self_heal.remediated")
```

`replay_chain_hook` is a new helper in `workers/chain.py` that
extracts the existing hook logic (spec-approve → architect-task-
create, etc.) so both the approval endpoint and the self-heal
watchdog call the same function. All four hooks grow the same
"does the next task exist?" early-return so replay is a no-op
when healthy. Idempotency is the precondition for remediate.

### 7. Heartbeat infrastructure

Migration `0049-task-heartbeat`:

```sql
ALTER TABLE tasks
    ADD COLUMN heartbeat_at timestamptz,
    ADD COLUMN deadline_at  timestamptz;
-- heartbeat_at updated periodically during execution; NULL for queued tasks
-- deadline_at = dispatched_at + role_deadline_minutes; immutable once set
```

Worker supervisor wrapper in `coder_core/workers/_runtime.py` (the
same layer as `run_with_transient_retry` from 0027) spawns a
background thread that PATCHes the heartbeat every 30 s:

```python
def with_heartbeat(task_id, broker_token, callable_):
    stop = threading.Event()
    def beat():
        while not stop.is_set():
            _client.patch(f"/v1/projects/{project_id}/tasks/{task_id}/heartbeat",
                          headers={"Authorization": f"Bearer {broker_token}"})
            stop.wait(30)
    t = threading.Thread(target=beat, daemon=True); t.start()
    try:
        return callable_()
    finally:
        stop.set(); t.join(timeout=1)
```

Every role worker's entry point already goes through this wrapper
once 0027 landed; adding the heartbeat thread is a single edit.

The heartbeat endpoint is auth'd via the same impersonation JWT
the worker already carries; it does a tiny UPDATE and returns
204. Not audited (high-volume, low-signal).

### 8. `self_heal_attempts` table (migration 0050)

```sql
CREATE TYPE self_heal_outcome AS ENUM (
    'succeeded',
    'failed',
    'skipped_cap',
    'dry_run'
);

CREATE TABLE self_heal_attempts (
    id                    uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id            text NOT NULL REFERENCES projects(project_id),
    pattern               text NOT NULL,
    target_type           text NOT NULL,
    target_id             text NOT NULL,
    attempted_at          timestamptz NOT NULL DEFAULT now(),
    outcome               self_heal_outcome NOT NULL,
    detail                jsonb NOT NULL DEFAULT '{}'::jsonb,
    audit_event_id        uuid REFERENCES audit_events(id),
    closed_escalation_ids uuid[] NOT NULL DEFAULT ARRAY[]::uuid[]
);

CREATE INDEX self_heal_attempts_cap_idx
    ON self_heal_attempts (pattern, target_id, attempted_at DESC);

CREATE INDEX self_heal_attempts_recent_idx
    ON self_heal_attempts (attempted_at DESC);
```

### 9. Escalation-close integration

```python
def _close_matching_escalations(db, target, pattern_name, outcome):
    trigger_kinds = outcome.escalation_trigger_kinds
    if not trigger_kinds:
        return []
    target_filter = (
        (EscalationRow.pipeline_run_id == UUID(target.target_id))
        if target.target_type == "pipeline_run"
        else (EscalationRow.task_id == UUID(target.target_id))
    )
    rows = db.execute(
        select(EscalationRow)
        .where(EscalationRow.project_id == target.project_id)
        .where(EscalationRow.status == "open")
        .where(EscalationRow.trigger_kind.in_(trigger_kinds))
        .where(target_filter)
        .with_for_update()
    ).scalars().all()
    closed_ids = []
    for esc in rows:
        esc.status = "resolved"
        esc.resolved_at = datetime.now(UTC)
        esc.resolved_by_type = "system"
        esc.resolved_by_id = "self-healing-watchdog"
        esc.resolution = f"{pattern_name} remediated"
        esc.next_rung_due_at = None
        record_audit_event(
            db=db, actor_type="system", actor_id="self-healing-watchdog",
            action="escalation.resolved", target_type="escalation",
            target_id=str(esc.id), project_id=target.project_id,
            before={"status": "open", "rung": esc.current_rung},
            after={"status": "resolved",
                   "resolved_by_id": "self-healing-watchdog",
                   "resolution": esc.resolution},
        )
        closed_ids.append(esc.id)
    return closed_ids
```

The closed-ids are stored on the `self_heal_attempts` row so the
admin UI can link both directions.

### 10. Admin surface

`/admin/self-heal`:
- table of recent attempts (default 7 days), columns: pattern,
  target, outcome, attempted_at, linked audit, linked closed
  escalations.
- filter by pattern, outcome.
- per-pattern mode summary chip ("`stuck_queued`: apply ✓,
  `zombie_executing`: dry_run, `orphan_chain_hook`: off") read
  from the settings endpoint.

Behind `VITE_SELF_HEAL_ENABLED`.

### 11. Terraform

```hcl
# coder-core/infra/terraform/self_heal.tf
resource "google_cloud_run_v2_job" "self_heal_watch" {
  name     = "coder-core-self-heal-watch"
  location = var.region
  template {
    template {
      service_account = google_service_account.self_heal_watch.email
      containers {
        image = var.coder_core_image
        args  = ["python", "-m", "coder_core.self_heal.watch"]
      }
    }
  }
}

resource "google_cloud_scheduler_job" "self_heal_watch" {
  name     = "coder-core-self-heal-watch"
  schedule = "*/5 * * * *"
}

resource "google_service_account" "self_heal_watch" { ... }
```

### 12. Observability

Structured-log events:
- `self_heal.tick_started`
- `self_heal.detected` (pattern, target, project)
- `self_heal.remediated` (outcome, detail, closed_escalations)
- `self_heal.skipped_cap`
- `self_heal.detect_failed`

`/metrics` grows a `self_heal` block:

```json
"self_heal": {
  "attempts_7d": {"stuck_queued": 12, "zombie_executing": 3, "orphan_chain_hook": 1},
  "success_rate_7d": {"stuck_queued": 1.0, "zombie_executing": 0.66, "orphan_chain_hook": 1.0},
  "escalations_prevented_7d": 11,
  "mean_minutes_stuck_to_remediated": 4.2
}
```

## Data flow

### Scenario A — stuck_queued auto-recovery

1. Task `t1` reaches `queued` at T. Dispatcher misses it because
   of a process restart concurrent with enqueue.
2. 15 min pass. Next 5-min tick (T+15 to T+20), `StuckQueued.detect`
   query hits `t1`; DispatcherQueue depth for `coder` is 0.
3. `_cap_hit` returns False (no prior attempts).
4. `remediate` calls `dispatch_queue.enqueue(t1.id)`; idempotent
   no-op if dispatcher now has it, real enqueue if not.
5. `self_heal_attempts` row written (`succeeded`), audit row
   (`self_heal.remediated`, pattern `stuck_queued`, detail
   includes `re_enqueued_at`).
6. `_close_matching_escalations` finds one open `stall`
   escalation for `t1`, closes it with resolved_by_id =
   `self-healing-watchdog`. Audit row.
7. Admin `/admin/self-heal` shows the attempt with a link to the
   closed escalation. Operator wasn't paged at all.

### Scenario B — zombie_executing, heartbeat gone

1. Developer task dispatched at T with a 30-min deadline.
   Claude CLI wedges at T+20; heartbeat stops at T+20:30.
2. At T+33, tick detects: `status='executing'`,
   `heartbeat_at < now-180s`, `deadline_at < now` → eligible.
3. Fleet-rollout check passes.
4. `remediate` takes `FOR UPDATE` on the row. Confirms
   heartbeat_at hasn't moved in the last 60s. Transitions to
   `failed` with `failure_kind='zombie'`, `_clone_for_retry`
   inserts a fresh queued task with the original's prompt,
   spec_id, role, pipeline_run_id.
5. Audit + attempts rows written.
6. Open `stall` escalation on the task closed.

### Scenario C — orphan chain hook after Slack outage

1. Team Manager approves a plan at T. The approval handler
   publishes `knowledge_approved` SSE but the chain hook's
   developer-task creation fails with a transient GitHub 5xx.
   Handler caught the exception, logged
   `chain_hook.failed` + emitted a structured error.
2. Run sits at `plan_approval` with `step_started_at=T`. No
   developer tasks created.
3. At T+10min, next tick: `OrphanChainHook.detect` finds the run.
4. `remediate`: locks row, re-checks next-task existence (still
   absent), calls `replay_chain_hook` which idempotently runs the
   developer-task creation. Success.
5. Audit + attempts written; any open stall escalation closed.

### Scenario D — detection but not safe to remediate (rollout in progress)

1. Zombie detector hits.
2. `_fleet_rollout_in_progress()` returns True because a Cloud
   Run revision change is active.
3. Detector returns empty list; nothing happens. Next tick
   re-checks; rollout complete by then; remediation proceeds.

### Scenario E — remediation fails

1. Stuck queued detected. `dispatch_queue.enqueue` raises because
   the queue has been reconfigured and the method is gone
   (hypothetical refactor bug).
2. The watchdog catches, records `outcome='failed'`, audits
   `self_heal.failed`.
3. No escalation is closed. The 0041 stall escalation continues
   its ladder as if 0042 weren't there. Operator sees the
   `self_heal.failed` in audit + the 0041 page.

## Invariants

1. **One remediation per (target, pattern, day).** Enforced by
   the cap query before `remediate` runs. Second same-day
   detection becomes `skipped_cap`.
2. **Remediate + audit + escalation-close commit atomically.**
   Single transaction per target.
3. **Every remediation is idempotent on re-run.** Verified per-
   pattern above.
4. **Dry-run is side-effect-free.** No task transitions, no
   chain hooks replayed, no escalations closed. Only
   `self_heal_attempts` row + audit row written with
   `outcome='dry_run'`.
5. **The watchdog's tick is bounded.** Per-tick budget caps total
   remediations at `settings.self_heal_tick_budget` (default 20
   across all patterns across all projects) so a mass event
   can't cascade.

## Interfaces

### New files

- `coder-core/src/coder_core/self_heal/__init__.py`
- `coder-core/src/coder_core/self_heal/protocol.py`
- `coder-core/src/coder_core/self_heal/watch.py`
- `coder-core/src/coder_core/self_heal/registry.py`
- `coder-core/src/coder_core/self_heal/patterns/stuck_queued.py`
- `coder-core/src/coder_core/self_heal/patterns/zombie_executing.py`
- `coder-core/src/coder_core/self_heal/patterns/orphan_chain_hook.py`
- `coder-core/src/coder_core/self_heal/models.py`
- `coder-core/src/coder_core/api/heartbeat.py` (PATCH endpoint)
- `coder-core/migrations/0049-task-heartbeat.sql`
- `coder-core/migrations/0050-self-heal-attempts.sql`
- `coder-core/infra/terraform/self_heal.tf`
- `coder-admin/src/admin/self-heal/SelfHealPage.tsx`
- `system/runbooks/self-heal-misfire.md`

### Modified files

- `coder-core/src/coder_core/workers/_runtime.py` — add
  `with_heartbeat` supervisor wrapper; every role worker's
  entry goes through it.
- `coder-core/src/coder_core/workers/chain.py` — extract
  `replay_chain_hook(run)` for shared use by approval handler
  and self-heal.
- `coder-core/src/coder_core/api/tasks.py::_clone_for_retry` —
  expose helper (already internal; promote docstring and a
  small extraction for self-heal callers).
- `coder-core/src/coder_core/dispatcher_queue.py::enqueue` —
  confirm idempotency on `task_id` key.
- `coder-core/src/coder_core/api/audit.py::ALLOWED_ACTIONS` —
  two new actions (`self_heal.remediated`, `self_heal.failed`).
- `coder-core/app.py::Settings` — fleet + per-pattern flags
  and thresholds.
- `coder-admin/src/routes.tsx` — `/admin/self-heal` route.

### New endpoints

- `PATCH /v1/projects/{id}/tasks/{id}/heartbeat` — worker-auth,
  returns 204.
- `GET  /v1/_admin/self-heal/attempts?pattern=&outcome=&since=`
  — admin list for the UI.

### Environment flags

- `CODER_SELF_HEALING_ENABLED` — master (default `false`).
- `SELF_HEAL_PATTERN_STUCK_QUEUED_MODE` (`off` | `dry_run` |
  `apply`, default `off`).
- `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE` (same).
- `SELF_HEAL_PATTERN_ORPHAN_CHAIN_HOOK_MODE` (same).
- `STUCK_QUEUED_MIN_MINUTES` (default 15).
- `ZOMBIE_HEARTBEAT_STALENESS_SECONDS` (default 180).
- `ORPHAN_CHAIN_HOOK_MIN_MINUTES` (default 10).
- `SELF_HEAL_TICK_BUDGET` (default 20).
- `VITE_SELF_HEAL_ENABLED` — frontend visibility.

## Open questions

- **Chain-hook idempotency audit.** Spec's open question #2.
  Design assumes replay is idempotent; needs a per-hook audit:
  (a) spec→architect — idempotent via `architect-for-spec-id`
  uniqueness check that already exists? **verify in impl.**
  (b) design→tm — same. (c) plan→developer fan-out — fan-out
  creates multiple tasks; needs per-task uniqueness on
  `(plan_id, plan_task_index)`. **verify; may need migration to
  add index.** (d) all_dev_accepted→pm_accept — the close-cycle
  backstop from 0044 already runs idempotently, but replay-chain
  needs to hit the same code path.

- **`_fleet_rollout_in_progress` signal source.** Options: read
  Cloud Run revision age from the metadata server; a Redis key
  set by the deploy pipeline; a database row set by the CD
  system (0014 — continuous-deployment). Leaning: the CD system
  writes `deploy_state` rows already; we read the most recent
  and check `state='rolling_out'`. Defer-decision until impl.

- **Per-project self-heal budget.** Currently `SELF_HEAL_TICK_BUDGET`
  is global. Is per-project fairness needed? Leaning no in v1
  (cap is 20/tick and per-pattern per-target-per-day cap limits
  blast radius), but worth noting if a noisy project saturates.

- **Re-opening escalations if remediation was a false-positive.**
  Scenario A/B: if `stuck_queued` reports success but the task
  doesn't actually advance, the 0041 watcher will fire a fresh
  escalation on the next tick. We don't re-open the _same_
  closed escalation. That's intentional (audit clarity) but
  worth stating so operators don't expect re-opens.

- **Heartbeat bombardment on the DB.** 5 workers × per-project
  concurrency × 2 writes/min is modest but non-zero. Consider a
  batching endpoint later if /metrics shows the row updates as
  top writer. Phase-2 optimisation.

## Rollout

### Stage 1 — detect-only shadow (2 weeks)

Ship migrations, watchdog code, all three remediators with mode
`dry_run`. Flip `CODER_SELF_HEALING_ENABLED=true`. Watchdog runs,
logs detections, writes `outcome='dry_run'` rows. No side effects.

Success criterion: detect-rate plausible (not flooding),
false-positive rate low (targets that already recovered by next
tick), no errors. Tune thresholds per-pattern.

### Stage 2 — enable `stuck_queued` apply (week 3)

Flip `SELF_HEAL_PATTERN_STUCK_QUEUED_MODE=apply`. Others remain
`dry_run`. Watch cap-hit rate, success rate, escalations-prevented
metric. 1 week soak.

### Stage 3 — enable `orphan_chain_hook` apply (week 4)

Flip that pattern to `apply` after verifying the chain-hook
idempotency audit in open question #1.

### Stage 4 — enable `zombie_executing` apply (week 5+)

This is the riskiest pattern (it transitions a task to failed +
clones). Flip after verifying the heartbeat wiring is solid on
every worker and the `_fleet_rollout_in_progress` gate reliably
holds during deploys.

## Backout plan

- Fleet: `CODER_SELF_HEALING_ENABLED=false` — watchdog no-ops
  every tick.
- Per-pattern: `SELF_HEAL_PATTERN_{NAME}_MODE=off`.
- Any remediated state can be manually unwound:
  - `stuck_queued` re-enqueue: if caused duplicates, cancel the
    extra task via `/override`.
  - `zombie_executing` clone: the clone is a normal queued task;
    reject it if not wanted, or let it run.
  - `orphan_chain_hook` replay: the created task is a normal one;
    reject if incorrect.
- Tables + Cloud Run Job can be dropped wholesale at major
  version cleanup if the feature is abandoned.
