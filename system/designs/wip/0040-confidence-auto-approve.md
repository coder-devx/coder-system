---
id: '0040'
title: Confidence-scored auto-approval
type: design
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
implements_specs: ['0040']
related_designs:
  - worker-communication
  - worker-roles
  - pm-worker
  - architect-worker
  - team-manager-worker
  - audit-log
  - observability-and-cost-tracking
affects_services:
  - coder-core
  - coder-admin
---

# 0040 — Confidence-scored auto-approval (design)

## Context

Spec [0040](../../product-specs/wip/0040-confidence-auto-approve.md)
scopes the "earn auto-approval on the easy cases" feature for the
three worker gates (spec, design, plan). This design describes the
pieces that go in coder-core + coder-admin, the new table, the
evaluator, the tick job, the break-glass endpoints, and the admin
surface — mapped onto the existing Phase 4 dispatcher, approval-gate,
chain-hook, and audit-log plumbing.

Four design invariants shape every part below:

1. **Chain dispatch never runs on a pending auto-approval.** The
   existing chain hook (`on_spec_approved`, `on_design_approved`,
   `on_plan_approved` in `workers/chain.py`) fires off the
   `knowledge_approved` SSE; if the artifact is
   pending-auto-approval we _don't_ publish that SSE until the tick
   finalises.

2. **Every state transition is audited.** Four new action strings
   reuse the 0037 `record_audit_event` helper. No silent rows.

3. **Flag-gated end-to-end.** Flag off == the evaluator short-
   circuits to `Manual(flag_off)` and every gate behaves as it does
   today.

4. **Decision is atomic with the Phase 4 write.** The evaluator runs
   inside the dispatcher's existing Phase 4 transaction; we either
   commit the artifact _and_ the auto-approval row, or neither.

## Goals / non-goals

### Goals

- A single evaluator function produces one decision per artifact
  write, composable with the existing `validate_and_retry` gate.
- The 1-minute tick is a thin reuse of the 0032/0038 Cloud Run Job
  pattern — no new deployment artefact beyond a Terraform entry.
- Undo and accept-now share a lock + state-machine with the tick so
  races are deterministic.
- Workers need no new infrastructure — just a schema bump.

### Non-goals

- Chain-cancellation of already-dispatched downstream tasks. Undo
  only works before chain dispatch.
- A worker framework to grade confidence from artifact content
  externally. The worker self-reports; the gate trusts + applies
  historical calibration.

## Architecture

```mermaid
flowchart TB
  subgraph worker [Worker Phase 4 write]
    wout[worker output JSON]
    sv[validate_and_retry<br/>schema gate from 0025]
    wout --> sv
  end

  subgraph gate [Gate handler]
    write[write artifact to wip/]
    eval[evaluate_auto_approval]
    branch{eligible?}
    man[manual path<br/>emit knowledge_approved SSE<br/>on human /approve]
    auto[pending path<br/>insert auto_approvals row<br/>emit auto_approval_pending SSE]
  end

  sv --> write
  write --> eval
  eval --> branch
  branch -- No --> man
  branch -- Yes --> auto

  subgraph tick ["Cloud Run Job: auto-approve-tick"]
    tloop[1-min loop]
    pick[SELECT FOR UPDATE<br/>WHERE status='pending'<br/>AND window_expires_at < now]
    finalize[transition → applied<br/>emit knowledge_approved<br/>run chain hook<br/>audit]
    tloop --> pick --> finalize
  end

  subgraph admin_api [Break-glass endpoints]
    undo[POST /auto-approvals/:id/undo]
    acceptnow[POST /auto-approvals/:id/accept-now]
    undo --> uaction[SELECT FOR UPDATE row<br/>→ undone<br/>emit knowledge_rejected<br/>spawn revision task<br/>audit]
    acceptnow --> aaction[SELECT FOR UPDATE row<br/>→ applied<br/>emit knowledge_approved<br/>chain hook<br/>audit]
  end

  auto -. 10 min .-> tick
  auto --> undo
  auto --> acceptnow

  subgraph admin_ui [coder-admin]
    card[Pending auto-approval card<br/>on RunDetail + artifact view]
    countdown[live countdown]
    card --> countdown
    card --> undo
    card --> acceptnow
  end

  man --> chain[Chain hook<br/>on_{spec,design,plan}_approved]
  finalize --> chain
  aaction --> chain
```

