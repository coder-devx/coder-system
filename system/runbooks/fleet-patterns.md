---
id: fleet-patterns
title: Fleet pattern index — operate and interpret
type: runbook
status: active
owner: ro
created: 2026-05-05
updated: 2026-05-05
last_verified_at: 2026-05-05
applies_to_services: [coder-core]
applies_to_integrations: []
---

# Fleet pattern index — operate and interpret

## When to run this

- You need to understand how the daily pattern indexer computes its groups.
- You are reading a pattern group in the admin API or admin UI and want to
  interpret the fields.
- You want to disable a pattern kind or turn off fleet patterns for one project.
- You see a `role_prompt_delta` group and want to decide whether to act on it.
- You see a `template_drift` group and want to promote the field to the central
  template.
- You are auditing whether artifact-body content is crossing tenant lines.

## Who can run this

Operator with admin API token for the relevant diagnostic steps. Template
promotion steps require a PR to `coder-devx/coder-system`.

---

## 1. How the five pattern kinds are computed

The daily `coder-core-pattern-indexer` Cloud Run Job runs at 03:00 UTC. It
fetches a knowledge snapshot per opted-in project (`share_patterns=TRUE`) and
runs five kind-specific modules. Each module produces `PatternGroupCandidate`
objects; the `StableIdMatcher` assigns stable ids; rows are written to
`pattern_groups` under a new `pattern_index_runs.id`.

### `adr` — Jaccard on ADR titles (floor 0.5)

1. Collect `(project_id, adr_id, adr_title, decision_first_sentence)` from
   every opted-in project's snapshot.
2. Tokenise each title: lowercase, remove stop words, drop 1-char tokens.
3. For every pair of ADRs across projects, compute token-bag Jaccard:
   `|intersection| / |union|`.
4. Group transitively: any set of ADRs where every pair's Jaccard ≥
   `patterns_indexer_adr_jaccard_floor` (default 0.5) forms one group.
5. Keep only groups with ≥ 2 distinct `project_id`s.

Setting `patterns_indexer_adr_jaccard_floor=1.0` effectively raises the bar to
exact match — in practice this produces zero groups and acts as a disable.

### `spec_problem` — Jaccard on `## Problem` first paragraphs (floor 0.4)

Same as `adr`, but over the first paragraph of each spec's `## Problem`
section. Threshold is lower (0.4) because problem-statement prose is naturally
wordier and looser than a short ADR title.

### `failure_taxonomy` — exact match across projects (≥ 2 projects)

SQL-based, no Jaccard:

```sql
SELECT failure_kind, COUNT(DISTINCT project_id) AS project_count
FROM tasks
WHERE status = 'failed'
  AND failed_at > now() - interval '30 days'
  AND project_id IN (SELECT id FROM projects WHERE share_patterns = TRUE)
GROUP BY failure_kind
HAVING COUNT(DISTINCT project_id) >= 2
```

Each surviving `failure_kind` value becomes one group. Members carry
`(project_id, failure_kind, count, last_seen_at)`. No Jaccard floor applies —
the `failure_kind` enum value is exact.

### `role_prompt_delta` — pre/post approval-rate window (|Δpp| ≥ 3, n ≥ 20)

For each project's `roles/*.md` files:

1. Find the latest commit in the last 30 days that touched the file.
2. Compute per-role task acceptance rate:
   - **Before:** `tasks.status='accepted'/total` over the 3 days before the
     commit timestamp.
   - **After:** same ratio over the 7 days after the commit.
3. `delta_pp = (after_rate - before_rate) * 100`.
4. Keep the `(project, role)` pair if `|delta_pp| ≥ min_pp`
   (`patterns_indexer_role_delta_min_pp`, default 3.0) and
   `sample_size_n ≥ min_sample_n` (`patterns_indexer_role_delta_min_sample_n`,
   default 20).

Each surviving `(project, role)` is a single-member group — role-prompt impact
is intrinsically per-project. Two projects editing the same role in the same
window produce two separate single-member groups (not one merged group), because
the _impact_ is per-project even if the edit is similar.

### `template_drift` — key-set diff (no floor)

1. For each type (`designs`, `adrs`, `product-specs`), parse the frontmatter
   key set from the project's `system/<type>/_TEMPLATE.md`.
2. Compare against the key set from the central
   `coder-system/template/system/<type>/_TEMPLATE.md`.
