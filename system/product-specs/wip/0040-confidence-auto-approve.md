---
id: '0040'
title: Confidence-scored auto-approval
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-27
last_verified_at: 2026-04-27
served_by_designs: ['0040']
related_specs:
  - task-orchestration
  - pm-worker
  - architect-worker
  - team-manager-worker
  - audit-log
  - observability
  - admin-panel
parent: pipeline-operations
---

# 0040 — Confidence-scored auto-approval

## Problem

Three gates on every pipeline run require human approval today: the
PM-drafted spec, the Architect design, and the Team Manager plan.
Many approvals are rubber-stamps — the output is plainly correct, a
human reads it for 90 seconds, clicks approve, and the pipeline moves
on. The friction is real: every gate can add hours of wall-clock
blocking time before the next worker dispatches, and every operator
hour spent rubber-stamping is time not spent on the harder calls.

We want the system to earn auto-approval on the easy cases so humans
focus on the hard ones. "Easy" means the worker is confident, the
project has opted in, the project's recent approval history on this
gate is overwhelmingly positive, and no risk flag tripped. "Hard"
means any of those conditions fail — and then the existing manual
gate runs unchanged.

Auto-approval must be _undoable_: a 10-minute window after
auto-approve lets a human revert with one click before the downstream
chain work dispatches, so a confident-but-wrong artifact doesn't
cascade into developer tasks.

## Users

- **Operator** — today clicks approve 3× per pipeline run; tomorrow
  clicks it only when the system defers. Wants a clear "pending
  auto-approval" indicator on the admin panel with a visible
  countdown and one-click undo.
- **Project owner (per-project opt-in)** — wants to opt their project
  in (or specific gates) only after they trust the worker outputs on
  that project. Tri-state opt-in per gate type.
- **Security-reviewer (from 0039 context)** — needs every
  auto-approval to emit the same audit-event shape as a human
  approval, with the additional fields (`auto_approved=true`,
  `worker_score`, `window_expires_at`, `undone_by`) exposed in the
  audit log.

## Goals

- Cut operator approval load on low-risk artifacts by ~50% without
  measurable degradation in downstream developer-task success rate.
- Zero cascades: an auto-approval that turns out to be wrong never
  reaches a developer worker. The undo window gates chaining.
- Every auto-approval writes an audit row; every undo writes an audit
  row; every override ("accept now" before the window closes) writes
  an audit row. No silent state changes.
- Roll back to full-manual-approval by flipping one flag with zero
  data loss.

## Non-goals

- **Reviewer-verdict auto-approval.** Developer PRs still require the
  reviewer worker's verdict plus, for now, a human merge click.
  Changing that is a separate, harder spec.
- **PM-accept auto-approval.** The PM accept mode already emits
  per-AC verdicts that are effectively a machine check; whether the
  run auto-promotes on full-pass is covered in
  [pm-worker](../active/pm-worker.md) and out of scope here.
- **Cross-project learning.** Historical-approval-rate inputs come
  from the project's own recent audit history only. "Other projects
  approved 95% of similar artifacts" is explicitly out of scope (see
  0048 cross-project patterns for that axis).
- **Self-grading of developer worker output.** Developer success is
  already measured by reviewer verdict + test pass rate; it does not
  need a self-reported confidence score.
- **Automatic _rejection_.** A low confidence score never triggers
  auto-reject — it defers to the human. "Confidence" gates
  auto-approval only.

## Scope

### In scope

1. **Worker self-confidence field.** Extend the existing worker
   output schemas (from spec 0025) for PM-draft, Architect, and Team
   Manager outputs with a required `self_confidence` envelope:
   ```
   self_confidence: {
     score: integer 0-100,
     justification: string (≤ 500 chars),
     risk_flags: array of enum strings (see below)
   }
   ```
   Workers emit this as part of their existing JSON envelope. Schema
   retry budget already applies.

2. **Risk-flag vocabulary.** A small, fixed set of machine-checkable
   flags. At least: `novel_component` (spec introduces a new logical
   component), `cross_tenant_surface` (spec adds a new project-scoped
   endpoint), `migration_required` (design includes a new Postgres
   migration), `external_dependency_added` (design introduces a new
   third-party service or package), `breaking_api_change`,
   `security_boundary_change`, `large_blast_radius` (plan creates
   > 5 developer tasks, or touches > 3 services). Presence of _any_
   flag disables auto-approval for that artifact.

3. **Auto-approval evaluator.** On worker Phase 4 write (after schema
   validation, before the human-gate SSE), the gate handler invokes
   `evaluate_auto_approval(artifact, gate_kind, project_id)` which
   returns either `EligibleForAuto(window_seconds)` or
   `Manual(reason)`. The four predicates:
   - project opt-in for this gate kind is `true`;
   - worker-reported `score` ≥ the resolved fleet threshold for this
     gate kind (defaults: spec 85, design 90, plan 80);
   - project's historical approval rate on this gate kind is ≥ 95%
     over the last `N=20` artifacts (audited via
     `audit_events.action='knowledge.approve'` rows); fewer than
     `N=5` prior artifacts means not-yet-eligible (not-enough-data
     defers to manual);
   - `risk_flags` array is empty.
   All four must hold. Any failure returns `Manual(reason)` and the
   existing human-approval flow runs unchanged.