## Parts

### 1. Worker schema extension

Three JSON schemas in `coder_core/workers/schemas/` gain a required
`self_confidence` block. Bump the `$id` version suffix on each.
`validate_and_retry` needs no changes; retries on missing/invalid
`self_confidence` are the same loop as today's missing-frontmatter
retries.

```python
# coder_core/workers/schemas/_confidence.py
RISK_FLAGS = frozenset({
    "novel_component",
    "cross_tenant_surface",
    "migration_required",
    "external_dependency_added",
    "breaking_api_change",
    "security_boundary_change",
    "large_blast_radius",
})

CONFIDENCE_SCHEMA = {
    "type": "object",
    "required": ["score", "justification", "risk_flags"],
    "properties": {
        "score": {"type": "integer", "minimum": 0, "maximum": 100},
        "justification": {"type": "string", "maxLength": 500},
        "risk_flags": {
            "type": "array",
            "items": {"enum": sorted(RISK_FLAGS)},
            "uniqueItems": True,
        },
    },
    "additionalProperties": False,
}
```

Worker prompt templates are updated in `workers/prompts/pm_draft.md`,
`architect.md`, `team_manager.md` with a short "before you finish"
section telling the worker to self-grade honestly and listing the
risk-flag vocabulary. The static-flag computation (see §4) gives us
a fail-safe if a worker under-reports.

### 2. New table: `auto_approvals`

Migration `0044-auto-approvals` (numbering continues from 0043
secret_rotations):

```sql
CREATE TYPE auto_approval_status AS ENUM (
    'pending',       -- awaiting window close
    'applied',       -- finalized, chain dispatched
    'undone',        -- reverted during window
    'cancelled'      -- (reserved for manual cleanup; unused in v1)
);

CREATE TYPE auto_approval_gate_kind AS ENUM ('spec', 'design', 'plan');

CREATE TABLE auto_approvals (
    id                   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id           text NOT NULL REFERENCES projects(project_id),
    gate_kind            auto_approval_gate_kind NOT NULL,
    artifact_type        text NOT NULL,              -- 'spec' | 'design' | 'task_plan'
    artifact_id          text NOT NULL,              -- id or plan row id
    pipeline_run_id      uuid REFERENCES pipeline_runs(id),
    worker_task_id       uuid REFERENCES tasks(id),  -- the worker that emitted the artifact
    worker_score         integer NOT NULL,
    worker_justification text NOT NULL,
    worker_risk_flags    text[] NOT NULL,
    static_risk_flags    text[] NOT NULL,            -- computed by gate handler (§4)
    historical_rate      real NOT NULL,              -- as of decision time
    historical_window_n  integer NOT NULL,           -- last-N approvals examined
    status               auto_approval_status NOT NULL DEFAULT 'pending',
    window_expires_at    timestamptz NOT NULL,
    decided_at           timestamptz NOT NULL DEFAULT now(),
    applied_at           timestamptz,
    undone_at            timestamptz,
    undone_by_user_id    text,
    undone_reason        text,
    revision_task_id     uuid REFERENCES tasks(id),  -- spawned on undo
    CONSTRAINT window_after_decided CHECK (window_expires_at > decided_at)
);

CREATE INDEX auto_approvals_pending_tick_idx
    ON auto_approvals (window_expires_at)
    WHERE status = 'pending';

CREATE INDEX auto_approvals_project_gate_idx
    ON auto_approvals (project_id, gate_kind, decided_at DESC);
```

