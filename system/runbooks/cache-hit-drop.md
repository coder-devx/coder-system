---
id: cache-hit-drop
title: Cache-hit ratio dropped overnight — diagnose and remediate
type: runbook
status: active
owner: ro
created: 2026-04-19
updated: 2026-04-19
last_verified_at: 2026-04-19
applies_to_services: [coder-core, coder-admin]
applies_to_integrations: [slack]
---

# Cache-hit ratio dropped overnight

Operational guide for when a project's prompt-cache hit ratio falls
below the configured floor. The cache mechanism is defined in spec
[0029-prompt-caching](../product-specs/wip/0029-prompt-caching.md) and
the populate + read + gate behaviours live in
[task-orchestration](../product-specs/active/task-orchestration.md).
Telemetry + alert wiring lives in
[observability](../product-specs/active/observability.md).

## When to run this

- Slack fires `:mag: Cache hit floor alert — project X cache-hit ratio
  is Y% over the last 24h ...` against the configured webhook.
- The admin `/metrics` page's "Prompt Cache Efficiency" table shows a
  role dropping from green (≥50%) to amber (20–50%) or rose (<20%).
- A project's `CacheCard` chip on the ProjectDetail overview shows a
  sudden drop from prior-week baseline.

## Who can run this

Operator with admin JWT. Remediation often touches role prompts or the
project's `AGENTS.md`, which may require a code/knowledge-repo change.

## Prerequisites

- Admin panel access for `/metrics` and `/projects/{id}` views.
- Read access to the project's knowledge repo (for the AGENTS.md
  check).
- `git log` of `coder-core/src/coder_core/workers/` if a role-prompt
  rewrite is suspected.

## What the alert means

The alert fires only when all four conditions hold:

1. `SLACK_CACHE_HIT_FLOOR` is set above 0 in coder-core's env.
2. `PROMPT_CACHING_ENABLED` is on (otherwise the ratio is
   legitimately ~0 and alerting is noise).
3. At least 3 tasks with populated cache counters landed in the last
   24h for the project.
4. `sum(cache_read_input_tokens) / sum(cost_input_tokens)` is below
   the floor.

A false-positive drop usually means the *prefix* Anthropic was caching
changed bytes since the last sibling call. Five things produce that
change.

## Triage

### 1. Did someone rewrite a role system prompt?

The five role docs live in the project's knowledge repo under
`system/roles/{developer,reviewer,pm,software-architect,team-manager}.md`.
A `git log -p system/roles/` in the knowledge repo will show any
recent edit. When a role doc is rewritten, every dispatched task for
that role sends a fresh prefix until the cache window (~5 min)
re-populates. Expected, temporary — the ratio recovers within one
pipeline-run cycle.

**Action:** confirm the edit was intentional, wait one cycle, and
re-check the ratio before escalating.

### 2. Did `AGENTS.md` churn in the project's knowledge repo?

The shared per-run context block embeds the knowledge repo's
`AGENTS.md` (capped at 64 KiB) as part of the cached prefix. Byte-level
changes — including whitespace and CRLF flips — invalidate the cache
for every new run.

**Action:** `git log -p AGENTS.md` in the project's knowledge repo.
Rapid-fire edits (e.g. a rewrite loop) will show here. Ask the author
to stabilise the file; for legitimate prose changes the ratio
recovers on the next pipeline run.

### 3. Did the context-block builder shape change?

The builder lives in
[`coder-core/src/coder_core/workers/context.py`](https://github.com/coder-devx/coder-core/blob/main/src/coder_core/workers/context.py).
Any change to `_SYSTEM_PROMPT_HEADER`, the brief layout, the AGENTS.md
section header, or the knowledge-snippets placeholder shifts every
project's prefix bytes. This is the "did we ship a coder-core deploy
last night?" check.

**Action:** `git log -p src/coder_core/workers/context.py` in the
coder-core repo. Any edit to `_compose` or the headers is a
fleet-wide cache reset — every project's ratio will dip and recover
on its next run. If ratios don't recover within one cycle, that's a
real bug (see §5).

### 4. Did a sibling-divergence audit fail?

The dispatcher logs
`dispatch_task: loaded project context block task=T pipeline_run=R
block_hash=H` on every task dispatch that carries a
`pipeline_run_id`. Two siblings of one run should log identical `H`
values. If they don't, the populate path wrote divergent bytes —
which would defeat the cache and is a real bug.

**Action:**

```sh
gcloud logging read 'textPayload:"loaded project context block"' \
  --project=vibedevx --freshness=24h --limit=200 \
  --format='value(textPayload)'
```

Group by `pipeline_run=` and confirm every group has one unique
`block_hash=`. If any group shows two hashes, file a bug against
spec 0029 — this should never happen.

### 5. Did the flag flip?

The `PROMPT_CACHING_ENABLED` env var gates the prepend. If the Cloud
Run revision rolled back without the flag set, the ratio drops to
whatever the CLI's own system-prompt caching produces (usually
non-zero but flat). The alert's `prompt_caching_enabled` guard
suppresses the Slack in this case — but the admin UI chart will
still show the drop.

**Action:** `gcloud run services describe coder-core --region=europe-west1
--project=vibedevx` and confirm `PROMPT_CACHING_ENABLED=true` is in
the `env:` block of the current revision. If not, re-deploy with the
flag restored.

## Remediation

| Triage finding | Fix |
|---|---|
| Role prompt rewrite (§1) | Wait one cycle. Ratio recovers. |
| AGENTS.md churn (§2) | Ask author to stabilise; no code change. |
| Context-builder shape change (§3) | Verify the deploy was intentional; ratio recovers within 1–2 pipeline runs. |
| Sibling-divergence audit fails (§4) | File bug — this is never expected. Roll back coder-core if the divergent hashes followed a deploy. |
| Flag flipped off (§5) | Redeploy coder-core with `PROMPT_CACHING_ENABLED=true`. |

## Success condition

- `/metrics` cache-hit rate for the affected role is back above the
  floor on the next pipeline-run cycle.
- No new Slack alert fires over the following hour (the rate limiter
  suppresses a second alert for an hour anyway, so check the
  cache-hit-rate chart, not the Slack channel).

## If something goes wrong

- **Alert keeps firing even after remediation:** the in-memory
  rate-limit should keep it quiet for 1 h, but restarting the
  coder-core process resets `_last_sent`. If the alert re-fires
  immediately after a Cloud Run revision roll, it's the same alert
  re-evaluated against the same data — expected once, not repeatedly.
- **Ratio doesn't recover within 2 pipeline cycles after a §1/§2
  stabilisation:** suggests the cache has a stale prefix that never
  matches. Force a fresh pipeline run and watch the next dispatch's
  block_hash log line — if it matches a prior run's hash, the content
  really is stable and the issue is on Anthropic's side. Escalate via
  the support channel.
- **Hash collisions in §4 appear on every deploy:** the populate path
  is non-deterministic, which is a bug against the phase-2 invariant.
  Back out the offending deploy and open an incident.
