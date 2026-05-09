# Roadmap — phase detail

> Per-phase detail behind [`ROADMAP.md`](./ROADMAP.md). Items here
> describe each WIP's scope, status, and acceptance criteria. When a
> WIP ships, its content folds into one or more `active/` files
> (per AGENTS.md rule 5) and the corresponding entry below is
> trimmed to a one-line shipped reference.
>
> ROADMAP.md carries the at-a-glance view (active components, in-flight
> WIPs, phase status). This file is the drill-down.

## Phase 3 — Scale & Reliability *(complete)*

> Make the pipeline robust, self-healing, and observable at scale.
> Success criteria: zero manual cleanup, <1% task loss from transient
> failures, 3+ pipelines running concurrently without queue starvation.

### 0023 — Branch cleanup GC job (shipped 2026-04-15)

Hourly job deletes stale `task/*` branches older than 24h with no open PR.
Prevents branch proliferation from failed developer tasks.

- **Status:** shipped → [`active/branch-cleanup`](./active/branch-cleanup.md) /
  [`designs/active/branch-cleanup`](../designs/active/branch-cleanup.md)
- **Extends:** `task-orchestration`, `developer-worker`, `observability`

### 0024 — Task Stage Runs API (shipped 2026-04-15)

`GET /v1/projects/{project_id}/tasks/{task_id}/stage-runs` endpoint
returning the archived `TaskStageRunRow` rows for a task, ordered by
`recorded_at` ascending. Debugging-oriented, no admin UI.

- **Status:** shipped → merged into
  [`task-orchestration`](./active/task-orchestration.md) /
  [`worker-communication`](../designs/active/worker-communication.md)
- **Extends:** `task-orchestration`, `observability`

### 0025 — Worker output compliance (shipped 2026-04-17)

Per-worker JSON schemas gate Phase 4 for PM (draft + accept),
Architect, and Team Manager. `validate_and_retry` re-prompts Claude on
schema failure up to a budget; exhaustion lands
`failure_kind="schema"` with zero side effects. Enforcement enabled
after a 48 h shadow soak from the 2026-04-15 deploy.

- **Status:** shipped → merged into
  [`pm-worker`](./active/pm-worker.md),
  [`architect-worker`](./active/architect-worker.md),
  [`team-manager-worker`](./active/team-manager-worker.md),
  [`task-orchestration`](./active/task-orchestration.md) /
  [`pm-worker`](../designs/active/pm-worker.md),
  [`architect-worker`](../designs/active/architect-worker.md),
  [`team-manager-worker`](../designs/active/team-manager-worker.md),
  [`worker-communication`](../designs/active/worker-communication.md).
- **ADR:** [0012 — re-prompt only, no programmatic repair](../adrs/0012-re-prompt-only-worker-output-remediation.md).

### 0026 — Pipeline run dashboard (shipped 2026-04-17)

Admin panel view showing pipeline runs end-to-end: inline Gate card
on `RunDetail` for spec / design / plan approvals without leaving
the run view, sort-by-blocked-longest-first on the Runs list with a
red `blocked Nm` badge per row. Two new timestamp columns on
`pipeline_runs` (`step_started_at` + `blocked_since`), a
`pipeline_step_stats` rollup table, and two new SSE event types
(`pipeline_run.changed` + `.gate_blocked`) back the UX.

- **Status:** shipped → merged into
  [`task-orchestration`](./active/task-orchestration.md),
  [`admin-panel`](./active/admin-panel.md) /
  [`worker-communication`](../designs/active/worker-communication.md).
- **Runbook:** [pipeline-run-blocked](../runbooks/pipeline-run-blocked.md).

### 0027 — Automatic retry on transient failures (shipped 2026-04-17)

Per-worker classify-and-retry loop wraps every role worker's `claude`
spawn. Transient-class failures (429/529/timeout/DNS) retry with
full-jitter exponential backoff inside the worker; budget exhaustion
lands `failure_kind="transient"` with a structured detail, recovered
runs populate `tasks.transient_retry_history` for the admin chip. The
pre-0027 dispatcher-level retry was removed on ship per ADR 0013.

Ship note: the worker internal-timeout signature was changed to
`exit_code=-9 + "coder task deadline exceeded"` so the classifier
doesn't retry our own task-deadline hits as transient (collision
found during the 2026-04-17 trial flip).

- **Status:** shipped → merged into
  [`pm-worker`](./active/pm-worker.md),
  [`architect-worker`](./active/architect-worker.md),
  [`team-manager-worker`](./active/team-manager-worker.md),
  [`developer-worker`](./active/developer-worker.md),
  [`reviewer-worker`](./active/reviewer-worker.md),
  [`task-orchestration`](./active/task-orchestration.md) /
  [`pm-worker`](../designs/active/pm-worker.md),
  [`architect-worker`](../designs/active/architect-worker.md),
  [`team-manager-worker`](../designs/active/team-manager-worker.md),
  [`worker-roles`](../designs/active/worker-roles.md),
  [`worker-communication`](../designs/active/worker-communication.md).
- **ADR:** [0013 — worker-level transient retry](../adrs/0013-worker-level-transient-retry.md).

### 0028 — Concurrent pipeline execution & queue fairness (shipped 2026-04-17)

`DispatcherQueue` sits in front of the global `worker_concurrency`
cap: waiters are queued per-project and admission round-robins across
contending projects so one tenant can't monopolise every slot.
Migration 0027 added the optional `projects.worker_concurrency_soft`
soft cap (yield on contention). Two new queue-depth endpoints
(`/v1/projects/{id}/ops/queue-depth`, `/v1/_admin/ops/queue-depth`)
and two admin surfaces (per-project Queue strip + Fleet queue
widget) surface the dispatcher state.

- **Status:** shipped → merged into
  [`task-orchestration`](./active/task-orchestration.md) /
  [`worker-communication`](../designs/active/worker-communication.md).
- **Runbook:** [concurrency-overflow](../runbooks/concurrency-overflow.md).

### 0051 — coder-core modular monolith hardening (shipped)

Kept `coder-core` as one deployable service, one Postgres schema, and
one test suite, while making its internals a clean modular monolith.
Routers became thin FastAPI/MCP adapters; workflow logic moved into
feature-package application services with visible transaction
ownership; tenant access lives in one canonical helper; the
import-linter contracts in CI hold with zero `ignore_imports`
exceptions; the four extraction-ready protocols (`WorkerDispatcher`,
`EventPublisher`, `AuditRecorder`, `KnowledgeReader`) are plumbed
through `set_*`-swappable singletons, exercised by spy-injection
tests.

Extraction decision (recorded in the design): **not yet**. The bar
for revisiting is documented — cost/scaling differential, independent
deploy/rollback need, or distinct credential scope. None of those
are pressing. When one does appear, the protocol seams mean
extraction is an implementation swap, not a service rewrite.

