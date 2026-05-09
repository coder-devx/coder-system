---
id: "0071"
title: Failure-mode grouping and operator runbooks
type: design
status: wip
owner: ro
created: 2026-05-09
updated: 2026-05-09
last_verified_at: 2026-05-09
summary: ~
implements_specs: ["0071"]
decided_by: ["0031"]
related_designs:
  - escalations
  - self-healing
  - knowledge-repo-model
  - knowledge-write-api
affects_services:
  - coder-core
  - coder-admin
affects_repos:
  - coder-core
  - coder-admin
  - coder-system
parent: ~
---

# Failure-mode grouping and operator runbooks

## Context

Spec [0071](../../product-specs/wip/0071-failure-mode-grouping-and-runbooks.md)
extends Now (WIP 0070) with a `stuck-group` row that collapses ≥3
open `stuck` tasks sharing a `failure_kind`, plus a failure-mode
runbook subtype under `system/runbooks/failure-modes/`. It also
audits the existing escalation watchdog — the same 27 stuck tasks
that motivate the grouping have produced zero escalations.

Two design questions: (1) the runbook artifact contract, (2) the
bulk-action API and its audit shape, (3) the watchdog rule
extension.

## Goals / non-goals

- **Goals.** Runbook frontmatter with `failure_kind` lookup, bulk
  action endpoints with shared `correlation_id`, watchdog rule that
  fires on observed stuck patterns, "missing runbook" CTA path.
- **Non-goals.** Auto-applying runbook actions. New escalation
  channel. Authoring runbooks in-panel.

## Design

```mermaid
flowchart TB
  tasks[(tasks · stuck)] --> agg[NowAggregator]
  agg -->|group by failure_kind| group[stuck-group row]
  group -->|GET /knowledge/runbooks/by-failure| kapi[Knowledge API]
  kapi --> repo[(coder-system runbooks/failure-modes)]
  group -->|inline retry-all| bulkAPI[Bulk action handler]
  bulkAPI --> tasksvc[Task dispatcher]
  bulkAPI --> audit[audit_events]
  watch[Escalation watchdog] --> tasks
  watch -->|threshold met| esc[escalations]
  esc -. now.changed .-> agg
```

### Components

- **Runbook subtype.** New folder `system/runbooks/failure-modes/`
  in the system repo (and mirrored in `template/`). Each file is
  markdown with frontmatter:

```yaml
id: claude-exit-1               # matches filename
title: Claude exited with code 1
type: runbook
subtype: failure-mode           # discriminator
status: active
owner: ro
last_verified_at: 2026-05-09
failure_kind: claude_exit_1     # matches tasks.failure_kind enum
signal: 'failure_detail =~ "claude exited with code 1"'
suggested_action: retry         # retry | retry_with_edit | escalate | manual_only
owning_role: developer
related_runbooks: []
```

- **Knowledge API extension.**
  `GET /v1/knowledge/runbooks/by-failure?kind=claude_exit_1`. Server
  scans `system/runbooks/failure-modes/`, matches on the
  `failure_kind` frontmatter field, returns the rendered markdown
  body and the frontmatter. 404 with `{next_action: "write-runbook",
  stub_url: "..."}` when no match.
- **Bulk action handler.** `POST /v1/projects/{id}/tasks:bulk-retry`
  accepts `{failure_kind, max_age_seconds}`. Resolves matching open
  stuck tasks, re-enqueues each, writes one `audit_event` per task
  with a shared `correlation_id`. Returns `{retried: N,
  correlation_id, results: [{task_id, status}]}`.
- **NowAggregator.groupBy.** A grouping pass on the `stuck-task`
  feed: rows sharing `(project_id, failure_kind)` collapse to one
  `stuck-group` row when count ≥ 3, with `count`, `oldest_age`,
  `newest_age`. The matched runbook is denormalised into the row's
  `meta` field so the panel can render the runbook panel without
  another fetch.
- **Watchdog rule audit.** The escalation watchdog is reviewed and
  one rule added: "≥3 open stuck tasks sharing a `failure_kind`
  for ≥6h" → opens an escalation. Implemented in the existing
  watchdog module; audited as a documented rule diff in the WIP's
  PR.

### Data flow

Operator clicks `[run runbook]` on a stuck-group row:

1. Frontend opens a confirm modal listing the matched tasks.
2. Operator confirms. Frontend calls
   `POST /v1/projects/{id}/tasks:bulk-retry?failure_kind=claude_exit_1`.
3. Handler resolves open matching tasks, re-enqueues each, writes
   `audit_event(actor=human:{email},
   correlation_id={generated_uuid}, action="task.retry.bulk",
   detail={failure_kind, count})` plus per-task
   `task.retry` events.
4. SSE emits `now.changed` with `removed: [stuck-group-id]` and the
   per-task feeds update too.
5. Frontend toast: "Retried N tasks. Audit chip [01ABCD…]".

### Edge cases

- **Runbook references a `failure_kind` that no longer exists in
  code.** Show as deprecated in the runbook detail page; the
  by-failure lookup never matches. Add a freshness signal that
  flags it in the freshness audit.
- **Race between operator clicking retry-all and the watchdog
  ack-by-resolution.** Both write audit events; the latter
  references the former's correlation if the bulk action resolved
  the underlying tasks first.
- **Runbook missing for an observed `failure_kind`.** UI shows an
  empty-state row in the runbook panel with `[add runbook]` linking
  to a pre-filled stub (frontmatter pre-populated, body empty)
  opened in the existing knowledge editor flow (WIP 0035) or as a
  PR template if that's faster to ship.
- **Runbook authored cross-project.** Failure-mode runbooks live in
  the system-level repo, applicable fleet-wide. Project-specific
  variants live under the per-project knowledge repo and override.
  Resolution order: per-project first, then system. (Same precedence
  as other knowledge artifacts.)

## Open questions

- Threshold and time-window for the new watchdog rule. The numbers
  above (≥3, ≥6h) are starting points; tune in the first 30d soak.
- Whether `bulk-retry` accepts arbitrary task-id lists in addition
  to the `failure_kind` filter. Useful for ad-hoc; probably yes,
  but keep `failure_kind` the canonical group form.
- Per-project runbook precedence ergonomics. Confirm during
  implementation; the resolver is straightforward.

## Rollout

1. Land the runbook subtype + author at least three runbooks
   (`claude-exit-1`, `coder-task-deadline-exceeded`,
   `ship-gate-remote-missing`) in the system repo as one PR.
2. Wire `GET /v1/knowledge/runbooks/by-failure` in `coder-core`.
3. Land the grouping pass in NowAggregator behind a flag. Verify
   the grouped rows match the un-grouped count in shadow.
4. Land bulk-retry endpoint. Test with one operator confirming
   manual on a single project; then enable inline action.
5. Land the watchdog rule diff. Confirm it fires once on the
   observed `coder` stuck pattern; ack from Slack.
6. Flip flag for fleet.

## Links

- Spec: [0071](../../product-specs/wip/0071-failure-mode-grouping-and-runbooks.md)
- ADR: [0031](../../adrs/0031-canonical-project-state-for-operator-surfaces.md)
- Depends on design: [0069](./0069-canonical-project-state.md), [0070](./0070-now-landing-surface.md)
- Services: [coder-core](../../services/coder-core.md), [coder-admin](../../services/coder-admin.md)