4. **The 10-minute undo window.** On `EligibleForAuto`, the handler
   writes an `auto_approvals` row with status `pending`, publishes a
   new `auto_approval_pending` SSE event, and _does not_ publish
   `knowledge_approved` yet. Chain dispatch (Architect task, TM task,
   Developer fan-out) waits for the window to close. A 1-minute
   Cloud Scheduler tick finds rows past `window_expires_at`,
   transitions them to `applied`, publishes `knowledge_approved`, and
   runs the same chain hook as a manual approval.

5. **Undo + accept-now.** Two break-glass endpoints on the
   `auto_approvals` row:
   - `POST /v1/projects/{id}/auto-approvals/{id}/undo` — during
     `pending`, transitions to `undone`, publishes
     `knowledge_rejected` with `reason="auto_approval_undone"`,
     spawns a revision task seeded with the operator's optional
     feedback body.
   - `POST /v1/projects/{id}/auto-approvals/{id}/accept-now` —
     during `pending`, transitions to `applied` immediately,
     publishes `knowledge_approved`, runs chain hook. For when the
     operator agrees and wants to skip the 10-minute wait.
   After the tick finalises an `applied` row, undo is refused with
   `409` — once the chain has dispatched, use the normal
   pause/retry/reject flow on the downstream tasks.

6. **Per-project opt-in.** Three tri-state columns on `projects`:
   `auto_approve_spec_enabled`, `auto_approve_design_enabled`,
   `auto_approve_plan_enabled`. `NULL` = inherit fleet default;
   `true` = opt in; `false` = opt out. Fleet default starts `false`
   for all three and flips per-gate only after the shadow-soak data
   is reviewed.

7. **Admin surface.** Gate-adjacent pending-auto-approval card on
   the run-detail view and the knowledge artifact view: score,
   justification, risk flags (none, by precondition), live countdown,
   Undo + Accept-now buttons. Behind `VITE_AUTO_APPROVE_ENABLED`.

8. **Audit.** Four new action strings on `audit_events` (from 0037):
   `knowledge.auto_approve_pending`, `knowledge.auto_approve_applied`,
   `knowledge.auto_approve_undone`, `knowledge.auto_approve_accepted_now`.
   Every state change writes one. `actor_type='system'` for the cron
   finalisation; `actor_type='user'` for the two break-glass endpoints.

### Out of scope

- Tuning the thresholds via the admin panel. For now they live in
  `settings.auto_approve_threshold_{spec,design,plan}` as env vars;
  runtime tuning is a phase-2 enhancement.
- Auto-approval on the _first_ N artifacts of a new project. Every
  project starts with a cold history; the evaluator defers until ≥ 5
  prior audited approvals exist for the gate kind.
- Retroactive evaluation of past artifacts. The feature applies
  forward-only from deploy.

## Acceptance criteria

- **AC1.** The three worker output schemas (`pm_draft`, `architect`,
  `team_manager`) gain a required `self_confidence` block. Schema
  version bumps; validate_and_retry enforces presence.

- **AC2.** The evaluator runs on every Phase 4 write for the three
  gate kinds. Outcome is one `Manual(reason)` or one
  `EligibleForAuto(window_seconds)` per artifact; outcome is logged
  to the structured feed with the reason.

- **AC3.** `EligibleForAuto` writes an `auto_approvals` row with
  `status='pending'`, publishes `auto_approval_pending` SSE, and
  withholds `knowledge_approved` until window close.

- **AC4.** A 1-minute Cloud Scheduler tick finalises expired pending
  rows: transitions to `applied`, writes audit, publishes
  `knowledge_approved`, runs chain hook. Idempotent — a re-tick on
  an already-`applied` row is a no-op.

- **AC5.** Undo endpoint during `pending` reverts to `undone`,
  publishes `knowledge_rejected`, spawns a revision task, writes
  audit. Undo during `applied` returns `409` with
  `reason="already_applied"`.

- **AC6.** Accept-now endpoint during `pending` finalises immediately
  (same shape as tick): `applied`, audit, `knowledge_approved`, chain
  hook.

- **AC7.** Per-project tri-state opt-in (`NULL`/`true`/`false`) on
  three new columns; defaults to inherit fleet flag. `PATCH
  /v1/projects/{id}` supports setting each.

- **AC8.** Historical-approval-rate input computed from the last
  `N=20` `audit_events.action='knowledge.approve'` rows for the
  project + gate kind; strictly < 5 prior approvals = not eligible.

- **AC9.** Every auto-approval lifecycle transition writes an
  `audit_events` row with the `auto_approved=true` detail plus the
  score, justification, and (on undo) the undo reason and spawned
  revision-task id.