- **Status:** shipped to prod 2026-04-26 across 5 PRs
  ([coder-core#29](https://github.com/coder-devx/coder-core/pull/29),
  [coder-system#6](https://github.com/coder-devx/coder-system/pull/6),
  [coder-core#30](https://github.com/coder-devx/coder-core/pull/30),
  [coder-system#7](https://github.com/coder-devx/coder-system/pull/7),
  [coder-core#31](https://github.com/coder-devx/coder-core/pull/31)).
  All 11 in-scope ACs done; 1 deferred (freshness-test calendar drift,
  pre-existing concern).
- **Spec:** folded into [delivery-and-infra](./active/delivery-and-infra.md) (PR #54, 2026-05-03) ·
  **Design:** [coder-core-modular-monolith](../designs/active/coder-core-modular-monolith.md)
- **Extends:** `task-orchestration`, `knowledge-api`, `multi-tenancy`,
  `audit-log`, `observability`, role-worker components

---

## Phase 4 — Cost & Token Efficiency *(phase-1 LIVE; phase-2 ready for dispatch)*

> Cut per-pipeline token spend by ~50% without hurting quality. Today
> every worker re-sends the same context; every task runs on the most
> expensive model regardless of complexity. Fix both.

### 0029 — Prompt caching & shared context reuse (phase-1 LIVE, fleet-enabled; phase-2 scope sealed 2026-04-27)

Populate + link + read + gate + per-project override + Slack cache-hit
floor + runbook all live in prod with `PROMPT_CACHING_ENABLED=true`
fleet-wide. Every task now prepends the shared per-run context block
to the system prompt. Validation moves from canary soak to live
measurement: watch `/metrics` `cache_stats` on the admin panel for
hit-rate climb across roles over the next pipeline cycle.
Migrations 0022, 0032-0034.

- **Status:** LIVE (flag on fleet-wide)
- **WIP:** 0029 · **Design:** 0029
- **Extends:** `knowledge-api`, `observability`, `task-orchestration`
- **Next:** ship WIP → active once the input-token-reduction numbers
  stabilise for 24-48 h at the measured rate. That also unblocks
  0030/0031/0032 cross-references from WIP to active docs.

### 0030 — Model tier routing (phase-1 LIVE on canary; phase-2 scope sealed 2026-04-27)

`resolve_tier_model` in the dispatcher + per-role low-tier config
(`worker_model_low_tier_reviewer=claude-haiku-4-5-20251001`) +
per-project pin (`projects.pin_top_tier` tri-state) + `/metrics`
`by_tier` rollup. `tier_routing_enabled=False` fleet-wide; `coder`
project opted in with `pin_top_tier=false`. Reviewer tasks on `coder`
route to Haiku; other projects stay on Sonnet. Migrations 0036, 0037.

- **Status:** LIVE on `coder` canary; fleet flag off
- **WIP:** 0030 · **Design:** 0030
- **Extends:** `task-orchestration`, `observability`
- **Next:** watch `coder` reviewer approval rate in the `by_tier`
  rollup for 48-72 h. If approval rate holds within 1 pp of baseline,
  flip the fleet flag and opt more roles' low-tier configs. Phase 2
  adds the yaml policy table + per-task-kind routing + schema-retry
  escalation.

### 0031 — Per-project token budgets & cost gates (phase-1 LIVE, per-project; phase-2 scope sealed 2026-04-27)

Per-project `budget_{soft,hard}_tokens` tri-state overrides +
`resolve_budget_limits` + dispatcher hard gate + soft-breach Slack
alert with per-month dedupe + `PATCH /v1/projects/{id}` support live.
No project currently sets a limit (every `budget_*_tokens=None`;
fleet defaults also 0 = disabled), so no task is gated yet — the
machinery is ready when ops decides where to set caps. Migration 0035.

- **Status:** LIVE (ready to configure per project)
- **WIP:** 0031 · **Design:** 0031
- **Extends:** `observability`
- **Next:** set realistic soft caps on `coder` (`PATCH
  /v1/projects/coder budget_soft_tokens=<X>`) once the first full
  month of post-caching spend defines a baseline. Phase 2 adds
  rollup table + `status=budget_blocked` + admin override UI +
  monthly reset cron.

### 0032 — Prompt & cost regression alerts (phase-1 LIVE, alerts on; phase-2 scope sealed 2026-04-27)

Detector + `regression_events` persistence + dedupe + acknowledge
flow + `GET|ack` endpoints live with
`REGRESSION_ALERTS_ENABLED=true`. Nightly Cloud Scheduler hook fires
the detector at 04:00 UTC; findings persist to the table and post to
the existing Slack webhook. Acknowledged events stop re-firing.
Migration 0038.

- **Status:** LIVE (flag on fleet-wide)
- **WIP:** 0032 · **Design:** 0032
- **Extends:** `observability`
- **Next:** calibrate the +25% threshold against the first week of
  real alerts. Phase 2 adds `stage_cost_baseline` pre-aggregation +
  commit-range attribution from the continuous-deployment log +
  admin `/metrics/regressions` tab.

---

## Phase 5 — Admin Panel v2: Interactive & Live *(complete)*

> Make the admin panel the thing you keep open all day. Today it's a
> list of rows; it should be a live view of what the system is doing,
> with every common action one keystroke away.

### 0033 — Live pipeline timeline (shipped 2026-04-19)

Replaces the flat task list with a per-run timeline: four horizontal
swim-lanes (pm_draft, architect, team_manager, pm_accept), stage
durations as bars reassembled from `task_stage_runs`, SSE-driven
progress tick via `pipeline_run.changed`, click-through for detail.
New endpoint `GET /v1/projects/{id}/pipeline-runs/{run_id}/timeline`;
no new storage. Admin component behind `VITE_RUN_TIMELINE_ENABLED`.

- **Status:** shipped → merged into
  [`admin-panel`](./active/admin-panel.md),
  [`task-orchestration`](./active/task-orchestration.md) /
  [`worker-communication`](../designs/active/worker-communication.md).

### 0034 — In-panel diff & PR viewer (shipped 2026-04-19)

View PR diffs and the reviewer's verdict/body inline in the admin
panel. New `/tasks/{id}/pr` endpoint parses `pr_url` and fans out
`fetch_pr` + `fetch_pr_diff` GitHubClient calls; frontend
`PrViewer.tsx` renders unified diffs with a custom Tailwind renderer.
Admin component behind `VITE_PR_VIEWER_ENABLED`.

- **Status:** shipped → merged into
  [`admin-panel`](./active/admin-panel.md),
  [`task-orchestration`](./active/task-orchestration.md) /
  [`worker-communication`](../designs/active/worker-communication.md).

### 0035 — Inline knowledge editor with approvals (shipped 2026-04-19)

Edit spec/design markdown body in-browser with live preview; Save
calls the existing `PUT /knowledge/{type}/{id}` (no backend changes).
Approve/reject buttons stay adjacent but disable while there are
unsaved edits. Body-only; frontmatter form deferred to phase 2 per
the original WIP's non-goals. Admin component behind
`VITE_KNOWLEDGE_EDITOR_ENABLED`.

- **Status:** shipped → merged into
  [`admin-panel`](./active/admin-panel.md),
  [`knowledge-api`](./active/knowledge-api.md) /
  [`knowledge-write-api`](../designs/active/knowledge-write-api.md).

### 0036 — Command palette & keyboard-first navigation (shipped 2026-04-19)

`⌘K` / `Ctrl+K` palette portal-mounted at the admin SPA shell: mixed
navigation (projects, tasks, specs, runs) + runnable actions (retry
stuck tasks, grant budget override, open run override) with fuzzy
match and recent-activation boost. Pure frontend — no backend changes.
Behind `VITE_COMMAND_PALETTE_ENABLED`.

- **Status:** shipped → merged into
  [`admin-panel`](./active/admin-panel.md) /
  [`system-overview`](../designs/active/system-overview.md).

---

## Phase 6 — Security & Compliance *(0037 + 0039 shipped; 0038 LIVE-soaking)*

> Close the gap between "it works" and "it's safe to let a customer
> near it." Preparation for external pilots.

### 0037 — Centralized audit log service (shipped 2026-04-19)

Every mutation (approve, reject, override, retry, merge, knowledge
write, impersonation) lands in an append-only `audit_events` log with
actor, project, target, before/after, and correlation ID. Queryable
per-tenant (`/v1/projects/{id}/audit-events`) and fleet
(`/v1/admin/audit-events`). `CorrelationMiddleware` stamps / echoes
`X-Correlation-ID`; `record_audit_event` writes inside the caller's
transaction so mutation + audit row are atomic. Admin `AuditLog.tsx`
page mounted at `/projects/:projectId/audit` and `/admin/audit`.
Migration 0041 (downgrade raises by design). Retention stamp at
`created_at + 365d` (GC is a later spec). Gated on
`CODER_AUDIT_LOG_ENABLED` (default on). New `audit-log` active
component owns the shape; existing components grow Evolution entries
for their mutation-endpoint wirings.

- **Status:** shipped → new [`audit-log`](./active/audit-log.md)
  component / [`audit-log` design](../designs/active/audit-log.md);
  evolution entries added to
  [`admin-panel`](./active/admin-panel.md) (viewer page),
  [`task-orchestration`](./active/task-orchestration.md) (mutation
  wirings), [`impersonation`](./active/impersonation.md) (actor chain
  + issue-token/revoke audits) /
  [`system-overview`](../designs/active/system-overview.md)
  (middleware slot),
  [`worker-communication`](../designs/active/worker-communication.md)
  (task-mutation wirings, worker-initiated correlation fallback),
  [`knowledge-write-api`](../designs/active/knowledge-write-api.md)
  (knowledge-mutation wirings),
  [`impersonation`](../designs/active/impersonation.md) (actor chain
  captured),
  [`observability-and-cost-tracking`](../designs/active/observability-and-cost-tracking.md)
  (adjacent operator surface).

### 0038 — Automated secret rotation (LIVE, first rotation 2026-05-20)

Scheduled rotation of per-project API keys, per-project Anthropic
keys, the admin JWT signing secret, and the shared GitHub App private
key. Zero-downtime rollover via a dual-value window per secret: new
value accepted immediately; old value accepted until a per-kind TTL
elapses, then closed. New `secret_rotations` registry table
(migration 0042) stores canonical name + kind + cadence + dual-value
window + last/next times + last error. New
`projects.api_key_hash_previous` column (migration 0043) backs the
two-key accept window for project API keys. A Cloud Run Job
`coder-core-rotate-secrets` ticks every 15 min via Cloud Scheduler,
rotates anything due, and closes any expired dual-value windows.
Every rotation emits an `audit_events` row (`action=secret.rotate`,
`target_type=secret`). Break-glass endpoint
`POST /v1/_admin/secrets/{canonical_name}/rotate-now` for incident
response. Admin `/admin/secrets` page behind
`VITE_SECRET_ROTATION_ENABLED`. Flag-gated fleet-wide on
`SECRET_ROTATION_ENABLED` (default off on first deploy; flip
per-kind after a shadow soak).

Live state as of 2026-04-21 16:10 UTC: migrations 0042+0043 applied;
four kind rotators live; `tick()` dispatcher + break-glass + admin
endpoints live; admin page live at `/admin/secrets` behind
`VITE_SECRET_ROTATION_ENABLED` (default on); 26 backend + 6 frontend
tests green. Cloud Run Job `coder-core-rotate-secrets` provisioned
(same image + SA as service, entrypoint `python -m
coder_core.rotation.job`); Cloud Scheduler `coder-core-rotate-secrets`
invokes the Job every 15 min via the Cloud Run Admin API;
`SECRET_ROTATION_ENABLED=true` on both service and Job. `GET
/v1/_admin/secrets` returns `enabled: true`. First rotation naturally
due 2026-05-20 (admin JWT, 30-day cadence); GitHub App key due
2026-10-17. Per-project rows: onboarding path (`POST /v1/projects`)
seeds them for new projects; existing-project backfill via
`POST /v1/_admin/secrets/backfill-projects` (idempotent, admin-gated).
Ship into `active/` deferred until a 30-day soak completes past the
first real rotation.

- **Status:** LIVE — scheduler ticking, zero rotations to date
  (nothing due yet; first natural rotation 2026-05-20)
- **WIP:** 0038 · **Design:** 0038
- **Runbook:** [secret-rotation-scheduler](../runbooks/secret-rotation-scheduler.md)
- **Extends:** `service-accounts`, `continuous-deployment`, `admin-panel`, `impersonation`, `audit-log`

### 0039 — Tenant isolation test harness (shipped 2026-04-21)

Continuously-verified isolation across every project-scoped endpoint,
every `project_id`-bearing table, every token type. The harness is a
pytest suite in `coder-core/tests/isolation/` (145 tests), a manifest
YAML as the single source of truth, two drift checks that block CI on
any mismatch, and an admin coverage dashboard at `/admin/isolation`.
Coverage at ship: 54/60 endpoints (6 skipped with explicit reasons),
20/20 tables, 3/3 tokens. AC5 (GCP IAM cross-tenant Secret Manager
reads) deferred to a future CI-staging spec — the three GCP surfaces
are registered with `skip: true` + reasons so the drift check still
fires for new additions. The harness was stricter than the spec's
4-stage ramp called for: the suite ran green on first wire-up, so
`CI_ISOLATION_SUITE_BLOCKING` was never needed — every PR has been
blocking since ship day.

- **Status:** shipped → new [`tenant-isolation`](./active/tenant-isolation.md)
  component / [`tenant-isolation` design](../designs/active/tenant-isolation.md)

---

## Phase 7 — Trusted Autonomy *(0041 + 0042 shipped; 0040 stage-2 shadow; 0049 + 0050 stages 3-4 soaking)*

> Today three gates (spec / design / plan) require human approval
> every run. Many are low-risk rubber-stamps. Let the system earn
> auto-approval on the easy cases so humans focus on the hard ones.

### 0040 — Confidence-scored auto-approval (Stage 2 shadow; OQs resolved 2026-04-27)

PM, Architect, and TM outputs gain a required `self_confidence`
envelope (score, justification, risk_flags from a fixed vocabulary).
An evaluator at each approval gate returns `EligibleForAuto` only
when four predicates hold: project opted in, score ≥ per-gate
threshold (spec 85, design 90, plan 80), last-20 audit-based
historical approval rate ≥ 95% (< 5 prior approvals = insufficient),
and zero risk flags (worker-reported ∪ handler-computed static
flags). On eligibility the handler writes an `auto_approvals` row
(migration 0044) with `status='pending'` and a 10-minute
`window_expires_at`; `knowledge_approved` and chain dispatch are
withheld until a 1-minute Cloud Scheduler tick finalises
(`SELECT FOR UPDATE SKIP LOCKED`) or an operator clicks
`accept-now`. Undo within the window reverts + spawns a revision
task. Per-project tri-state opt-in on three new
`projects.auto_approve_{spec,design,plan}_enabled` columns
(migration 0045). Every transition writes an `audit_events` row
(four new actions). Admin surfaces a pending-auto-approval card
adjacent to the existing Gate card on RunDetail + on knowledge
artifact views behind `VITE_AUTO_APPROVE_ENABLED`. Fleet flag
`AUTO_APPROVE_ENABLED` starts off; 4-stage ramp (shadow →
enable pending writes → `coder` spec only → expand).

Live state as of 2026-04-21: migrations 0044 + 0045 applied; domain
model, evaluator, tick, finalize, undo, accept-now, 4 admin endpoints
all deployed; admin panel pending-approval card live behind
`VITE_AUTO_APPROVE_ENABLED` (default off). Cloud Run Job
`coder-core-auto-approve-tick` + Cloud Scheduler (`* * * * *` UTC)
provisioned on vibedevx; running every minute, currently emitting
`skipped: "disabled"` because `AUTO_APPROVE_ENABLED=false` fleet-wide.
All per-project opt-ins are `NULL`. This is **Stage 1** of the
4-stage rollout — the spec's "schema-only shadow". Stages 2/3 are
product decisions and gated on a green Stage 1 soak; see the
[auto-approve-rollout](../runbooks/auto-approve-rollout.md) runbook
for the flip procedure and the metrics to watch before each advance.

- **Status:** infra wired, Stage 1 shadow (fleet flag off, tick
  ticking, no auto-approvals created)
- **WIP:** 0040 · **Design:** 0040
- **Runbook:** [auto-approve-rollout](../runbooks/auto-approve-rollout.md)
- **Extends:** `task-orchestration`, `observability`, `pm-worker`, `architect-worker`, `team-manager-worker`, `audit-log`, `admin-panel`

### 0041 — Escalation policies & on-call routing (shipped 2026-04-22)

A 1-minute Cloud Run Job `coder-core-escalation-watch` scans three
pipeline-run-shaped trigger conditions — stall, failure-streak, and
SLA wall-clock breach — and advances escalations through a 3-rung
Slack → DM → PagerDuty ladder per the project's `escalation_policy`.
Migrations 0046 (`escalations`), 0047 (`on_call_schedules`), 0048
(seven SLA + routing columns on `projects`). Ack endpoint (API +
Slack interactive button) stops further rungs; resolve closes and
is reused by 0042 self-healing as `actor='system'`. Every state
change writes an `escalation.*` audit row. Admin pages live behind
`VITE_ESCALATIONS_ENABLED`.

- **Status:** shipped → new [`escalations`](./active/escalations.md)
  component / [`escalations` design](../designs/active/escalations.md).
  Evolution entries added to
  [`task-orchestration`](./active/task-orchestration.md) (observation
  surface),
  [`admin-panel`](./active/admin-panel.md) (two admin pages),
  [`audit-log`](./active/audit-log.md) (five new actions +
  `slack_external` actor type).
- **Flag:** `CODER_ESCALATIONS_ENABLED` default off; rollout is
  shadow → L0-only fleet → per-project full ladder opt-in. `coder`
  runs with `escalation_policy='off'` until Stage 3.
- **Runbook:** [escalations-firing](../runbooks/escalations-firing.md)
  (to be authored alongside Stage 2 flip).

### 0042 — Self-healing stuck pipelines (v1 shipped 2026-04-22)

A 5-minute Cloud Run Job `coder-core-self-heal-watch` runs a small
registry of `Remediator`s with a uniform `detect + remediate`
interface; each remediation is _provably safe_ (worst case = no
change). Migration 0049 (`self_heal_attempts`). On a successful
remediation the watchdog enumerates open `escalations` matching the
target and calls `/escalations/{id}/resolve` with
`resolved_by_id='self_healing'` — peer-consumer integration with
0041. Per-pattern mode `off`/`dry_run`/`apply` plus fleet kill switch
`CODER_SELF_HEALING_ENABLED`.

**v1 ships one pattern: `stuck_queued`** (`tasks.status='queued'` >
15 min with `DispatcherQueue.depth(project)=0` and
`worker_concurrency` not pinned → re-enqueue via the existing
idempotent override path). The `zombie_executing` and
`orphan_chain_hook` patterns described in the original WIP are
**deferred** pending the prerequisite surfaces (heartbeat column +
endpoint + supervisor wrapper for zombies; replay-chain endpoint
for orphan chains). Admin `/admin/self-heal` page also deferred
until the fleet flag flips on and there's attempt data worth
surfacing.

- **Status:** shipped (v1) → new
  [`self-healing`](./active/self-healing.md) component /
  [`self-healing` design](../designs/active/self-healing.md).
  Evolution entries added to
  [`task-orchestration`](./active/task-orchestration.md) (reads the
  same observation surface),
  [`audit-log`](./active/audit-log.md)
  (`self_heal.remediated`, `self_heal.failed` actions).
- **Flag:** `CODER_SELF_HEALING_ENABLED` default off; pattern modes
  start in `dry_run` per the rollout stages in the active design.
- **Next:** flip `stuck_queued` to `apply` on `coder` after fleet
  flag on + soak; measure escalation capture rate; then expand the
  pattern registry (zombie + orphan) once the heartbeat +
  replay-chain surfaces land.

### 0049 — MCP agent interface (Stage 1 + 5 Stage 2 slices shipped)

Add an MCP server to `coder-core` so external agents can connect,
authenticate with existing tokens, and drive Coder: read pipeline
state, create tasks, approve plans, impersonate a role, subscribe
to SSE-backed resources. Twelve v1 tools wrap existing HTTP
handlers; the MCP layer is a transport + schema adapter, not a new
permission model (impersonation + audit stay unchanged). Two flags:
`CODER_MCP_ENABLED` (fleet) and `projects.mcp_enabled` (tri-state
per project, Boolean).

**Shipped (2026-04-23 / 24):**

- **Stage 1 — PR #12.** Schema (migration 0051, tri-state
  `projects.mcp_enabled` Boolean), hand-rolled JSON-RPC 2.0
  transport at `/mcp`, auth adapter handling admin JWT + project
  API key, tool registry, `list_tasks` tool end-to-end,
  `mcp.session_opened` audit action. Self-review caught + fixed
  one real bug (HTTPException → -32603 instead of -32602
  translation).
- **Stage 2 reads — PR #13.** Four more read tools (`get_task`,
  `list_pipeline_runs`, `get_pipeline_run`, `get_metrics`).
- **Stage 2 knowledge reads — PR #14.** `list_knowledge` +
  `get_knowledge`, using the process-wide github client directly.
- **Stage 2 first write — PR #15.** `create_task` plus a
  `pydantic.ValidationError` → -32602 handler in the transport.
- **Stage 2 admin toggle endpoint — PR #16.** `POST /v1/_admin/
  projects/{id}/mcp-enabled` + `project.set_mcp_enabled` audit
  action.
- **Stage 2 correlation-ID plumbing + 3 tools — PR #17.**
  `coder_core.mcp.context` contextvar + `request_stub_with_
  correlation_id` helper. Unlocks `approve_task_plan`,
  `reject_task_plan`, and the admin-only `override_pipeline_run`.
- **Stage 2 broker-JWT + `impersonate` — PR #18.** Third bearer
  path on the auth adapter (verify + revocation check), plus the
  impersonation tool that makes agent role-taking end-to-end.
- **Stage 2 `submit_knowledge` — PR #19.** Final v1 tool — one
  tool with a `mode` arg dispatching to create vs update.
- **Stage 2 admin UI — coder-admin #3.** `MCPEnabledCard` on
  ProjectDetail mirroring the AuthModeCard shape, consuming the
  `/mcp-enabled` endpoint.

**All 13 v1 tools live behind the flag** (12 from the spec's
list plus `create_task` which the design split across reads +
writes). Fleet flag `CODER_MCP_ENABLED` stays off until an
external agent is onboarded.

**Remaining Stage 2:**

- SSE subscription resources (three resources over the existing
  `SSEBroker`) — only piece left. Biggest new surface: the current
  transport is one-shot request/response; subscriptions need the
  server to hold a response stream open and push JSON-RPC
  notifications.

- **Status:** Stage 1 + half of Stage 2 shipped
- **WIP:** 0049 · **Design:** 0049
- **Extends:** `impersonation`, `service-accounts`, `audit-log`,
  `admin-panel`, `multi-tenancy`, `task-orchestration`,
  `knowledge-api`

---

## Phase 8 — Knowledge Depth *(0043 + 0044 shipped; 0045 / 0046 / 0047 / 0048 in flight)*

> Make the knowledge repo compound in value. Today it's structured,
> validated (ADR 0008), and atomically written via the Knowledge API.
> It is not yet *fresh*, *auto-captured on ship*, *auto-populated at
> onboarding*, *graph-served*, *migratable across template revisions*,
> or *cross-project-aware*. Each of those is a specific, observable
> gap — not a vague "make it smarter" — and each unlocks a real
> behaviour we want from the system.
>
> Success criteria: `active/` is never more than 48 h behind shipped
> reality; median fleet freshness score trends non-decreasing;
> onboarding a new project produces a populated knowledge repo in a
> single afternoon; Knowledge API can return a traversed subgraph in
> one call; template schema bumps apply across every project without
> hand-editing. Items 0043 and 0044 were small enough to pull forward
> into Phase 3 capacity; both shipped 2026-04-18. Everything else waits
> for this phase.

> **Outermost slice: 0046 alone is worth shipping standalone.** Phase 8
> is the longest, deepest-dependency, and most-novel stretch on the
> roadmap — six items totalling ≥ 4× the architectural surface of any
> earlier phase. The temptation is to wait for the full bundle. Don't.
> 0046 (graph-aware retrieval) ships ≥ 4× speedup on every authoring
> worker and ≥ 6× drop in GitHub Contents calls per task — an
> immediately-felt win that doesn't depend on any other Phase 8 item.
> 0045 (cold-start) is the next-biggest singleton gain (onboarding
> drops from days to one afternoon), and only soft-depends on 0046
> being live. 0047 + 0048 should batch together (template migration
> is the substrate the cross-project pattern indexer uses to propose
> template changes — they form one product surface). Plan around
> three slices, not one.

### 0043 — Knowledge freshness signals (shipped 2026-04-18)

Shipped into `active/` as
[knowledge-freshness](./active/knowledge-freshness.md). Every non-ADR
artifact now carries `last_verified_at`; the Knowledge API envelope
includes `freshness: {score, reasons, …}` on every read;
`min_freshness=N` returns 409 STALE with the body; `POST .../verify`
bumps the date atomically; a nightly audit dispatches the lowest-scored
artifacts to the Architect worker, which emits verified / needs_rewrite
/ uncertain and the consumer calls `.../verify` or files a structured
report. The admin Freshness tab renders the score histogram and
Needs-attention table with one-click Verify.

- **Status:** shipped → [`active/knowledge-freshness`](./active/knowledge-freshness.md)
- **Design:** [`designs/active/knowledge-freshness`](../designs/active/knowledge-freshness.md)

### 0044 — Write-through enforcement on ship (shipped 2026-04-18)

Operationalised AGENTS.md rule 5. The Reviewer worker's output schema
gained a required `ship_attestation`: every AC of the shipping WIP
either names an `active/` artifact + section that now covers it, or
is explicitly dropped with a reason. Team Manager's close-cycle step
now refuses to close while shipped-but-unmerged WIPs exist (fails open
on GitHub errors). `POST /v1/knowledge/ship` performs the full fold
(active updates + WIP delete + both registries) in one atomic Git
Trees commit. Admin panel renders a two-column Ship gate (merges ↔
attestation) on RunDetail. Architect worker ships a
`knowledge-ship-draft` mode that auto-populates the merges column
when `settings.ship_draft_dispatch_enabled` is on.
`scripts/find_orphan_wips.py` supports both report and
`--open-audit` dispatch modes for the one-time fleet sweep.

- **Status:** shipped → folded into
  [`knowledge-api`](./active/knowledge-api.md),
  [`reviewer-worker`](./active/reviewer-worker.md),
  [`team-manager-worker`](./active/team-manager-worker.md),
  [`architect-worker`](./active/architect-worker.md),
  [`admin-panel`](./active/admin-panel.md), and
  [`task-orchestration`](./active/task-orchestration.md)
- **Design:** [`knowledge-write-api`](../designs/active/knowledge-write-api.md)
  (ship endpoint + orphan-WIP query),
  [`team-manager-worker`](../designs/active/team-manager-worker.md)
  (close-cycle backstop),
  [`architect-worker`](../designs/active/architect-worker.md)
  (ship-draft mode)
- **ADR:** [`0015 — ship gate lives in the Coder pipeline`](../adrs/0015-ship-gate-in-coder-pipeline.md)

### 0045 — Cold-start knowledge ingestion (scope sealed 2026-04-27)

A oneshot Cloud Run Job `coder-core-cold-start-ingest` takes
`(project_id, code_repo_url, code_repo_ref)` and produces a single
PR titled `cold-start: <project>` against the new project's
knowledge repo. The job clones, scans (directory tree, READMEs,
language manifests, top-N module docstrings, last 500 commit
messages), buckets into per-scope batches each ≤ 80k input tokens,
dispatches one architect task per batch in a new **`cold-start`
mode** (header `# Knowledge cold start` + new
`architect_cold_start.json` schema emitting `artifacts[]` of
`{artifact_type, artifact_id, body, ingestion_provenance,
confidence}`), then aggregates returns, drops `confidence < 60`,
skips artifacts whose `ingestion_provenance.human_edited == true`
(or absent = human-authored), commits everything via Git Trees on
a `cold-start/<date>-<sha>` branch, and opens the PR. Cross-batch
context-passing (sequential batches; later batches see earlier
artifacts' frontmatter + ids only) keeps an inferred design
referencing an inferred service coherent. **Re-run safety** rests
on a per-knowledge-repo GitHub Action
`flip-cold-start-provenance.yml` (distributed via `template/` for
new projects + a one-time `seed_cold_start_action.py` sweep for
existing) that flips `human_edited: true` on any cold-started
artifact a human commit edits — re-runs then skip those artifacts.
Hard cost ceiling `cold_start_max_tokens` (default 2M+200k); ≥ 40
sub-batches fails fast. Tri-state per-project flags
`cold_start_enabled` + `cold_start_min_confidence` (migration
0053); run-tracking table `cold_start_runs` (migration 0052).
CLI `coder project ingest <slug> --from <url> [--ref <git_ref>]
[--wait]` enqueues + optionally polls; `--status` prints the
latest run. Onboarding runbook gains Step 11 + a new
`cold-start-review.md` runbook walks the operator through PR
review (categories to check, how to read provenance, when to drop
vs edit ADRs). **Specs and runbooks are out of scope** — both
encode intent or operator procedure that can't be inferred from
code; the PM worker authors specs the normal way after onboarding.
Cold-start PRs are never auto-approved (0040 disabled regardless
of project policy). Target: < 50 kLoC repo from
`coder project ingest` to PR open in ≤ 90 min. Rollout:
schemas+templates land first (no behaviour) → driver+endpoint
behind `CODER_COLD_START_ENABLED`=false fleet, `coder` opt-in
true → dry run on `coder` for calibration → Action sweep across
existing repos → fleet flip → admin `/admin/cold-start` UI
behind `VITE_COLD_START_ENABLED`.

- **Status:** drafting
- **WIP:** 0045 · **Design:** 0045
- **Extends:** `onboarding`, `knowledge-api`, `architect-worker`, `knowledge-freshness`

### 0046 — Graph-aware knowledge retrieval (Stage 0a shipped 2026-04-27)

New endpoint `GET /v1/projects/{id}/knowledge/graph` returns the
subgraph reachable from a starting artifact (`?start=<type/id>`)
in a single round-trip, replacing the N+1 walk every authoring
worker does today (architect's pre-claude assembly currently
~30–50 sequential GETs). Bounded BFS with three caps: `depth`
(default 2, hard cap 3), `max_nodes` (default 200, hard cap
500), per-node fan-out cap (50, server-enforced); over-cap
edges land in `truncated_at[]` annotated with reason rather than
5xx-erroring. **Cache-coherence invariant:** the handler resolves
the project's `main` to a commit SHA at request entry and uses
that SHA for every subsequent fetch in the response — two
artifacts in one response can never disagree about each other's
content. **Freshness gating** via `min_freshness=N` (semantics
inherited from 0043): below-floor nodes return as `stub_nodes`
with no body and no out-edge traversal, so workers see "this
branch is stale, I'm seeing it blind" rather than silent
exclusion. Same typed envelope as the existing single-`GET`
shape — workers convert by replacing one helper call, no new
model code. Per-worker conversions: architect (depth=2,
`served_by_designs+related_designs+decided_by`), TM (depth=2,
`decided_by+related_designs+affects_services`), reviewer
(depth=1, `served_by_designs`), PM accept (depth=1,
`related_specs`); each keeps a runtime-flag-gated fallback to
the legacy serial walk for one-week soak before removal.
**Pure logic** in `coder_core/knowledge/graph.py` — `GraphExpander`
takes a fetch callback so it's unit-testable; no I/O. Reuses the
existing TTL cache + parsers + freshness machinery — no new
storage, no precomputed graph, no background indexer.
Tri-state per-project flag `projects.knowledge_graph_enabled`
(migration 0054) + fleet kill switch
`CODER_KNOWLEDGE_GRAPH_ENABLED`. Admin per-artifact "Graph" tab
renders Mermaid via the 0034 PR-viewer's shared renderer behind
`VITE_KNOWLEDGE_GRAPH_ENABLED`. Headline KPI: pre-claude
assembly p50 latency drop from ~6 s to ≤ 1.5 s on `coder` seed
(architect task), ≥ 4× across all four converted workers; secondary:
GitHub Contents calls per task drop from 30+ to ≤ 5. Rollout: ship
endpoint + expander dark → `coder` opt-in → architect conversion
trial-flip → TM/reviewer/PM trial-flips one per day → fleet
flip → admin tab → fallback removal after 1-week soak.

- **Status:** Stage 0a shipped 2026-04-27 ([coder-core#34](https://github.com/coder-devx/coder-core/pull/34))
  — pure-logic `GraphExpander` module + 12 unit tests live in prod.
  No FastAPI route, no migration, no worker conversions yet (those
  are Stage 0b+). Open questions resolved inline at scope-sealing
  (depth=0 semantics, explicit edge_types, truncation reason field,
  stub-no-body, `min_freshness=70` decoupled to a follow-up).
- **WIP:** 0046 · **Design:** 0046
- **Extends:** `knowledge-api`, `knowledge-freshness`, `architect-worker`, `reviewer-worker`, `team-manager-worker`, `pm-worker`

### 0047 — Template schema migration (scope sealed 2026-04-27)

A schema author writes one migration file in
`coder-system/migrations/knowledge/00NN-<slug>.py` (or `.yaml` for
declarative cases — `rename_frontmatter_key`,
`add_frontmatter_key_with_default`, `remove_frontmatter_key`,
`move_folder`, `rename_folder`); a Cloud Run Job
`coder-core-template-migrate` (oneshot + weekly Cloud Scheduler)
applies any pending migration to every managed project as a
**reviewed PR** titled `template-migration: 00NN-<slug>`.
**Per-project `template_version`** at the top of `system/repos.yaml`
records what's applied; a migration with `NUMBER > version`
applies, others skip. **Idempotent** at the row level
(`template_migrations` table, migration 0055, unique on
`(project_id, migration_number, batch_index)`). **Strict
per-project ordering** via Postgres advisory lock keyed on
`hash(project_id)` — migration N's PR must merge before N+1's
opens; failure of N blocks N+1 on that project but not on
other projects. **Pure SDK:** migration files import only
`KnowledgeRepoView` (read-only snapshot) + intent dataclasses
(`FileChange`, `MoveFile`, `DeleteFile`, `RegistryRewrite`),
return `list[change]`; the runner owns Git Trees commit
construction (sharing the helper with 0044's `/ship` endpoint),
PR open via existing helpers, and DB tracking. Per-PR file cap
(`template_migration_max_files_per_pr`=50) + `ALLOW_BATCHING=True`
auto-splits into `-1`, `-2` PRs; only the final batch carries the
`repos.yaml` version bump. **No-op for project** (e.g. migration
touches `services/` and project has no services) opens a
one-line `repos.yaml`-only PR explaining inapplicability —
preserves "every change goes through review" symmetry. **Knowledge
API integration:** `?min_schema_version=N` returns
`409 SCHEMA_DRIFT` with `pending_migrations[]` if project's
version is behind; new `GET /v1/projects/{id}/template/version`;
admin matrix `GET /v1/_admin/template/migrations`. **Per-repo
GitHub Action** `record-template-migration.yml` (distributed
via `template/.github/workflows/` for new + one-time
`seed_template_migration_action.py` sweep for existing) POSTs on
PR merge to flip the row to `merged`. **`coder-system` is
self-hosted** — the schema author updates `template/` + bumps
`coder-system/system/repos.yaml.template_version` in the same PR
as the migration file; the runner only operates on managed
projects (same boundary as ADR 0008's CI validator). **CLI**
`coder migrate test --against ./fixture-repo --migration <path>`
runs a migration against a local fixture repo for the dev loop;
`coder migrate status` prints the matrix. Tri-state
`projects.template_migrations_enabled` (migration 0056) +
`CODER_TEMPLATE_MIGRATIONS_ENABLED` fleet flag. Admin
`/admin/template-migrations` matrix behind
`VITE_TEMPLATE_MIGRATIONS_ENABLED`. **Out of scope:** rewriting
artifact bodies, ADR migrations (append-only by contract), live
read-time transformations (we want explicit drift signal not
silent masking), auto-merging migration PRs (always reviewed).
Headline KPI: median time from migration merged-to-coder-system →
all-projects-merged ≤ 1 week. Rollout: SDK+runner+endpoints land
no migrations → `0001-baseline.py` no-op proves the path → `coder`
opt-in synthetic test → Action distribution sweep → fleet flip →
first real schema change → admin UI on.

- **Status:** drafting
- **WIP:** 0047 · **Design:** 0047
- **Extends:** `knowledge-api`, `onboarding`, `admin-panel`, `audit-log`

### 0048 — Cross-project pattern surfacing (scope sealed 2026-04-27)

A read-only fleet-scoped pattern index produced by a daily Cloud
Run Job `coder-core-pattern-indexer` (03:00 UTC + manual
`POST /v1/_admin/patterns/index/run`). Five v1 pattern kinds:
**`adr`** (Jaccard ≥ 0.5 on tokenised ADR titles across ≥ 2
projects), **`spec_problem`** (Jaccard ≥ 0.4 on `## Problem`
first-paragraph tokens across projects), **`failure_taxonomy`**
(SQL aggregate on `tasks.failure_kind` over 30 days where
`count_distinct(project_id) ≥ 2`), **`role_prompt_delta`** (per
project per role, pre/post approval-rate window 3d/7d around the
latest commit touching the role file, keep where `|Δ| ≥ 3 pp`
and `n ≥ 20`), **`template_drift`** (frontmatter keys present in
a project's `system/<type>/_TEMPLATE.md` but absent centrally).
**Stable `pattern_id` across runs** via a matcher that reuses the
prior id when member-key Jaccard ≥ 0.6, falls back to a
deterministic hash for first-appearance — keeps
`informed_by_patterns` citations resolvable. **Pure structural
similarity in v1**, no embeddings, no LLM (consistent with ADR
0014's freshness rejection of semantic similarity).

**Admin endpoints** at `/v1/_admin/patterns/...` (admin token):
list, detail, index runs, manual run trigger. **Worker consult
endpoint** `GET /v1/projects/{id}/patterns/consult?topic=&kinds=
&max_results=5` is project-token-callable through the
impersonation broker, which attaches a special read-only
`fleet:patterns:consult` scope (whitelisted to this one
endpoint) on outbound. Per-project per-minute rate cap
(`patterns_consult_per_project_per_minute`=30; over → 429
`Retry-After`). Every consult writes a `consultations` row
(migration 0058) plus an `audit_events` row
(`action='pattern.consulted'`).

**Isolation invariant:** the consult endpoint's response model
forbids extra fields and exposes only `(project_id, artifact_id,
decision_pill_or_summary, pattern_id)` per member — no body, no
freshness, no raw frontmatter. To read another project's actual
content, the operator must click through to the admin panel with
their own admin scope. Schema test enforces the invariant on the
Pydantic model. **`informed_by_patterns: [pattern_id]`**
frontmatter (added to design / ADR / spec `_TEMPLATE.md` via a
0047 migration) records what a worker cited; ADR 0008 validator
soft-checks each id resolves against the latest indexer run.

Architect worker's pre-claude assembly gains an opt-in
consultation step (gated on
`architect_pattern_consult_enabled`, default off) when the spec
implies an ADR-warranting decision; cited patterns land as a
`# Cross-project precedent` block in prompt context. PM and
reviewer get the same shape in subsequent phases (ACs deferred).
Admin `/admin/patterns` page (behind
`VITE_FLEET_PATTERNS_ENABLED`) lists the latest run's groups,
sortable by member count, with a `template_drift`-row
"Propose template promotion" button that opens a pre-filled
0047 migration scaffold (the 0048 ↔ 0047 handoff). Tri-state
`projects.fleet_patterns_enabled` (migration 0058) +
`projects.fleet_patterns_index_opt_in` (default true; per-tenant
opt-out) + `CODER_FLEET_PATTERNS_ENABLED` fleet flag. Migrations
0057 (`pattern_groups` + `pattern_index_runs`) + 0058
(`consultations` + projects flags). Headline KPIs: ≥ 30% of
architect tasks producing an ADR call consult; citation rate
(non-empty `informed_by_patterns` among consulted tasks); indexer
wall-clock < 10 min. Rollout: schemas + endpoints behind 404
flag → manual `coder`-only indexer run → second project added →
architect consult flip on `coder` → fleet flip → PM/reviewer
consult → first `template_drift`-driven 0047 promotion.

- **Status:** drafting
- **WIP:** 0048 · **Design:** 0048
- **Extends:** `knowledge-api`, `admin-panel`, `architect-worker`, `pm-worker`, `team-manager-worker`, `reviewer-worker`, `developer-worker`, `multi-tenancy`, `knowledge-freshness`

---

## Cross-cutting pre-work

Items that don't belong to a single phase but unblock multiple WIPs.
Split by status — shipped items below the in-flight set so the
in-flight reads first.

### In flight

### 0052 — Managed-repo GitHub Action distribution (Stage 0 shipped 2026-04-27)

Both 0045 (cold-start)
and 0047 (template
migrations) need the same operational primitive: a per-managed-
repo GitHub Action that POSTs back to coder-core when something
happens in the project's knowledge repo. Without this spec,
each ships its own seed script + receiver pattern and we end
up with two divergent implementations of the same machinery.

0052 extracts the shared primitive — a fleet-manifest
(`coder-system/system/managed-workflows.yaml`), a reusable
`install_workflow` / `verify_workflow` helper in coder-core, a
common HMAC-verifying receiver middleware with handler
registration, and an admin matrix at `/admin/managed-workflows`
showing fleet × workflow installation state. Future managed-
repo callbacks consume the helper without redesigning the
machinery.

**Sequencing.** Lands before 0045 Stage 3 (cold-start Action
distribution sweep) and before 0047 Stage 3 (template-migration
Action distribution sweep). 0045 and 0047 each register one
workflow and one handler against the helper; their Stage 3 work
becomes a one-line manifest entry plus the existing `coder
managed-workflows sync`.

- **Status:** Stage 0 shipped 2026-04-27 across two PRs:
  [coder-system#9](https://github.com/coder-devx/coder-system/pull/9)
  (empty manifest at `system/managed-workflows.yaml`) +
  [coder-core#33](https://github.com/coder-devx/coder-core/pull/33)
  (callback receiver scaffold + register_handler API +
  `CODER_MANAGED_WORKFLOWS_ENABLED` flag). Flag default-off in prod;
  manifest is empty. Stage 1 (install_workflow / verify_workflow /
  iter_managed_workflows helpers + `coder managed-workflows sync`
  CLI) and Stage 2 (admin matrix endpoint + SPA page) still WIP.
  When 0045 (cold-start) and 0047 (template migration) need to
  ship their respective workflows, they consume this helper.
- **WIP:** 0052 · **Design:** 0052
- **Extends:** `knowledge-api`, `onboarding`, `audit-log`, `admin-panel`
- **Unblocks:** 0045, 0047

### 0053 — Post-PR CI fix loop (Stage 0a shipped 2026-04-27)

The developer-worker pipeline today ends at `succeeded|accepted`
once internal pytest passes and the reviewer accepts the PR.
External GitHub Actions checks (ruff format, lint, build,
terraform, deploy) run independently, and their failures are
**not** observed by the orchestrator — once a task is terminal,
the orchestrator stops watching, and a CI-failing PR sits open
with no automated remediation.

Realised pain: PR #34 (0046 GraphExpander, 2026-04-27) succeeded
internally but failed CI on `ruff format --check` — a one-file
whitespace fix that consumed operator time to push manually.

0053 closes the loop with two stages:

- **Stage 0 — pre-flight on the developer worker.** Run
  `uv run ruff format` + `uv run ruff check --fix` (and per-repo
  `preflight_commands`) before `git push`. Cheap prevention:
  most mechanical issues never reach CI.
- **Stage 1 — post-PR CI watcher + fix-up dispatcher.** A new
  `coder_core/integrations/ci_watcher.py` subscribes to GitHub
  `check_run` events on managed PRs; on failure, dispatches a
  fix-up developer task (same branch, no new PR) up to
  `MAX_CI_FIX_ATTEMPTS = 3`; on exhaustion, escalates via 0041's
  on-call routing.

Re-uses 0052's HMAC-webhook pattern. Re-uses 0041's escalation
path. Re-uses spec 0025's `validate_and_retry` shape for the
worker re-prompt.

- **Status:** Stage 0a shipped 2026-04-27 (coder-core#36 — preflight live in prod). Stage 0b (re-prompt path) and Stage 1 (post-PR CI watcher) still WIP.
- **WIP:** 0053 · **Design:** 0053
- **Extends:** `developer-worker`, `reviewer-worker`, `task-orchestration`, `audit-log`, `admin-panel`
- **Closes:** the worker→CI feedback gap surfaced by PR #34

### 0056 — Worker dispatch durability (drafting since 2026-04-28)

Surfaced by the wave-2 dispatch session where ~100% of workers
zombied — Cloud Run service-instance eviction killed the
`asyncio.create_task` orchestrator before the worker could write back.
Three workarounds shipped on the day cover the symptom (Cloud Run
CPU bump to 4 vCPU, reaper apply mode, threshold 25→45 min); this
spec is the architectural fix — workers run as their own Cloud Run
Jobs rather than as asyncio tasks of the HTTP service.

Status note: **drafting since 2026-04-28** — symptom is mitigated in
production, so this hasn't been load-bearing. The right time to
unblock is when (a) symptom recurs despite the workarounds, or (b)
0050 / 0049 graduate from soak and free up dispatch attention. Until
then, 0056 stays drafting; reraise during the next phase-planning
sweep if the workarounds start showing strain.

- **Status:** drafting (5+ days)
- **WIP:** 0056 · **Design:** 0056
- **Extends:** `task-orchestration`, all role workers, `continuous-deployment`, `observability`

---

### Shipped

### 0054 — Orchestrator GitHub-state reconciliation (shipped 2026-04-28, flag on)

The orchestrator's "Fix #3" check (in `workers/orchestrator.py`)
marks a developer task `succeeded|stuck` when the executing stage
reports success but no PR URL was extracted from the worker's
stdout. Realised pain (2026-04-27, task `22089ec6`): Claude wrote
files, committed, pushed the branch, AND opened the PR — but its
final message didn't include the PR URL. `parse_pr_url` returned
None → task row's `pr_url` stayed null → orchestrator's Fix #3
mis-marked the task stuck even though the artifact (a green-CI
mergeable PR) existed. The operator had to manually check GitHub
to discover the divergence.

0054 closes this by having the orchestrator query GitHub for an
open PR on the task's `branch_name` before transitioning to STUCK.
On a worker-authored open PR found, populate `pr_url`, write an
audit row, and let the next orchestrator tick proceed normally.
Read-only against GitHub; flag-gated for shadow rollout; fail-soft
to the existing stuck path on any error.

- **Status:** shipped 2026-04-28 ([coder-core#37](https://github.com/coder-devx/coder-core/pull/37);
  test-skip follow-up [coder-core#38](https://github.com/coder-devx/coder-core/pull/38)
  for an unrelated time-sensitive test).
  `CODER_ORCHESTRATOR_PR_URL_RECONCILE_ENABLED=true` flipped on
  revision `coder-core-00161-ln6`. **Live in prod and reconciling.**
  Architect dispatch (task `62e0c95e`) verified line numbers,
  found existing `GitHubClient.list_pulls` (no new helper needed),
  and produced [ADR 0016](../adrs/0016-bot-identity-via-user-type.md)
  for `user.type == "Bot"` detection. Then TM dispatch
  (task `8932c578`) produced a 5-task plan that the developer
  dispatch implemented one-shot in PR #37.
- **WIP:** 0054 · **Design:** 0054 · **ADR:** [0016](../adrs/0016-bot-identity-via-user-type.md)
- **Extends:** `developer-worker`, `task-orchestration`, `audit-log`
- **Closes:** the "PR exists but task is stuck" failure class
  (eliminated as of 2026-04-28; orchestrator now queries GitHub for
  open PRs on `branch_name` before transitioning to STUCK).

### 0055 — Non-developer-role workers need GitHub write access (shipped 2026-04-28)

Surfaced during the 0054 manual-chain dispatch on 2026-04-27.
Architect task `62e0c95e` ran productively (read the spec, verified
line numbers in orchestrator.py, found existing helpers, made an
ADR-worthy design call about Bot detection) — but exited unable to
open a PR: *"`gh` is unauthenticated and there's no `GH_TOKEN` in
the environment."* The work was lost on container reap.

Root cause: `developer.py` injected `GH_TOKEN` from
`task.workspace.github_token`, but non-developer-role tasks don't
have a workspace configured in the manual-dispatch path. So
architect/TM/PM/reviewer couldn't ship their outputs through PRs.

Fix shipped via [coder-core#41](https://github.com/coder-devx/coder-core/pull/41):
new `workers/_github_env.apply_github_token_env(env, project_id,
settings, *, github_token)` helper sets `GH_TOKEN`; every role
worker calls it before spawning `claude`. The dispatcher resolves
the per-project installation token at dispatch time —
workspace-bearing roles reuse `workspace.github_token`,
non-workspace roles get a knowledge-repo-scoped token via
`tokens.get_token_for_repo(github_org, knowledge_repo)` passed on
`WorkerInput.github_token`. Token-mint failures fall through with a
warning so local-dev paths without a GitHub App still work.
Implementation dispatched directly via the developer worker (the
chicken-and-egg unblock).

- **Status:** shipped 2026-04-28 — all roles can authenticate `gh` without a workspace; covered by `tests/workers/test_github_env.py`
- **PR:** [coder-core#41](https://github.com/coder-devx/coder-core/pull/41)
- **Folded into:** `architect-worker`, `team-manager-worker`, `pm-worker`, `reviewer-worker`, `developer-worker`, `task-orchestration` (specs); `worker-roles`, `architect-worker`, `team-manager-worker`, `pm-worker` (designs)
- **Realised pain:** architect task `62e0c95e` (2026-04-27)

---

## Phase 9 — Operator surface coherence *(drafting since 2026-05-09)*

> Make the admin panel a coherent operator console. One canonical
> project-state read, one actionable landing surface, grouped failure
> modes with runbooks, a real diagnostic view on TaskDetail, drive
> mode in the browser, and a working SpecCompose write path.
>
> Trigger: a 2026-05-09 live walk of the deployed admin found the
> same project quantities reported with different values on different
> pages of the same project (`coder`) — Pipeline `27 stuck`, Inbox
> `27 items`, Fleet `8 blocked`, Escalations `0`, Workers `0/4` idle;
> Cache hit shown as `351301%` on Overview and `366900%` on
> TaskDetail; Metrics `139 = 18 + 8 + ?` with 113 tasks unaccounted.
> Six pages, six different views of the same data, no source of
> truth. Operator must mentally reconcile.
>
> ADR [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md)
> commits to one server-computed canonical read for every operator
> surface; this phase ships under that rule.

### 0069 — Canonical project-state endpoint and consumers (Stage 0a shipped 2026-05-09)

One server-computed `GET /v1/projects/{id}/state` endpoint that every
admin surface reads for project-level counters and cost totals.
Page-local recompute is forbidden going forward. Folds in the
cache-hit-rate unit fix (`[0.0, 1.0]` bound, percentage rendering
fixed once) and the Metrics summary-card math reconciliation
(`total = succeeded + failed + running + queued + stuck + blocked +
paused + cancelled`).

Sibling `GET /v1/admin/state` returns the per-project array plus
fleet totals using the same schema, powering Fleet's stat cards and
table rows. SSE event `project.state.changed` invalidates the
cached browser state.

**Stage 0a shipped 2026-05-09** ([coder-core#188](https://github.com/coder-devx/coder-core/pull/188),
[coder-core#189](https://github.com/coder-devx/coder-core/pull/189)
follow-up isolation manifest registration,
[coder-admin#31](https://github.com/coder-devx/coder-admin/pull/31)):

- `GET /v1/projects/{id}/state` and `GET /v1/_admin/state` live in
  prod with the typed schema in [design 0069](../designs/wip/0069-canonical-project-state.md).
- `cache_hit_rate` is bounded `[0.0, 1.0]` server-side; the legacy
  unit-confusion path (`351301%` / `366900%`) is unreproducible.
- `coder-admin` consumes the endpoint via `useProjectState`:
  `<ProjectStateStrip />` lands at the top of the project page,
  `<ProjectStateHeaderPill />` renders site-wide while inside a
  project, Pipeline's "Retry N stuck" reads `stuck` from canonical
  state instead of a parallel `listTasks(stage='stuck')` call.

**Stage 0b shipped 2026-05-09** ([coder-admin#33](https://github.com/coder-devx/coder-admin/pull/33),
[coder-admin#34](https://github.com/coder-devx/coder-admin/pull/34)):

- ProjectDetail's `<CacheCard/>` reads `cache_hit_rate` from
  canonical state instead of a per-page reducer. The legacy
  unbounded computation (`351301%` / `366900%` / `362526%` on three
  consecutive prod views) is structurally fixed — the live value is
  now bounded by construction.
- Metrics summary cards reconcile against canonical state. The "Total
  / Succeeded / Failed" trio that left 113 of 139 tasks unaccounted
  is replaced by two reconciling rows: period totals on the top row,
  live canonical buckets (running / queued / stuck / blocked) on the
  bottom row.

AC2 ("same int / same string everywhere") now holds across the live
surfaces — STUCK 31 reads identically on the project Overview strip,
the global header pill, the Pipeline "Retry N stuck" button, the
NowBadge, and the Metrics page Stuck card.

Remaining surfaces still on legacy reads (Fleet, Inbox stuck total)
have separate concerns (cross-project aggregation; list length is the
count) and aren't in scope for canonical state migration.

- **Status:** Stage 0a + 0b shipped 2026-05-09 (both halves live and
  reconciling in prod). AC1, AC2, AC3, AC4 satisfied.
- **WIP:** 0069 · **Design:** 0069 · **ADR:** [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- **Extends:** `admin-panel`, `observability`
- **Unblocks:** 0070, 0071, 0072, 0073, 0074

### 0070 — Now landing surface (Stage 1 shipped 2026-05-09)

Default route at `/` is now **Now** — every actionable item across
every project the operator can see, ranked severity × age, with
inline actions per row for the kinds that have clean per-row
endpoints. The previous Projects table moves to `/projects`.
Persistent `<NowBadge/>` shows the count site-wide on every
authenticated route.

**Stage 1 shipped 2026-05-09** ([coder-admin#32](https://github.com/coder-devx/coder-admin/pull/32)):

- `/` route is Now; `/projects` keeps the table.
- Five row kinds reused from the existing inbox aggregator: gate /
  escalation / stuck / regression / paused. Severity ranks urgent →
  high → med → low; ties broken by age oldest-first within tier.
- Inline actions wired for the per-row-endpoint kinds: regression →
  `acknowledgeRegressionEvent`, escalation → `acknowledgeEscalation`,
  paused → `resumeSpecRun`. Stuck and gate rows click through to
  TaskDetail / SpecDetail.
- `<NowBadge/>` polls `/v1/_admin/inbox` every 15s, tints emerald /
  amber / rose by count. Click-through is the implicit `/` link.

**Stage 2 deferred** to follow-up specs and PRs:
- Per-task retry endpoint (the inline retry on stuck rows depends on
  this; today only bulk-retry exists).
- `budget-breach` row kind (extends inbox aggregator with a 6th kind
  reading from the per-project budget cap state).
- `stuck-group` collapsing — depends on spec 0071's failure-mode
  knowledge subtype.
- `Inbox.tsx` deletion (kept as peer surface for now; users can
  still hit `/inbox`).

- **Status:** Stage 1 shipped 2026-05-09; Stage 2 deferred to 0071 + follow-ups
- **WIP:** 0070 · **Design:** 0070 · **ADR:** [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- **Extends:** `admin-panel`, `escalations`, `self-healing`
- **Depends on:** 0069

### 0071 — Failure-mode grouping and operator runbooks (Stages 1 + 2 + 3 shipped 2026-05-09)

Now (0070) collapses ≥3 open `stuck` tasks sharing a
`failure_kind` into one `stuck-group` row with bulk-action buttons
(`retry all`, `run runbook`, `open all`). Failure-mode runbooks live
under `system/runbooks/failure-modes/{slug}.md` with typed
frontmatter (`failure_kind`, `signal`, `suggested_action`,
`owning_role`); `GET /v1/knowledge/runbooks/by-failure?kind=…`
resolves them.

**Stage 1 shipped 2026-05-09** ([coder-system#93](https://github.com/coder-devx/coder-system/pull/93),
[coder-core#193](https://github.com/coder-devx/coder-core/pull/193)):

- New runbook subtype `failure-mode` under
  `system/runbooks/failure-modes/` (mirrored to `template/`). Each
  file's frontmatter carries `failure_kind` (matches
  `tasks.failure_kind` enum), `signal` (regex predicate over
  `failure_detail`), `suggested_action` (`retry` /
  `retry_with_edit` / `escalate` / `manual_only`), `owning_role`.
- Three first runbooks covering 11 of the 27 stuck-task rows
  observed on the 2026-05-09 walk of `coder`:
  `claude-exit-1` (6×), `coder-task-deadline-exceeded` (3×),
  `ship-gate-remote-missing` (2×).
- New endpoint
  `GET /v1/projects/{project_id}/knowledge/runbooks/by-failure?kind=…`
  resolves a `failure_kind` to its matched runbook (frontmatter +
  rendered markdown body). 404 with
  `details.next_action: "write-runbook"` and a `stub_url` when no
  runbook covers the kind — the panel surfaces a CTA at the empty
  state so an operator can author one (AC7).
- Mounted on a dedicated `runbooks_router` BEFORE the main
  knowledge router so the literal `by-failure` segment isn't
  swallowed by the `/{type}/{id}` catch-all.

**Stage 2 shipped 2026-05-09** ([coder-core#194](https://github.com/coder-devx/coder-core/pull/194),
[coder-admin#38](https://github.com/coder-devx/coder-admin/pull/38)):

- New `InboxItemKind.STUCK_GROUP` collapses ≥3 open stuck tasks
  sharing `(project_id, failure_kind)` into a single row.
  Threshold pinned at 3 per the 2026-05-09 walk of `coder` — the
  6 `claude_exit_1` + 3 deadline rows on the live panel collapse
  to 2 group rows. Cohorts <3 pass through as individual rows;
  untagged stuck rows always pass through individually so an
  operator never loses a row to grouping.
- `InboxItem.meta` now optional, carrying `count`, `failure_kind`,
  `oldest_age_iso`, `newest_age_iso`, `task_ids`, `roles` for
  stuck-group rows so the panel can render the count badge + drill
  link without a second fetch.
- New endpoint `POST /v1/projects/{id}/tasks/bulk-retry` accepts
  `{failure_kind, max_age_seconds?}`. Filters open stuck tasks by
  `failure_kind` (with optional age cutoff), retries each, writes
  per-task `TaskLogRow` tagged with the shared `correlation_id`
  so audit-trail readers can fan out from one click. Empty match
  returns `retried=0` cleanly so re-clicks after a partial resolve
  no-op.
- Now renders stuck-group rows distinctly: rose chip "stuck
  group", `×N` count badge inline with the label, `retry all`
  inline action wired to the bulk-retry endpoint, `open →`
  navigates to the project pipeline filtered by failure_kind.

**Stage 3 shipped 2026-05-09** ([coder-core#195](https://github.com/coder-devx/coder-core/pull/195)):

- New escalation detector `detect_stuck_groups` fires on
  `(project_id, failure_kind)` cohorts of ≥3 open stuck tasks
  whose oldest member has been stuck for ≥6h. Untagged stuck
  rows (no `failure_kind`) are deliberately ignored — paging on
  rows with no actionable kind would noise on-call.
- Candidate is keyed to the cohort's oldest task id so the
  existing `(project_id, trigger_kind, task_id)` partial unique
  index dedupes ticks against the same cohort. When the operator
  retries the oldest and a fresh oldest takes its place, the next
  tick opens a follow-on row — same shape as `failure_streak`.
- New `EscalationTrigger.STUCK_GROUP` value + migration 0069
  widening `ck_escalations_trigger_kind` (same shape as 0054
  which added `ci_fix_exhausted`).
- Wired into `scan_triggers` so the existing 1-min watcher tick
  picks it up alongside `stall` / `failure_streak` /
  `sla_breach` / `ci_fix_exhausted`.

This closes the 27-stuck → 0-escalations gap surfaced on the
2026-05-09 walk of `coder`. Threshold + age (3, 6h) pinned per
the spec design; tune on first 30d soak.

**Stage 3 deferred slice:** `/runbooks/{slug}` admin route
rendering the runbook body and an inline `[run on N matched]`
button — operationally useful but not load-bearing for the
watchdog audit. Tracked as a follow-up.

- **Status:** Stages 1 + 2 + 3 shipped 2026-05-09; `/runbooks/{slug}` admin route deferred
- **WIP:** 0071 · **Design:** 0071 · **ADR:** [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- **Extends:** `self-healing`, `escalations`, `observability`, knowledge runbooks
- **Depends on:** 0069, 0070

### 0072 — Task replay and diagnostic surface (Stages 1 + 2 shipped 2026-05-09)

TaskDetail surfaces diagnostic data the orchestrator has been
recording for months — counts only, until now.

**Stage 1 shipped 2026-05-09** ([coder-admin#35](https://github.com/coder-devx/coder-admin/pull/35)):

- **Stage timeline at the top.** Always-expanded horizontal segmented
  bar over `task_stage_runs` (the data already lives in the spec-0024
  endpoint); rose on failure, emerald on success, sky on the current
  stage. Hover shows stage / status / duration / tokens / error.
- **Tool uses panel renders `input_args` per invocation.** The legacy
  panel was counts-only — operators couldn't see what was actually
  called. The aggregate by-tool table stays; below it a per-
  invocation list collapses `input_args` to a one-liner per row and
  expands on click to a pretty-printed JSON block.
- **Logs empty state distinguishes running vs terminal.** Terminal
  tasks now point at the Cloud Run execution + GCS transcript prefix
  instead of saying "No logs yet" (which was misleading on a
  finished task that *had* no captured stdout).

**Stage 2 shipped 2026-05-09** ([coder-core#191](https://github.com/coder-devx/coder-core/pull/191),
[coder-admin#36](https://github.com/coder-devx/coder-admin/pull/36)):

- New endpoint `POST /v1/projects/{id}/tasks/{taskId}/replay`. Body
  `{prompt?, rationale?}`. Empty body delegates to retry; non-empty
  edited prompt writes a `task.replay` audit event (vs `task.retry`)
  and a `replay`-keyed task-log row, so history can tell apart
  "operator clicked retry" from "operator edited and re-dispatched".
  Reuses the existing retry plumbing under the hood — same retry-
  chain pointer (`original_task_id`), same retryability rules, no
  new schema migration.
- **Replay-with-edit modal** on TaskDetail. The button sits next to
  Retry on stuck/rejected tasks; the modal pre-fills the original
  prompt; the dispatch button label tracks the edit state ("Dispatch
  retry" vs "Dispatch replay") so the operator sees what audit shape
  their action will produce.

**Stage 3 deferred** (content-bearing turn rendering): the body of
each Claude turn isn't in `task_turns` today (only `text_length` /
token counts) — the full transcript lives in the GCS prefix
referenced by `tasks.transcript_uri`. Stage 1's GCS deep-link
partially covers that pain; a future PR can lazy-load the JSONL
through a new proxy endpoint when the operator expands a turn row.

- **Status:** Stages 1 + 2 shipped 2026-05-09; Stage 3 deferred
- **WIP:** 0072 · **Design:** 0072 · **ADR:** [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- **Extends:** `admin-panel`, `task-orchestration`, `observability`
- **Depends on:** 0069

### 0073 — Drive mode in the browser (drafting since 2026-05-09)

`/drive/{project}/{role}` route gives the operator an in-browser
takeover surface using the same impersonation token machinery the
CLI already uses. Three-pane layout (role context · conversation ·
scratch + artifact preview), persistent `<SessionBanner/>` with
countdown, audit-event chain per session. `SpecTalk.tsx` (currently
a frozen demo) folds into this surface.

The trust model does not change — drive sessions reuse role-scoped
impersonation tokens (ADR 0006 unchanged). The new entry point is
the surface, not the auth.

- **Status:** drafting since 2026-05-09
- **WIP:** 0073 · **Design:** 0073 · **ADR:** [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- **Extends:** `impersonation`, `admin-panel`, `mcp-agent-interface`
- **Depends on:** 0069

### 0074 — SpecCompose write endpoint and draft hand-off to Now (Stage 1 shipped 2026-05-09)

`POST /v1/projects/{id}/specs` files a spec via PR (branch +
`commit_tree` of artifact + registry + `create_pull_request`),
returning `{spec_id, pr_url, status, branch, path}`. The "Preview
only" banner on `SpecCompose.tsx` is removed; `[file spec]` is
enabled and renders three post-submit states: `saving` (form locked
+ pill), `filed` (emerald success card with [Open PR], [Open spec],
[Start another]), `validation-failed` (rose banner + per-field rose
borders + inline error text anchored by the typed
`SpecComposeFieldError` list under `ApiError.details.errors`).

**Stage 1 shipped 2026-05-09** ([coder-core#192](https://github.com/coder-devx/coder-core/pull/192),
[coder-admin#37](https://github.com/coder-devx/coder-admin/pull/37)):

- New `coder_core.specs.compose` module with `plan_filing` +
  `execute_filing` helpers; `POST /v1/projects/{id}/specs` endpoint.
- Server allocates the next free spec id from the project's
  `system/product-specs/registry.yaml`, renders the artifact
  matching `_TEMPLATE.md` (frontmatter + Problem / Goals / Non-goals
  / Acceptance criteria with `- **ACn.**` bullets / Links), and
  lands artifact + registry update in one atomic `commit_tree` on a
  `spec/{id}-{slug}` branch with one PR opened.
- Validation failures return a typed field-error list under
  `detail.code: "validation_failed"` + `detail.details.errors:
  [{field, code, message}]` (AC4). Concurrent filings collide on
  `branch_already_exists` (AC7) — the panel can re-submit to pick
  up the next free id.
- Frontend wires `[file spec]`, removes the "Preview only" banner,
  renders `saving` / `filed` / `validation-failed` states (AC2,
  AC4). `[save draft]` stays disabled — drafts ship in Stage 2.

**Stage 2 deferred:** drafts (`status: "draft"` payload, no PR;
form preserved); Specs-page draft chip + age + `[resume]`/`[discard]`
on hover; Now `draft-spec` row kind for drafts >24h. The drafts
work needs a persistence model that wasn't in scope for Stage 1.

- **Status:** Stage 1 shipped 2026-05-09; Stage 2 deferred (drafts +
  Specs page draft chip + Now draft-spec row)
- **WIP:** 0074 · **ADR:** [0031](../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- **Extends:** `admin-panel`, `knowledge-api`
- **Depends on:** 0069, 0070

---