Downgrade: `DROP TABLE`, `DROP TYPE`, as always. Coder-core migrates
at startup.

### 3. Per-project opt-in columns

Migration `0045-auto-approve-opt-in`:

```sql
ALTER TABLE projects
    ADD COLUMN auto_approve_spec_enabled    boolean,  -- NULL = inherit fleet
    ADD COLUMN auto_approve_design_enabled  boolean,
    ADD COLUMN auto_approve_plan_enabled    boolean;
```

`PATCH /v1/projects/{id}` gains three optional fields with the same
tri-state shape as `pin_top_tier` and `prompt_caching_enabled` so the
frontend control is a copy-paste of the existing tri-state toggle.

### 4. The evaluator: `evaluate_auto_approval`

Lives in `coder_core/approvals/auto.py`. Invoked from the three gate
handlers (`api/knowledge.py::on_phase4_spec_write`,
`api/knowledge.py::on_phase4_design_write`,
`api/task_plans.py::on_phase4_plan_write`). Single entry point:

```python
def evaluate_auto_approval(
    *,
    db: Session,
    project_id: str,
    gate_kind: Literal["spec", "design", "plan"],
    artifact_body: str,
    worker_confidence: WorkerConfidence,
    settings: Settings,
) -> AutoApprovalDecision:
    if not settings.auto_approve_enabled:
        return Manual("flag_off")

    opt_in = resolve_project_opt_in(db, project_id, gate_kind)
    if not opt_in:
        return Manual("project_opted_out")

    threshold = settings.auto_approve_threshold[gate_kind]
    if worker_confidence.score < threshold:
        return Manual("score_below_threshold")

    static_flags = compute_static_risk_flags(gate_kind, artifact_body)
    all_flags = set(worker_confidence.risk_flags) | set(static_flags)
    if all_flags:
        return Manual("risk_flag_present", flags=sorted(all_flags))

    hist = compute_historical_approval_rate(db, project_id, gate_kind, n=20)
    if hist.n < 5:
        return Manual("insufficient_history", n=hist.n)
    if hist.rate < 0.95:
        return Manual("historical_rate_below_95", rate=hist.rate, n=hist.n)

    return EligibleForAuto(
        window_seconds=settings.auto_approve_window_seconds,  # default 600
        worker_score=worker_confidence.score,
        worker_justification=worker_confidence.justification,
        worker_risk_flags=sorted(worker_confidence.risk_flags),
        static_risk_flags=sorted(static_flags),  # [] at this point
        historical_rate=hist.rate,
        historical_window_n=hist.n,
    )
```

Static-flag computation (the fail-safe):

```python
def compute_static_risk_flags(gate_kind: str, body: str) -> list[str]:
    flags = []
    if gate_kind in ("spec", "design"):
        if re.search(r"^## +Capabilities", body, re.MULTILINE) and \
           "new logical component" in body.lower():
            flags.append("novel_component")
        if re.search(r"POST\s+/v1/projects/\{", body):
            flags.append("cross_tenant_surface")
    if gate_kind == "design":
        if re.search(r"[Mm]igration\s+\d{4}-", body):
            flags.append("migration_required")
        if re.search(r"new\s+(third-party|external)\s+(service|package|dependency)", body, re.I):
            flags.append("external_dependency_added")
    if gate_kind == "plan":
        n_tasks = body.count('"role":')  # crude; plan_json parses the real shape
        if n_tasks > 5:
            flags.append("large_blast_radius")
    return flags
```

The plan-kind flag computation uses the parsed `plan_json`, not a
regex on the body; the regex-y shape above is for illustration. The
real plan handler has the decoded dict available.

Historical-approval-rate query:

```sql
SELECT
    count(*) FILTER (WHERE action = 'knowledge.approve') AS approved,
    count(*) AS total
FROM audit_events
WHERE project_id = :project_id
  AND target_type = :target_type
  AND action IN ('knowledge.approve', 'knowledge.reject')
ORDER BY created_at DESC
LIMIT 20;
```

Needs a `LATERAL` or subquery because `LIMIT` applies before
aggregation — implementation does a `SELECT ... LIMIT 20` in a CTE
and aggregates over the CTE. `target_type` maps gate_kind → spec/
design/task_plan.

### 5. Gate handler integration

Each gate handler grows a thin branch after the Phase 4 write:

```python
def on_phase4_spec_write(spec, worker_output, task, db, settings, correlation_id):
    # ... existing: write to wip/, register, etc.

    decision = evaluate_auto_approval(
        db=db,
        project_id=spec.project_id,
        gate_kind="spec",
        artifact_body=spec.body,
        worker_confidence=worker_output.self_confidence,
        settings=settings,
    )

    if isinstance(decision, EligibleForAuto):
        row = AutoApprovalRow(
            project_id=spec.project_id,
            gate_kind="spec",
            artifact_type="spec",
            artifact_id=spec.id,
            pipeline_run_id=task.pipeline_run_id,
            worker_task_id=task.id,
            worker_score=decision.worker_score,
            worker_justification=decision.worker_justification,
            worker_risk_flags=decision.worker_risk_flags,
            static_risk_flags=decision.static_risk_flags,
            historical_rate=decision.historical_rate,
            historical_window_n=decision.historical_window_n,
            window_expires_at=datetime.now(UTC) + timedelta(seconds=decision.window_seconds),
        )
        db.add(row)
        db.flush()
        record_audit_event(
            db=db,
            actor_type="system",
            actor_id="coder-core",
            action="knowledge.auto_approve_pending",
            target_type="spec",
            target_id=spec.id,
            project_id=spec.project_id,
            correlation_id=correlation_id,
            before=None,
            after={"auto_approval_id": str(row.id), "score": row.worker_score,
                   "window_expires_at": row.window_expires_at.isoformat()},
        )
        publish_sse(
            channel="events",
            event="auto_approval_pending",
            data={"auto_approval_id": str(row.id), "gate_kind": "spec", "artifact_id": spec.id},
        )
        # NOTE: do NOT publish knowledge_approved; do NOT fire chain hook yet.
        return
    # else Manual(...): existing behaviour — publish knowledge.pending, wait for /approve.
    structured_log.info(
        "auto_approve.deferred",
        gate_kind="spec",
        reason=decision.reason,
        **decision.context,
    )
```

Same shape for design + plan handlers. All three live adjacent to the
existing spec/design/plan write code.

### 6. The tick: `coder-core-auto-approve-tick`

Cloud Run Job, Cloud Scheduler ticks every 1 min. Same deployment
shape as 0038's `coder-core-rotate-secrets`. Entry point:

```python
# coder_core/approvals/tick.py
def tick(db: Session, now: datetime, clock_budget: timedelta) -> TickResult:
    deadline = now + clock_budget
    finalised = 0
    errored = 0
    while datetime.now(UTC) < deadline:
        row = db.execute(
            select(AutoApprovalRow)
            .where(AutoApprovalRow.status == "pending")
            .where(AutoApprovalRow.window_expires_at <= now)
            .order_by(AutoApprovalRow.window_expires_at.asc())
            .limit(1)
            .with_for_update(skip_locked=True)
        ).scalar_one_or_none()
        if row is None:
            break
        try:
            _finalize(db, row, actor_type="system", actor_id="coder-core-auto-approve-tick")
            db.commit()
            finalised += 1
        except Exception:
            db.rollback()
            errored += 1
            structured_log.exception("auto_approve_tick.finalize_failed", row_id=str(row.id))
    return TickResult(finalised=finalised, errored=errored)
```

`_finalize` is shared by the tick and `accept-now`:

