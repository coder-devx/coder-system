---
id: worker-schema-failure
title: Worker schema failure — diagnose and remediate
type: runbook
status: active
owner: ro
created: 2026-04-15
updated: 2026-04-15
last_verified_at: 2026-04-17
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: []
---

# Worker schema failure

Operational guide for tasks that fail with
``failure_kind = "schema"``. The schema gate lives in
[task-orchestration](../product-specs/active/task-orchestration.md)
and the per-worker schemas in [pm-worker](../designs/active/pm-worker.md),
[architect-worker](../designs/active/architect-worker.md), and
[team-manager-worker](../designs/active/team-manager-worker.md).
Rationale in ADR
[0012](../adrs/0012-re-prompt-only-worker-output-remediation.md).

## When to run this

- A PM, Architect, or Team Manager task appears in the admin panel
  with the red **Schema failure** panel.
- The pipeline has stalled at a `draft:` / `accept:` / architect /
  team-manager stage and the operator can see the structured failure.
- `worker_schema_failures_total` spikes in the observability feed.

## Who can run this

Operator with admin JWT. Remediation may need a code change in
`coder-core` (prompt or schema), in which case escalate to the
service owner.

## What the failure means

`failure_kind="schema"` is set only when the worker's claude output
could not be validated after the full retry budget. The model was
re-prompted with the validator errors and still failed. The task has
**no side effects** — no knowledge file, no commit, no `task_plans`
row, no pipeline-chain trigger. Only the `tasks` row itself is
mutated.

`failure_detail` holds:

```json
{
  "error_kind": "schema" | "parse" | "too_large" | "empty" | "schema_load",
  "errors": ["frontmatter/id: 'abc' does not match pattern ^[0-9]{4}$", ...],
  "last_raw": "truncated raw output (≤4 KB)",
  "attempts": 3,
  "schema_version": "v1"
}
```

## Triage

1. **Open the task in the admin panel** (`/tasks/{id}`). The schema
   panel shows the validator errors and the last raw output inline —
   no log dive needed.
2. **Read the top `errors` entry.** It's usually specific enough to
   classify:
   - `frontmatter/*`, `verdicts/*/verdict`, etc. → the model produced
     an output shape the schema rejected.
   - `<root>: top-level JSON must be an object` → the model wrote
     markdown or a list at the top.
   - `invalid JSON: ...` → `error_kind="parse"`; usually a fence or
     preamble. ADR 0012 forbids auto-repair; re-prompt is what
     already happened.
3. **Check `attempts`.** Always `budget + 1`. If you see a different
   number, file a bug — the accounting is off.
4. **Check `schema_version`.** Must match the latest checked-in
   schema under `src/coder_core/workers/schemas/`. If not, a deploy
   lagged the schema update or rolled back — fix the deploy first
   before remediating the prompt.

## Remediation paths

### 1. Re-run (transient model drift)

First response. Costs nothing but tokens.

```sh
curl -X POST -H "Authorization: Bearer $ADMIN_JWT" \
  "$CORE_URL/v1/projects/$PROJECT_ID/tasks/$TASK_ID/override" \
  -d '{"action": "retry"}'
```

Use when:

- The same worker + same prompt has succeeded recently.
- The validator errors look superficial (a single missing field, a
  spurious code fence) and not structural.
- `worker_schema_failures_total` for this worker is flat or
  decreasing — one-off, not a regression.

If the retry also fails schema, do **not** retry again — move on.

### 2. Loosen the schema (format evolution)

The model's new output is legitimately better or the old schema was
too strict.

- Edit `src/coder_core/workers/schemas/<worker>.json`.
- Bump `$id`'s version segment (`v1` → `v2`) — **never** edit a
  published version in place. In-flight tasks keep validating against
  their recorded version.
- Open a PR. Keep the diff tiny so the relaxation is reviewable.
- After merge, re-run failed tasks — they'll pick up the new schema.

Use when:

- The validator errors are consistent across many tasks in a short
  window (look at `failure_detail.errors[0]` across rows).
- The rejected fields are *more* useful than the schema permits (e.g.
  the model started including an extra link field the schema doesn't
  allow).

### 3. Fix the prompt (chronic drift)

The model keeps producing a shape the schema correctly rejects.

- The worker's system prompt lives in the same worker file
  (`workers/pm.py`, `workers/architect.py`, `workers/team_manager.py`).
- Read the last-raw snippet and the prompt side-by-side. Usually the
  drift is a prompt instruction the model is ignoring (e.g. "respond
  with ONLY JSON" being overridden by a tool-use trajectory that
  emits explanatory markdown).
- Tighten the prompt; add a negative example if useful. Reference the
  `docs/prompt-best-practices.md` guide if one exists for the role.
- Open a PR. Include the `failure_detail` that motivated the change
  in the PR body so the reviewer can judge.

Use when:

- The same validator errors appear across multiple tasks over more
  than a day.
- The retry-success rate for this worker drops below 30% on the
  observability dashboard.

## Escalation

If step 1 fails, step 2 is ambiguous (schema *might* be too strict),
and the prompt looks fine — open an incident. The combination usually
means either a model version regression or an infrastructure change
has altered what reaches the worker (truncated prompt, env var
missing, etc.).

## Related

- Spec: [task-orchestration](../product-specs/active/task-orchestration.md)
  (schema gate lives in the orchestrator's Phase 4).
- Designs: [pm-worker](../designs/active/pm-worker.md),
  [architect-worker](../designs/active/architect-worker.md),
  [team-manager-worker](../designs/active/team-manager-worker.md),
  [worker-communication](../designs/active/worker-communication.md)
  (`tasks.failure_kind` / `failure_detail` columns).
- ADR: [0012 — re-prompt-only remediation](../adrs/0012-re-prompt-only-worker-output-remediation.md)
- Adjacent: [worker-transient-failure](./worker-transient-failure.md),
  [branch-gc](./branch-gc.md)