- **AC10.** Rolling out: `AUTO_APPROVE_ENABLED` default
  `false`. Stage 1 schema-only, Stage 2 evaluator runs but does not
  publish (shadow). Stage 3 flips the flag and the per-gate
  thresholds one at a time.

- **AC11. (pre-Stage-3)** Static risk-flag check — gate handler
  computes the grep-able subset of `risk_flags`
  (`migration_required`, `external_dependency_added`,
  `large_blast_radius`) from the artifact body / plan and ORs
  with the worker's self-reported flags before evaluating
  predicate 4. Test: a worker that returns `risk_flags=[]` on
  an artifact whose body contains a migration file path lands
  as `Manual(reason="risk_flag_present")` (not auto-approved).

- **AC12. (pre-Stage-3)** Undo / tick race — both the
  `auto_approval_finalise_tick` and `POST .../undo` /
  `POST .../accept-now` endpoints acquire `SELECT FOR UPDATE`
  on the `auto_approvals` row before transitioning. Test:
  concurrent tick + undo on the same `pending` row lands the
  row in exactly one of {`applied`, `undone`}; the loser
  observes the post-transition state and returns the
  appropriate response (tick: no-op; undo: `409
  reason="already_applied"`).

- **AC13.** Revision task spawned on undo carries
  `undone_reason ∈ {score_below_threshold, risk_flag_present,
  historical_rate_below_95, insufficient_history}` (operator-
  selected, optional) plus the operator's optional free-text
  body. Default reason if operator selects none is null.

## Metrics

- **Auto-approve rate per gate kind** — %of artifacts that reached
  `applied` without manual intervention. Fleet + per-project.
- **Undo rate** — % of auto-approved artifacts undone before the
  window closed. Target < 5% fleet-wide on the first 30 days; a
  sustained > 10% is a signal the threshold is too low.
- **Mean wall-clock gate time** — time from worker Phase 4 write to
  chain dispatch. Manual vs auto buckets; target auto bucket ≤ 11
  minutes (10-min window + tick latency).
- **Downstream impact** — developer-task success rate on chains that
  started from auto-approved vs manually-approved spec/design/plan.
  Target no measurable delta; a > 3pp drop is a rollback signal.
- **Deferral reason distribution** — breakdown of
  `Manual(reason)` causes: `score_below_threshold`,
  `risk_flag_present`, `historical_rate_below_95`,
  `insufficient_history`, `project_opted_out`. Operators read this
  to decide whether to lower a threshold or wait.

## Decisions

Resolved 2026-04-27. Three of these (static risk-flag check,
undo/tick race lock, revision task structured `undone_reason`)
are **pre-Stage-3 work** — they need to land before the
fleet flag flips. See AC12 for the static check AC.

- **`self_confidence` token cost — measure now using shadow-mode
  data.** Stage 2 shadow already runs the evaluator on every
  Phase 4 write; pull the per-output `self_confidence`-block
  token counts from the structured-log feed and compare to the
  pre-0040 0029 baseline. If the cost is materially > 200
  tokens, surface to the cost-regression-alert (0032) feed
  before Stage 3 flip.
- **Per-project threshold override — phase-2.** Not v1. A
  project demanding a stricter threshold than fleet is a
  reasonable use case but doesn't block the rollout. Add via
  `projects.auto_approve_*_threshold_override` columns when a
  requesting tenant shows up.
- **Risk-flag static check — yes, gate handler ORs the
  worker's self-report with statically-computed flags.**
  `migration_required`, `external_dependency_added`, and
  `large_blast_radius` are grep-able from the artifact body
  (migration filename present, dependency manifest delta,
  task-count from the plan). Static check is fail-safe against
  worker self-serving scoring. Lands as new AC12 below;
  pre-Stage-3 work.
- **Undo vs tick race — `SELECT FOR UPDATE` on the
  `auto_approvals` row.** Both the tick and the undo endpoint
  acquire the row lock before transitioning state. Whoever
  lands first wins; the loser sees the new state and either
  no-ops (tick on already-undone) or returns 409 (undo on
  already-applied). Lands in implementation; pre-Stage-3 work.
- **Revision task on undo — operator's optional text +
  structured `undone_reason`.** The reason field is a small
  enum of the four predicates (`score_below_threshold`,
  `risk_flag_present`, `historical_rate_below_95`,
  `insufficient_history`) that the operator believes the
  evaluator should have caught. Builds grader data over
  time. Schema change in the revision-task spawn payload.

## Open questions

_None — all resolved. See Decisions above._

## Links

- Related specs:
  [task-orchestration](../active/task-orchestration.md),
  [pm-worker](../active/pm-worker.md),
  [architect-worker](../active/architect-worker.md),
  [team-manager-worker](../active/team-manager-worker.md),
  [audit-log](../active/audit-log.md),
  [observability](../active/observability.md),
  [admin-panel](../active/admin-panel.md)
- Design: [0040](../../designs/wip/0040-confidence-auto-approve.md)
- Roadmap entry: [ROADMAP.md](../ROADMAP.md) → Phase 7 / 0040