3. For each key present in ≥ 1 project but absent centrally, emit one group
   with member shape `(project_id, artifact_type, field_name,
   first_seen_in_artifact)`.

No similarity threshold — a field either exists or it doesn't.

### `StableIdMatcher` — reuse logic

After each kind module produces candidates, `StableIdMatcher` assigns stable
ids to preserve citations across re-runs:

1. Load the prior run's `pattern_groups` rows (same `kind`).
2. For each new candidate, compute Jaccard on the member-key set:
   `{(project_id, artifact_id)}` against each prior group of the same kind.
3. If overlap ≥ `patterns_stable_id_jaccard_floor` (default 0.6) → **reuse**
   the prior group's `id`.
4. Otherwise → **mint** a new id:
   `<kind>-<sha1(kind | sorted_member_keys)[:12]>` (deterministic from
   content — same members on a fresh re-run produce the same new id).
5. Iteration order is sorted on `(kind, sorted_member_keys)` to guarantee
   determinism: the same (prior run, candidates) input always produces the
   same id assignment.

The stability property is load-bearing: `informed_by_patterns` citations in
shipped designs and ADRs must keep resolving even as the fleet grows and
membership drifts slightly between runs.

---

## 2. How to read a pattern group

Each group in `GET /v1/_admin/patterns/{pattern_id}` returns:

```json
{
  "pattern_id": "adr-cloud-run-background-a3f2c8",
  "kind": "adr",
  "title": "ADR: background job runner (2 projects)",
  "score": 0.625,
  "sample_size_n": null,
  "index_age_minutes": 420,
  "members": [
    {
      "project_id": "coder",
      "artifact_id": "adrs/0041",
      "decision_pill_or_summary": "Use Cloud Run Jobs + Cloud Scheduler for all background job workloads; reject Celery."
    },
    {
      "project_id": "vibetrade",
      "artifact_id": "adrs/0009",
      "decision_pill_or_summary": "Cloud Run Jobs + Scheduler; Celery explicitly rejected due to ops overhead."
    }
  ]
}
```

**`score`** — kind-specific similarity metric:
- `adr` / `spec_problem`: Jaccard coefficient (0–1). Higher = more token
  overlap.
- `failure_taxonomy`: count of failed tasks in the 30-day window.
- `role_prompt_delta`: `delta_pp` (signed percentage points). Positive = higher
  acceptance rate after the edit.
- `template_drift`: count of projects that have the drifted field.

**`sample_size_n`** — populated only for `role_prompt_delta`. It is the number
of tasks that fell in the combined pre/post window. Small `n` makes the delta
unreliable — see §4 below.

**`members`** — one entry per contributing project. `decision_pill_or_summary`
is hard-truncated at 200 characters by the indexer; it is the only content that
crosses tenant lines. No artifact body or raw frontmatter is included.

**`index_age_minutes`** — minutes since the run that produced this group
completed. At 03:00 UTC daily, `index_age_minutes` grows to ~1440 before the
next run. A value above 1500 suggests the last run failed — check
`GET /v1/_admin/patterns/index/runs` for the latest run status.

**Worked example.** `coder` has ADR 0041 titled "Use Cloud Run Jobs and
Cloud Scheduler for background work". `vibetrade` has ADR 0009 titled
"Background job runner: Cloud Run Jobs + Scheduler". Tokenised:

- coder/0041: `{cloud, run, jobs, scheduler, background, work}`
- vibetrade/0009: `{background, job, runner, cloud, run, jobs, scheduler}`

Jaccard = `|{cloud,run,jobs,scheduler,background}| / |{cloud,run,jobs,scheduler,background,work,job,runner}|` = 5/8 = 0.625 ≥ 0.5 floor → grouped with `score=0.625`.

The `StableIdMatcher` found no prior group with overlapping members → minted
`adr-cloud-run-background-a3f2c8` (deterministic SHA of sorted member keys).

---

## 3. How to disable a pattern kind

### Raise the Jaccard floor to effectively zero out matches

For `adr` and `spec_problem`, set the floor to 1.0 via the settings API:

```bash
PROD="https://coder-core-ql732k45va-ew.a.run.app"
TOKEN=$(cat ~/.config/coder/admin.key)

# Disable adr grouping
curl -s -X PATCH "$PROD/v1/_admin/settings" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"patterns_indexer_adr_jaccard_floor": 1.0}'

# Disable spec_problem grouping
curl -s -X PATCH "$PROD/v1/_admin/settings" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"patterns_indexer_spec_jaccard_floor": 1.0}'
```

