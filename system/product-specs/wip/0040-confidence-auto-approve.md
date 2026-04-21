---
id: '0040'
title: Confidence-scored auto-approval
type: spec
status: wip
owner: ro
created: 2026-04-19
updated: 2026-04-21
last_verified_at: 2026-04-21
served_by_designs: ['0040']
related_specs:
  - task-orchestration
  - pm-worker
  - architect-worker
  - team-manager-worker
  - audit-log
  - observability
  - admin-panel
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

## Open questions

- **Worker prompt cost for `self_confidence`.** Asking the worker to
  self-grade adds tokens. Preliminary estimate is < 200 tokens per
  output; needs measurement against the shared-context baseline from
  0029 before we call the feature free.

- **Threshold per-project override.** Should a project be able to
  require a _higher_ threshold than fleet (e.g., `coder` wants
  design ≥ 95 not 90)? Leaning yes as a phase-2, not blocking.

- **Risk-flag self-check vs static check.** `novel_component` is a
  judgement call the worker makes; `migration_required` is
  grep-able from the design body. Should the gate handler also
  compute the static flags and OR with the worker's self-reported
  flags? Probably yes — adds a fail-safe against worker
  self-serving scoring. Noted for design.

- **Undo during chain dispatch.** If the tick fires and begins chain
  dispatch at the exact moment a user hits Undo, we race. Design
  should define the resolution — probably: tick takes a SELECT FOR
  UPDATE on the `auto_approvals` row before transitioning, and
  the undo endpoint takes the same lock, so whoever lands first
  wins. Revisit at implementation.

- **Revision task prompt shape.** A manual reject spawns a revision
  task with the reviewer's feedback body; what does an undo spawn?
  Leaning: the operator's optional text body plus a structured
  `undone_reason` (which of the four predicates the operator thinks
  failed — so over time we can build a grader). Revisit in design.

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
