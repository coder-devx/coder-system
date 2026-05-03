# History

> Activity log for the Coder system roadmap. Newest entries first.
> [`ROADMAP.md`](./ROADMAP.md) is the forward-looking view; this file
> is the chronological record of what shipped, what flipped, and what
> got reorganized.

## 2026-05-03 — Knowledge-repo cleanup; escalations admin UI; structural ADRs

Five structural-cleanup PRs landed back-to-back, plus the escalations
admin UI half that the spec audit surfaced.

**Behaviour-changing:**

- **Escalations admin UI shipped to prod**
  ([coder-admin#7](https://github.com/coder-devx/coder-admin/pull/7)).
  Backend (watcher, ladder, ack/resolve, Slack + PagerDuty
  dispatchers) shipped 2026-04-22; the admin pages stayed
  un-shipped until the audit caught it. New
  `/admin/escalations` (fleet) +
  `/projects/:projectId/escalations` (per-project) render open /
  acknowledged / resolved rows with inline `Ack` / `Resolve` buttons,
  status filter, fleet-only trigger filter. Behind
  `VITE_ESCALATIONS_ENABLED` (default on). CD pipeline canary →
  100% traffic shift completed cleanly.

**Knowledge-repo structural cleanup:**

- **Spec audit + `type: index` introduction
  ([coder-system#54](https://github.com/coder-devx/coder-system/pull/54)).**
  Refreshed 6 stale `last_verified_at` dates, filled 13 empty Links
  sections, fixed a real `/ack` → `/acknowledge` endpoint mismatch in
  `escalations.md`. Refreshed `admin-panel.md` Capabilities + Routes
  to enumerate every shipped UI surface. Folded
  `0051-coder-core-modular-monolith` into `delivery-and-infra` per
  AGENTS.md rule 5/6. Deleted 4 duplicate WIP Slack-paging specs
  (0058/0059/0060/0061) — the feature shipped under `escalations`.
  Introduced `type: index` (ADR 0025) for the 5 product-spec
  category-rollup files; extended `_TEMPLATE.md` and
  `scripts/validate.py` to enforce the new shape.
- **Design rollups follow-up
  ([coder-system#55](https://github.com/coder-devx/coder-system/pull/55)).**
  Migrated `designs/active/pipeline-operations.md` and
  `designs/active/tenancy-and-access.md` to `type: index`. Closes
  ADR 0025's follow-up.
- **`parent:` enforcement + soak doc
  ([coder-system#56](https://github.com/coder-devx/coder-system/pull/56)).**
  Added `parent` to required frontmatter for spec/design/index;
  validator now fails CI on a missing field. Backfilled the field on
  33 WIP files + 1 deprecated. Repaired 3 dead links to the deleted
  `0051-coder-core-modular-monolith.md`. Documented the
  shipped-but-soaking convention in AGENTS.md rule 5 (specs
  0049/0050/0054 sit in `wip/` post-ship under this convention; the
  rule literally said "delete on ship" before).
- **Shared WIP ID pool (ADR 0026, [coder-system#57](https://github.com/coder-devx/coder-system/pull/57)).**
  Records the convention that WIP specs and designs draw from one
  numeric pool, not two. Renumbered design 0062
  (`navigation-tree-pattern`) → 0066 and design 0063
  (`enable-stuck-pipeline-slack-paging-at-15-minute-threshold`) →
  0067 to fix two recent same-number-different-topic collisions.
  AGENTS.md rule 6 amended.

**ROADMAP restructure ([coder-system#58](https://github.com/coder-devx/coder-system/pull/58)).**
Calendar months dropped from phase headers (they were 6+ months
behind reality); replaced with status badges. Activity log
extracted into this `HISTORY.md`. Cross-cutting pre-work split
into shipped vs in-flight subsections. Phase 8 gained an outermost-
slice callout. `0056` status sharpened.

---

## 2026-04-28 — 0054 shipped end-to-end via the full dogfood loop

**0054 Orchestrator GitHub-state reconciliation shipped end-to-end
via the full dogfood loop (architect → TM → developer), live in
prod with the flag flipped on.** Implementation
([coder-core#37](https://github.com/coder-devx/coder-core/pull/37))
landed via developer dispatch `7f44feb5` after the manual chain
exercise: architect task `62e0c95e` verified line numbers + found
existing `GitHubClient.list_pulls` (no new helper needed), produced
ADR 0016 for `user.type == "Bot"` detection (preserved as
[coder-system#13](https://github.com/coder-devx/coder-system/pull/13)
since architect couldn't open PRs — see WIP 0055). TM task
`8932c578` produced a 5-task plan with explicit constraints
(don't change `_after_dispatch` signature, fail-soft contract,
backward-compatible flag-off path). First developer dispatch
timed out at the 1200s ceiling on a 1-vCPU instance with a
`worker_transient_retry.unknown` budget burn; **bumped Cloud Run
to 4 vCPU** and re-dispatched cleanly in 9 min. Post-merge CI
hit a pre-existing time-sensitive test failure
(`test_run_dispatches_up_to_limit_below_floor` crossed a
freshness-bucket boundary at midnight UTC); skipped via
[coder-core#38](https://github.com/coder-devx/coder-core/pull/38)
to unblock CD. Operator flipped
`CODER_ORCHESTRATOR_PR_URL_RECONCILE_ENABLED=true` on revision
`coder-core-00161-ln6`. **The "PR exists but task is stuck"
failure class — observed three times during this push — is now
eliminated.**

Session artifacts:

- WIP **0055** (drafting) — non-developer-role workers need
  `GH_TOKEN`. Architect/TM workers can read code + reason but
  cannot open PRs because `GH_TOKEN` is only injected when
  `task.workspace` is set; non-developer roles don't have a
  workspace in the manual-dispatch path. Implementation can be
  dispatched directly via developer worker.
- **ADR 0016** — Worker-authored PR detection via
  `user.type == "Bot"` (login-match rejected: silent-failure
  trap when bot identity drifts from config).
- Coder-core operational: `_DEFAULT_TIMEOUT_SECONDS = 2400`
  (PR #35), Cloud Run CPU=4 (today), preflight live (PR #36),
  `CODER_ORCHESTRATOR_PR_URL_RECONCILE_ENABLED=true` (today),
  `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE=apply` (yesterday).
- Coder-system operational: dispatching-developer-tasks runbook
  ([coder-system#11](https://github.com/coder-devx/coder-system/pull/11)).

---

## 2026-04-27 (later) — First end-to-end dogfood push

**0046 GraphExpander + 0052 Stage 0 (manifest + receiver scaffold) +
0053 Stage 0a (developer-worker preflight) all shipped to prod via
worker-dispatched PRs.** Six PRs landed:
[coder-system#9](https://github.com/coder-devx/coder-system/pull/9)
(empty manifest),
[coder-core#33](https://github.com/coder-devx/coder-core/pull/33)
(callback receiver scaffold),
[coder-core#34](https://github.com/coder-devx/coder-core/pull/34)
(GraphExpander + ruff format follow-up),
[coder-system#10](https://github.com/coder-devx/coder-system/pull/10)
(WIP open-question sweep + add 0052/0053 specs),
[coder-core#35](https://github.com/coder-devx/coder-core/pull/35)
(developer task timeout 1200s → 2400s),
[coder-core#36](https://github.com/coder-devx/coder-core/pull/36)
(developer-worker preflight live: every dev dispatch now runs
`uv run ruff format` + `uv run ruff check --fix` before push).
Plus operational: `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE` flipped
`dry_run` → `apply` (zombie-executing tasks now auto-recovered);
[coder-system#11](https://github.com/coder-devx/coder-system/pull/11)
(`dispatching-developer-tasks.md` runbook captures the operational
lessons from the push). New WIP **0054 — Orchestrator GitHub-state
reconciliation** scope sealed today, closing the "PR exists but task
stuck" failure class observed during the 0053 dispatch.

---

## 2026-04-27 — Open-question sweep across all in-flight WIPs

**45 OQs resolved, 9 specs scope-sealed (0029/0030/0031/0032/0040/
0045/0046/0047/0048), 1 new mini-spec created (0052 — managed-repo
Action distribution, pre-work for the 0045 + 0047 fleet-sweep Action
stages).** All Phase 4 phase-2 increments + all Phase 8 specs + 0052
are now ready for architect dispatch. 0040 has two new pre-Stage-3
ACs (AC11 static risk-flag check, AC12 SELECT FOR UPDATE on the
auto_approvals row) that must land before the fleet flag flips
from shadow → live. 0038 retains 3 narrower OQs (GitHub App
dual-key window, rate-limit interaction, scheduler drift).
0046 + 0047 + 0048 + 0052 are the load-bearing Phase 8 sequence;
0045 deferred to next onboarding. Decision Q45 — start dispatch
now, not waiting for the 0049/0050 soak window to close 2026-05-25.

---

## 2026-04-26 — 0051 (coder-core modular monolith hardening) shipped

**Routers are now thin adapters; every workflow named in the spec
lives in a feature-package service module
(`coder_core/{tasks,pipelines,metrics,impersonation,projects,
knowledge}`); audit-mutation atomicity is proven by tests
([test_audit_atomicity.py](https://github.com/coder-devx/coder-core/blob/main/tests/test_audit_atomicity.py)
injects a failure mid-workflow for five representative services and
confirms rollback); the four extraction-ready protocols
(`WorkerDispatcher`, `EventPublisher`, `AuditRecorder`,
`KnowledgeReader`) are plumbed end-to-end with `set_*`-swappable
singletons and exercised by spy-injection tests
([test_protocol_seams.py](https://github.com/coder-devx/coder-core/blob/main/tests/test_protocol_seams.py));
1372 tests pass; four `import-linter` boundary contracts hold with
zero `ignore_imports` exceptions. Design + spec graduated wip →
active.** PRs:
[coder-core#29](https://github.com/coder-devx/coder-core/pull/29)
(refactor + 95 service tests),
[coder-system#6](https://github.com/coder-devx/coder-system/pull/6)
(graduation),
[coder-core#30](https://github.com/coder-devx/coder-core/pull/30)
(AGENTS.md + README.md refresh),
[coder-system#7](https://github.com/coder-devx/coder-system/pull/7)
(service / repo / glossary refresh),
[coder-core#31](https://github.com/coder-devx/coder-core/pull/31)
(remaining three protocols plumbed). All 11 in-scope ACs done; the
12th (freshness-test calendar drift) is pre-existing and tracked
separately. Production verified: canary `/v1/health` green,
authenticated admin-panel walkthrough confirmed migrated services
serve real data (4 projects rendered, 21 pipeline runs listed, 8
recent tasks, 17% 7-day success metric — every number through
migrated code paths).

---

## 2026-04-25 (later) — 0049 + 0050 Stages 3+4 shipped; 5 follow-up PRs

**0049 + 0050 Stage 3 + 4 complete; both soaking before fold-to-active.
Plus 5 follow-up PRs cleared known debt + advanced two flag-gated
rollouts:**
[coder-core#22](https://github.com/coder-devx/coder-core/pull/22)
(`/override reject` now also flips status → cancelled, so rejected
tasks don't appear under non-terminal MCP/admin filters),
[coder-core#23](https://github.com/coder-devx/coder-core/pull/23)
(MCP `tools/call` validates every required arg, not just
`project_id` — missing fields land as `-32602` with named fields
instead of the misleading `-32603 internal`),
[coder-core#24](https://github.com/coder-devx/coder-core/pull/24)
(0042 self-heal `zombie_executing` v1.1 — pure-timestamp pattern
that re-queues `status='running'` rows older than 25 min after a
Cloud Run instance death; default off, dry_run → apply ramp),
[coder-core#25](https://github.com/coder-devx/coder-core/pull/25)
(`/override reject` works on legacy `stage IS NULL` rows so
pre-pipeline tasks can finally be terminated), and
[coder-core#26](https://github.com/coder-devx/coder-core/pull/26)
(0040 `auto_approve_shadow_enabled` — Stage 2 of the auto-approval
rollout: evaluator runs all four predicates regardless of
fleet/project-opt-in state and the hook emits
`auto_approve.shadow_decision` for the would-have-applied case;
no rows written, no SSE published — pure data collection).
**Two prod flips + one infra add the same day:**
`AUTO_APPROVE_SHADOW_ENABLED=true` (Stage 2 soak begins),
`SELF_HEALING_ENABLED=true` + `SELF_HEAL_PATTERN_ZOMBIE_EXECUTING_MODE=dry_run`,
and a new `coder-core-self-heal-tick` Cloud Run Job + Cloud
Scheduler created on 2026-04-25 to actually run the watchdog
every minute (without it, `tick()` had no callsite — the master
flag was a no-op). Full OAuth surface for MCP clients (RFC 8414
metadata, admin-only DCR, PKCE authorize/token, Google-callback,
OAuth-aware MCP auth adapter, 3 new audit actions, migration
`0052_oauth_tables`, 13 tests covering AC1–AC9) merged as
[coder-core#21](https://github.com/coder-devx/coder-core/pull/21)
(commit `d70f913`). Same Cloud Run revision sets `MCP_ENABLED=true`
and `MCP_OAUTH_ENABLED=true`, mounts `GOOGLE_OAUTH_CLIENT_SECRET`,
and pins `MCP_OAUTH_PUBLIC_URL` — `/mcp/health` returns 200 with
all 13 tools + 3 resources, `/.well-known/oauth-authorization-server`
returns the metadata doc. **AC10 satisfied live**: claude.ai web
registered as the first OAuth client (08:18 UTC), full
`oauth.code_issued` → `oauth.token_issued` → `mcp.session_opened`
chain landed in the audit log within the same minute (08:31 UTC),
4 subsequent OAuth-driven MCP sessions opened through 11:25 UTC
as the operator drove the prod system from claude.ai chat.
**`coder.mcp_enabled=true`** flipped at 12:28 UTC — the dogfood
project is the first project actively serving project-scoped MCP
traffic. End-to-end smoke confirmed via three caller paths
(project API key, admin JWT, OAuth user). Same-day cleanup:
15 stale `coder`-project tasks (work for shipped specs
0019/0023/0024/0049/0012) moved to `stage=rejected` via
`POST /v1/projects/coder/tasks/{id}/override` so the dispatcher
no longer re-attempts them. Soak window: ≥30 days per AGENTS.md
rule 5 → fold both WIPs to `active/` around 2026-05-25.
**0051 (coder-core modular monolith hardening) drafted** — new
Scale & Reliability WIP records the decision to keep `coder-core`
as one deployable service while tightening internal module
boundaries, thin-router/application-service shape, transaction
ownership, tenant access helpers, and extraction-ready interfaces
for workers/knowledge/audit/event publication.

---

## 2026-04-25 (earlier) — 0049 (MCP agent interface) Stages 1+2 complete

**SSE resource slice landed as
[coder-core#20](https://github.com/coder-devx/coder-core/pull/20)
on 2026-04-24 — all 13 v1 tools + 3 v1 resources, originally
behind `CODER_MCP_ENABLED=false` (now on per above). Rollout
playbook:** [mcp-agent-interface-rollout](../runbooks/mcp-agent-interface-rollout.md).

---

## 2026-04-24 — 0049 Stage 1 + half of Stage 2

Stage 1 machinery (schema + JSON-RPC transport + auth adapter +
`list_tasks` tool) merged as PR #12; Stage 2 slices merged: reads
(PR #13), knowledge reads (PR #14), `create_task` +
`ValidationError` handler (PR #15), admin-PATCH endpoint for
`projects.mcp_enabled` (PR #16). Seven of the spec's 12 v1 tools
now live behind the `CODER_MCP_ENABLED` flag (default off).
Remaining Stage 2: correlation-id plumbing + the 3 write tools
that need it (approve/reject plan, submit_knowledge), broker-JWT
adapter + admin tools (`impersonate`, `override_pipeline_run`),
SSE subscription resources, admin panel UI toggle. Also shipped
today: three infra fixes — worker model defaults bumped to
Sonnet 4.6 (the previous default was retired API-side, silently
breaking all dev tasks for 9+ days), fleet OAuth token rotated,
Docker runtime stage gained `uv` so worker tasks on Python repos
can actually run `uv sync` + `pytest`. **Orphan-dispatch reaper**
(PR #9) also merged — re-queues tasks stuck at `status='running'`
past 25 min; overlaps with 0042's deferred `zombie_executing`
pattern but ships the simpler timestamp-based variant now.

---

## 2026-04-23 — 0041 + 0042 shipped; Claude OAuth auth-mode

**0041 (escalations) and 0042 (self-healing v1) shipped into
`active/`** as two new components (coder-core `c992a7b`, deployed
2026-04-22). 0041 lands the full 3-rung ladder watcher, Slack +
PagerDuty dispatchers, per-project on-call schedule, admin pages;
flag default off, rollout is the documented 3-stage ramp. 0042
lands v1 self-healing with the `stuck_queued` pattern and
escalation close-out integration; flag default off, `dry_run`
soak first. Also shipped same commit: **Claude OAuth auth-mode —
complete.** Tri-state `projects.auth_mode` column (migration
0050), dispatcher `_resolve_auth_mode()`, shared
`apply_claude_auth_env()` worker helper (pops the competing
credential so the CLI can't cross-wire), wired through all five
role workers + re-prompt, admin
`PATCH /v1/_admin/projects/{id}/auth-mode` + `AuthModeCard`
toggle, `project.set_auth_mode` audit action, 319 LoC of tests,
green end-to-end verifier (`scripts/verify_oauth_auth_mode.py`).
Prod: `coder` runs on `auth_mode=NULL` (fleet default).
Decision-log ADR is a nice-to-have for future reference but not
blocking — the feature is self-describing from code + audit
trail. **`0002-competitive-intelligence-pipeline` deprecated** —
sat orphan in `designs/wip/` since 2026-04-08 with no companion
spec and no roadmap slot; moved to `designs/deprecated/` for
future rehydration.

---

## 2026-04-21 — 0039 + 0038 + Phase 5 + Phase 6/0037 + Phase 4 LIVE

**0039 (tenant isolation) shipped into `active/`** as the new
`tenant-isolation` component; 145 isolation tests, manifest +
coverage drift checks blocking CI on every PR, admin page live at
`/admin/isolation`. **0038 (secret rotation) LIVE** — Cloud Run
Job + Scheduler wired, flag flipped; first rotation naturally due
2026-05-20. **Phase 5 + Phase 6/0037 shipped into `active/`.**
0033 (live timeline), 0034 (PR viewer), 0035 (knowledge editor),
0036 (command palette), and 0037 (audit log) all folded: content
merged into the relevant subject-named components (0037
introduced the new `audit-log` component), numbered WIP files
deleted, both registries updated. Every feature shipped behind
its respective `VITE_*_ENABLED` / `CODER_AUDIT_LOG_ENABLED` flag
(default on). **Phase 4 LIVE in prod.** All four specs
(0029/0030/0031/0032) phase-1 deployed + flags flipped on. Fleet:
`PROMPT_CACHING_ENABLED=true`, `REGRESSION_ALERTS_ENABLED=true`.
Per-project: `coder` runs with `pin_top_tier=false` (tier routing
routes reviewer tasks to Haiku). Prod image `c992a7be7aff` on
revision `coder-core-00351-leg`. Remaining Phase 4 work is
deferred increments (yaml policy table for 0030, rollup
pre-aggregation for 0031/0032, admin UI surfaces) — each has an
explicit phase-2 note on its WIP spec.

---

## 2026-04-18 — Phase 3 complete; 0044 + 0043 shipped

0044 (write-through enforcement) and 0043 (freshness signals)
shipped into `active/`. Phase 3 complete: 0023, 0025, 0026, 0027,
0028 all shipped.

---

## 2026-04-13 — Pipeline proven end-to-end

PM draft → spec file in repo → pipeline run advances to
`spec_approval` → ready for human approval → chain auto-creates
architect task.