After the next indexer run (or a manual `POST /v1/_admin/patterns/index/run`),
no new `adr` or `spec_problem` groups will be produced. Existing rows from
prior runs remain queryable but `GET /v1/_admin/patterns` filters to the latest
run by default.

For `failure_taxonomy`, `role_prompt_delta`, and `template_drift` there is no
Jaccard floor. To suppress them, disable fleet patterns entirely (below) or
remove the project's opt-in.

### Disable fleet patterns fleet-wide

Set the environment variable on the `coder-core` Cloud Run service:

```bash
gcloud run services update coder-core \
  --region=europe-west1 \
  --update-env-vars CODER_CROSS_PROJECT_PATTERNS_ENABLED=false
```

Effect: all consult endpoint calls return `404 not_enabled`; the next indexer
run aborts with `status='failed', error_kind='disabled'`. Data is preserved
for when you re-enable.

### Disable per-project (consumption gate)

A project can be prevented from consulting the patterns surface without
affecting its contribution to the index:

```bash
# Disable consumption for project "vibetrade"
curl -s -X PATCH "$PROD/v1/projects/vibetrade" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fleet_patterns_enabled": false}'
```

Workers in that project will receive `404 not_enabled` from the consult
endpoint. Re-enable by setting `fleet_patterns_enabled=null` (inherits fleet
flag) or `true`.

### Disable per-project (contribution gate)

To stop a project's artifacts from appearing in any pattern group:

```bash
curl -s -X PATCH "$PROD/v1/projects/vibetrade" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"share_patterns": false}'
```

The serve-time re-check in the consult handler strips that project's members at
the next consult call without waiting for a new indexer run. The next indexer
run excludes the project entirely.

---

## 4. How to interpret a `role_prompt_delta`

A `role_prompt_delta` group says: "project X edited role Y's prompt on date D,
and the acceptance rate moved by `delta_pp` percentage points over the following
7 days."

**Fields to read:**

| Field | Meaning |
|---|---|
| `delta_pp` | Signed pp change: `(post_rate - pre_rate) × 100`. Positive = more tasks accepted after the edit. |
| `sample_size_n` | Total tasks counted in the pre window (3 days) + post window (7 days). |
| `decision_pill_or_summary` | Short description of the diff (first line of the commit message, truncated to 200 chars). |

**Why small `n` makes the delta unreliable.**

The delta is computed from task-outcome counts in a 10-day window. A project
running 3–5 tasks per day produces ~30–50 tasks in that window — near the noise
floor. With `n=10`, a single outlier task flipping from accepted to failed moves
the rate by 10 pp. With `n=5`, it moves by 20 pp.

**Recommendation: do not act on a delta unless `sample_size_n ≥ 50`.** Below
that threshold, treat the group as a _signal to watch_ rather than evidence to
act on. Wait for the next indexer run (or a few days of additional tasks) to
see if the delta persists.

Conversely, a `delta_pp=+6` with `n=200` is meaningful signal. If the diff was
something the operator wants to adopt in another project, they can read the full
commit in the source project's roles repo and port it manually — no automated
cross-write exists.

The minimum thresholds the indexer uses (`patterns_indexer_role_delta_min_pp`
default 3.0 and `patterns_indexer_role_delta_min_sample_n` default 20) are
intentionally conservative for a small fleet. At fleet size ≥ 5 projects with
higher task volume, consider raising `min_sample_n` to 50 in settings.

---

## 5. How to propose a template promotion from `template_drift`

A `template_drift` group appears when one or more projects have added a field
to their local `system/<type>/_TEMPLATE.md` that is absent from the central
`coder-system/template/system/<type>/_TEMPLATE.md`.

### Operator steps

1. **Identify the group.** Find it via the admin API or admin UI
   (`/admin/patterns?kinds=template_drift`). Note the `field_name` and
   `artifact_type` from the group's members.

2. **Inspect the local template.** For example, if a project added
   `informed_by_patterns` to its designs template:

   ```bash
   gh api "repos/<project-org>/<project-repo>/contents/system/designs/_TEMPLATE.md" \
     --jq '.content' | base64 -d | head -20
   ```

   Read the field's semantics from how the project uses it in existing
   artifacts.