```python
def _finalize(db, row, *, actor_type, actor_id, user_id=None):
    assert row.status == "pending"
    row.status = "applied"
    row.applied_at = datetime.now(UTC)
    record_audit_event(
        db=db, actor_type=actor_type, actor_id=actor_id,
        action="knowledge.auto_approve_applied",
        target_type=row.artifact_type, target_id=row.artifact_id,
        project_id=row.project_id,
        before={"status": "pending"},
        after={"status": "applied", "applied_at": row.applied_at.isoformat()},
    )
    publish_sse(channel="events", event="knowledge_approved", data={...})
    run_chain_hook(db, row.gate_kind, row.artifact_id, row.project_id)
```

The `skip_locked` + `with_for_update` ensures races against
`accept-now` or `undo` fail safely: whoever holds the row wins, the
other caller gets `None` or `409`.

### 7. Break-glass endpoints

```
POST /v1/projects/{id}/auto-approvals/{auto_approval_id}/undo
POST /v1/projects/{id}/auto-approvals/{auto_approval_id}/accept-now
```

Both live in `api/auto_approvals.py`. `undo`:

```python
@router.post("/auto-approvals/{auto_approval_id}/undo")
def undo(auto_approval_id: UUID, body: UndoBody,
         project_id: str = Depends(require_project_auth),
         user_id: str = Depends(current_user),
         db: Session = Depends(db_session),
         correlation_id: str = Depends(get_correlation_id)):
    row = db.execute(
        select(AutoApprovalRow)
        .where(AutoApprovalRow.id == auto_approval_id)
        .where(AutoApprovalRow.project_id == project_id)
        .with_for_update()
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "not_found")
    if row.status != "pending":
        raise HTTPException(409, f"already_{row.status}")
    row.status = "undone"
    row.undone_at = datetime.now(UTC)
    row.undone_by_user_id = user_id
    row.undone_reason = body.reason or "operator_undone"
    revision = spawn_revision_task(db, row, body)
    row.revision_task_id = revision.id
    record_audit_event(
        db=db, actor_type="user", actor_id=user_id,
        action="knowledge.auto_approve_undone",
        target_type=row.artifact_type, target_id=row.artifact_id,
        project_id=project_id, correlation_id=correlation_id,
        before={"status": "pending"},
        after={"status": "undone", "undone_reason": row.undone_reason,
               "revision_task_id": str(revision.id)},
    )
    publish_sse(channel="events", event="knowledge_rejected", data={...})
    db.commit()
    return AutoApprovalResponse.model_validate(row)
```

`accept-now` follows the same shape, calling `_finalize(... actor_type='user', actor_id=user_id)`.

### 8. Admin surface

One new component in `coder-admin/src/runs/AutoApprovalCard.tsx`
rendered adjacent to the existing `GateCard` in RunDetail, and a
compact variant on the knowledge artifact detail view:

- score + justification in a muted box,
- risk flags if any (with precondition "present = shouldn't be here
  ever" callout — visible indicates a bug, not a normal state),
- live countdown via `setInterval` off `window_expires_at`,
- two buttons: **Undo** (opens a small modal for optional reason +
  spawns revision) and **Accept now**.

Listens on the existing SSE stream for
`knowledge_approved` / `knowledge_rejected` / `auto_approval_pending`
so state flips update without a reload. Behind
`VITE_AUTO_APPROVE_ENABLED`, default on once stage 3 of rollout
flips.

### 9. Terraform

```hcl
# coder-core/infra/terraform/auto_approve.tf
resource "google_cloud_run_v2_job" "auto_approve_tick" {
  name     = "coder-core-auto-approve-tick"
  location = var.region
  template {
    template {
      service_account = google_service_account.auto_approve_tick.email
      containers {
        image = var.coder_core_image
        args  = ["python", "-m", "coder_core.approvals.tick"]
      }
    }
  }
}

resource "google_cloud_scheduler_job" "auto_approve_tick" {
  name     = "coder-core-auto-approve-tick"
  schedule = "* * * * *"  # every minute
  http_target { ... }
}

resource "google_service_account" "auto_approve_tick" { ... }
# SA needs: cloudsql.client, secretmanager.secretAccessor (db password), logging.logWriter
```

The SA is distinct from the app SA and the regression-detector SA
(0032) — matches the one-SA-per-job hygiene from 0005.

### 10. Observability

No new metric schema. Existing `/metrics` endpoint grows three
fields under a new `auto_approve` namespace:

```json
"auto_approve": {
  "rate_by_gate": {"spec": 0.42, "design": 0.18, "plan": 0.31},
  "undo_rate_7d": {"spec": 0.012, "design": 0.0, "plan": 0.027},
  "deferred_reasons_7d": {
    "score_below_threshold": 38,
    "risk_flag_present": 14,
    "historical_rate_below_95": 9,
    "insufficient_history": 21,
    "project_opted_out": 104
  }
}
```

Computed on-demand from `audit_events` and `auto_approvals` — no
rollup table in v1.

### 11. Structured logs

New event shapes, using the existing observability feed:

- `auto_approve.evaluated` — on every gate write: `{gate_kind,
  project_id, decision, reason, score, historical_rate, historical_n}`
- `auto_approve.finalized` — on tick/accept-now:
  `{auto_approval_id, applied_by, latency_ms}`
- `auto_approve.undone` — on undo: `{auto_approval_id, undone_by,
  reason, revision_task_id}`

## Data flow

### Scenario A — happy path, spec auto-approved

1. PM draft task completes Phase 4 write of spec `0050-foo.md`.
2. Spec handler calls `evaluate_auto_approval`:
   - flag on ✓
   - project_id=`coder` has `auto_approve_spec_enabled=true` ✓
   - worker_score=92 ≥ threshold=85 ✓
   - worker_risk_flags=[] ✓, static flags computed = [] ✓
   - historical rate on `coder` specs = 96% over last 20 ✓
3. Returns `EligibleForAuto(window_seconds=600, ...)`.
4. Handler writes `auto_approvals` row (status=pending,
   window_expires_at=now+10min), audit row
   (`knowledge.auto_approve_pending`), SSE
   `auto_approval_pending`. Does NOT publish `knowledge_approved`.
5. Admin RunDetail shows the new card with countdown. Operator
   watches or ignores.
6. 10 minutes elapse. Tick picks the row up,
   `SELECT FOR UPDATE SKIP LOCKED`, transitions to `applied`,
   writes audit (`knowledge.auto_approve_applied`), publishes
   `knowledge_approved`, runs `on_spec_approved` chain hook which
   auto-creates the Architect task as it does today.
7. Admin card flips to "approved" (via the existing SSE path).

### Scenario B — operator undoes mid-window

1-4 as above.
5. At t+6min, operator clicks **Undo** in the card with reason
   "I don't like the Scope section."
6. Endpoint takes `SELECT FOR UPDATE` on the row; status=pending
   ✓. Transitions to undone, spawns a revision PM task with the
   operator's reason as prompt feedback, writes audit
   (`knowledge.auto_approve_undone`), publishes
   `knowledge_rejected`.
7. Admin card flips to "undone; revision task #abc123 spawned."
8. Tick eventually wakes, sees no pending rows past expiry (this
   one's now undone), no-op.

### Scenario C — worker self-reports low confidence

1. Architect design task completes. `worker_score=72` which is below
   the design threshold 90.
2. Evaluator returns `Manual(score_below_threshold)`.
3. Handler falls through to the existing behaviour: publishes
   `knowledge_pending` SSE, waits for human `/approve`. No
   `auto_approvals` row inserted.
4. Structured log emits `auto_approve.evaluated` with the decision;
   `/metrics` buckets this under `score_below_threshold` for
   operator visibility.

### Scenario D — race: tick and accept-now fire simultaneously

1. Tick's `SELECT FOR UPDATE SKIP LOCKED` grabs the row at t=expiry.
2. Operator's accept-now endpoint tries to lock; is blocked until
   tick commits.
3. Tick finalises: status → applied, audit, chain hook, SSE.
4. Accept-now acquires lock: sees `status='applied'`, returns 409
   `already_applied`. Admin panel shows the chain already running;
   the accept-now button was racey but resolved safely.

## Invariants

1. **Chain hook fires exactly once per artifact.** Either on manual
   approve, or on tick-finalise, or on accept-now — never more than
   one of the three.
2. **`knowledge_approved` SSE is published exactly once per
   artifact.** Same as above.
3. **Transition is always `pending → {applied, undone}`.** No back-
   transitions. Enforced by code + `CHECK` constraint can be added
   if needed.
4. **Undo is inert after `applied`.** Returns 409; the chain has
   already dispatched and should be managed via task override
   instead.
5. **Worker retries don't double-write.** `validate_and_retry` is
   upstream of the evaluator; a retry re-runs Phase 4 which
   overwrites the in-progress artifact row but the evaluator runs
   once per _successful_ Phase 4 commit.
6. **Evaluator is deterministic given (artifact, history, settings,
   now).** The inputs are logged so a past decision is reproducible
   for post-mortem.

## Interfaces

### New files

- `coder-core/src/coder_core/approvals/__init__.py`
- `coder-core/src/coder_core/approvals/auto.py` (evaluator)
- `coder-core/src/coder_core/approvals/tick.py` (Cloud Run Job entry)
- `coder-core/src/coder_core/approvals/models.py` (SQLAlchemy row)
- `coder-core/src/coder_core/workers/schemas/_confidence.py`
- `coder-core/src/coder_core/api/auto_approvals.py` (break-glass routes)
- `coder-core/migrations/0044-auto-approvals.sql`
- `coder-core/migrations/0045-auto-approve-opt-in.sql`
- `coder-core/infra/terraform/auto_approve.tf`
- `coder-admin/src/runs/AutoApprovalCard.tsx`
- `coder-admin/src/knowledge/AutoApprovalBadge.tsx`

### Modified files

- `coder-core/src/coder_core/api/knowledge.py` — call evaluator on
  spec + design Phase 4 writes.
- `coder-core/src/coder_core/api/task_plans.py` — call evaluator on
  plan write.
- `coder-core/src/coder_core/api/projects.py::patch_project` —
  expose three new tri-state fields.
- `coder-core/src/coder_core/workers/schemas/pm_draft.json`,
  `architect.json`, `team_manager.json` — embed `self_confidence`.
- `coder-core/src/coder_core/workers/prompts/pm_draft.md`,
  `architect.md`, `team_manager.md` — add self-grade instruction.
- `coder-core/src/coder_core/api/audit.py::ALLOWED_ACTIONS` — four
  new action strings.
- `coder-admin/src/runs/RunDetail.tsx` — mount AutoApprovalCard
  alongside GateCard.
- `coder-admin/src/routes.tsx` — no new routes in v1 (card is
  embedded, not a page).
- `coder-core/app.py::Settings` — new env vars.

### New endpoints

- `POST /v1/projects/{id}/auto-approvals/{auto_approval_id}/undo`
- `POST /v1/projects/{id}/auto-approvals/{auto_approval_id}/accept-now`
- `GET  /v1/projects/{id}/auto-approvals/{auto_approval_id}` (for
  admin card poll fallback; SSE is primary path)

### Environment flags

- `CODER_AUTO_APPROVE_ENABLED` — master switch (default `false`).
- `CODER_AUTO_APPROVE_WINDOW_SECONDS` — default 600.
- `CODER_AUTO_APPROVE_THRESHOLD_SPEC` — default 85.
- `CODER_AUTO_APPROVE_THRESHOLD_DESIGN` — default 90.
- `CODER_AUTO_APPROVE_THRESHOLD_PLAN` — default 80.
- `VITE_AUTO_APPROVE_ENABLED` — frontend visibility.

## Open questions

- **Historical rate bootstrapping for new gate types.** `plan`
  approvals only became audited as of 0037 (2026-04-19). Projects
  with < 5 audited plan approvals will all start `insufficient_history`.
  That's the desired behaviour, but it means `plan` auto-approval
  effectively doesn't activate until a project has been running for
  2-3 weeks post-0037 ship. Flag for rollout plan.

- **Parallel pending approvals.** A single pipeline run can have at
  most one pending spec auto-approval at a time (one spec per run),
  but projects can have several runs concurrently. Pending rows are
  independent — no cross-row locking. The SSE channel is
  fleet-scoped; admin filters by project.

- **Cron granularity.** 1-min Cloud Scheduler is cheap and
  approximate. If operator undo click lands <1s before
  `window_expires_at`, they still win because the lock wait blocks
  the tick. The worst case is a 10-min+up-to-1-min window; that's
  acceptable and within the "≤ 11 min" spec metric.

- **Audit `before` column shape.** For pending→applied transitions,
  `before={"status": "pending"}` is thin. Do we also include
  the worker output snapshot? Leaning: no — the artifact body is
  already in the knowledge repo; duplicating it on `audit_events`
  bloats the table. Cross-reference via `target_id` is enough.

## Rollout

### Stage 1 — schemas + evaluator (shadow), week 1

Ship the migrations (0044, 0045), the schema bump on all three
workers, the evaluator code, the audit action strings. Do not
publish the new SSE or write `auto_approvals` rows yet — the
handler branch is gated behind `auto_approve_enabled && False`. The
structured-log `auto_approve.evaluated` event fires so we get
shadow-mode metrics.

Soak: 3 days. Confirm every Phase 4 write produces a logged
evaluation and no schema-retry storm.

### Stage 2 — enable pending writes, week 2

Flip `CODER_AUTO_APPROVE_ENABLED=true` fleet-wide. Per-project
opt-in stays `NULL` (inherit fleet), but fleet flag is still off,
so effective behaviour is unchanged except now `project_opted_out`
is the logged reason. No pending rows written yet.

Soak: 3 days. Ship admin card in "shadow render" mode (reads the
`audit_events` log of `auto_approve.evaluated` structured events
for diagnostic visibility).

### Stage 3 — enable spec auto-approval for `coder`, week 3

Flip fleet `auto_approve_spec_enabled=true` and set
`coder.auto_approve_spec_enabled=true`. Any spec the PM drafts on
`coder` that passes the four predicates lands as pending; tick
finalises 10 min later.

Watch for 1 week: auto-approve rate, undo rate, downstream developer
success delta. If undo rate < 10% and developer-success delta < 3pp,
proceed.

### Stage 4 — expand, weeks 4-6

Per-gate activation: spec first, then design, then plan. Per-project
roll-out: `coder` first, then opt in others individually. Thresholds
stay at defaults; phase-2 gets a tuning surface.

## Backout plan

- Flip `CODER_AUTO_APPROVE_ENABLED=false`. Immediate effect:
  evaluator returns `Manual(flag_off)`; no new pending rows;
  existing pending rows still finalise on tick (because the tick
  doesn't re-check the flag — that's deliberate, no state stuck in
  pending). If we also want to freeze pending rows, ship a manual
  `UPDATE auto_approvals SET status='cancelled'` playbook step for
  the runbook.
- Per-project opt-out: `PATCH /v1/projects/{id}` with
  `auto_approve_*_enabled=false`. No new pending rows for the
  project.
- The `auto_approvals` table and the three tri-state columns can be
  dropped wholesale at the next major version if the feature is
  abandoned; no other code paths read them.