3. **Open a PR to the central template.** Edit
   `coder-system/template/system/<artifact_type>/_TEMPLATE.md` to add the
   field with an appropriate default (usually `[]` or empty string) and a YAML
   comment explaining its purpose.

4. **Reference the 0047 migration process.** The PR body should note the
   corresponding 0047 migration that will propagate the field to managed
   projects' templates. The migration sets a `ALLOW_BATCHING=true` flag and
   targets the relevant `artifact_type`. See the
   [ship-wip-into-active runbook](./ship-wip-into-active.md) for how to
   pair a template PR with a 0047 migration.

5. **After the central template PR merges**, the `template_drift` group will
   disappear from the next indexer run (because the field is now present
   centrally). If it persists, verify the central template was updated with
   the exact same YAML key name.

**What not to do:** do not auto-promote by copying the local template file
wholesale. Only the specific drifted field belongs in the PR — other
project-specific content must stay in that project's own template.

---

## 6. Privacy boundary

**The invariant:** no artifact body content or raw frontmatter from one project
reaches another project through the worker consult path.

### What crosses tenant lines (and only this)

When a worker calls `GET /v1/projects/{id}/patterns/consult`, the response is
shaped by `PatternGroupConsultSafe` (Pydantic model with `Config.extra='forbid'`).
Per member, the model allows exactly:

| Field | Max length | What it is |
|---|---|---|
| `project_id` | opaque string | Already known: a fleet project exists |
| `artifact_id` | opaque string | The artifact's path/id — not title or body |
| `decision_pill_or_summary` | 200 chars hard-truncated | `## Decision` first sentence or problem summary; stripped by indexer at write time |
| `pattern_id` | stable string | Identifier only |

### What is stripped

`Config.extra='forbid'` on `PatternGroupConsultSafe` and
`PatternMemberConsultSafe` means any field not in the above list causes a
Pydantic validation error at the model level — it cannot silently leak through.
Explicitly stripped: `body`, raw `frontmatter`, `freshness`, `last_verified_at`,
`created_at`. For `role_prompt_delta`, even the diff hunks are stripped — the
consult response carries only `delta_pp` and `sample_size_n`.

### Schema test

A schema test in `coder-core` asserts `Config.extra = 'forbid'` on both
`PatternGroupConsultSafe` and `PatternMemberConsultSafe`. This test is
load-bearing: any future field addition to the safe model must be reviewed
against this invariant and will fail the schema test if `extra` is changed.

### What admin scope adds

Admin-scope responses (`GET /v1/_admin/patterns/{id}`) return
`PatternGroupFull` with full member detail including diff hunks for
`role_prompt_delta`. This is the operator surface — an authenticated admin is
expected to have cross-project visibility. The worker consult endpoint never
uses the admin path.

### `share_patterns=TRUE` as the only contribution gate

A project contributes to the index only if `projects.share_patterns=TRUE`.
`NULL` (opt-out default) and `FALSE` (explicit hide) are both equivalent for
indexer inclusion: the project's artifacts never enter any `pattern_groups` row.
This gate is enforced in two places:

1. **Indexer runner** — the project list query filters to `share_patterns=TRUE`
   before fetching any snapshot.
2. **Serve-time re-check** — the consult handler re-verifies `share_patterns`
   for each member project after the token-overlap match. Members from projects
   that have since opted out are stripped before the response is returned,
   without waiting for the next indexer run.

Admin scope does not bypass `share_patterns` — admin tokens see the same member
filter as project tokens. To read a non-sharing project's knowledge directly,
an admin must use the per-project `/v1/projects/{id}/knowledge/` endpoints.

## Related

- Spec [0048](../product-specs/wip/0048-cross-project-patterns.md) — Cross-project pattern surfacing
- Design [0048](../designs/wip/0048-cross-project-patterns.md) — full design with invariants and rollout plan
- ADR [0022](../adrs/0022-structural-jaccard-for-pattern-discovery.md) — structural Jaccard vs semantic similarity
- ADR [0023](../adrs/0023-admin-api-and-consult-endpoint-as-pattern-surfaces.md) — admin API + consult endpoint as the two surfaces
- ADR [0024](../adrs/0024-share-patterns-column-as-enforcement-boundary.md) — `share_patterns` column as enforcement boundary
