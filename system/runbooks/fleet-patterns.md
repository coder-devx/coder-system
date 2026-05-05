---
id: fleet-patterns
title: Fleet patterns — operate and interpret the cross-project pattern index
type: runbook
status: active
owner: ro
created: 2026-05-05
updated: 2026-05-05
last_verified_at: 2026-05-05
applies_to_services: [coder-core]
---

# Fleet patterns — operate and interpret the cross-project pattern index

Spec 0048 (cross-project pattern surfacing) introduces a daily indexer
that groups similar artifacts across opted-in projects and surfaces those
groups to operators (via the admin API) and workers (via the consult
endpoint). This runbook covers day-2 operations: understanding what the
indexer computed, disabling misbehaving pattern kinds, and acting on the
signals the patterns surface provides.

## 1. How the five pattern kinds are computed

The indexer runs as a Cloud Run Job (`coder-core-pattern-indexer`) at
03:00 UTC daily, or on demand via `POST /v1/_admin/patterns/index/run`.
It fetches per-project knowledge snapshots (via the 0046 graph endpoint,
depth=1) for every project with `share_patterns=TRUE`, then dispatches
five separate modules:

### `adr` — title Jaccard

`kinds/adr.py` collects every ADR's title across opted-in projects. Each
title is tokenised (lowercase, stop-words removed, tokens ≤ 1 char
dropped) and the Jaccard similarity between every pair of project ADRs is
computed. Pairs meeting `patterns_indexer_adr_jaccard_floor` (default
**0.5**) are grouped transitively. A group must contain ≥ 2 distinct
`project_id`s to be retained; single-project groupings are discarded.

### `spec_problem` — problem paragraph Jaccard

`kinds/spec_problem.py` does the same tokenise-and-Jaccard operation, but
on the first paragraph of each spec's `## Problem` section. The floor is
`patterns_indexer_spec_jaccard_floor` (default **0.4**) — slightly lower
than `adr` because problem statements are more verbose and share more
common words than decision titles.

### `failure_taxonomy` — exact match, ≥ 2 projects

`kinds/failure_taxonomy.py` does not use Jaccard. It queries the DB:
`SELECT failure_kind, project_id FROM tasks WHERE status='failed'
AND created_at > now() - interval '30 days'`. Any `failure_kind` that
appears in ≥ 2 distinct opted-in projects forms a group. Each group's
`score` is the cross-project occurrence count; a higher score means the
failure is more widespread.

### `role_prompt_delta` — approval-rate window comparison

`kinds/role_prompt_delta.py` finds commits to `roles/*.md` in each
project's repo over the last 30 days. For each such commit, it computes
the `tasks.status='accepted'`/total ratio in two windows around the
commit:

- **Before window:** `(commit_date - 3d, commit_date)`
- **After window:** `(commit_date, commit_date + 7d)`

If `|after_rate - before_rate| ≥ patterns_indexer_role_delta_min_pp`
(default **3.0 percentage points**) and the sample in the after window
is `≥ patterns_indexer_role_delta_min_sample_n` (default **20** tasks),
a group is emitted. Each group is intrinsically single-project (a
per-project, per-role signal); there is no cross-project grouping for
this kind. `score` is `delta_pp`; `sample_size_n` is the after-window
task count.

### `template_drift` — key-set diff against central template

`kinds/template_drift.py` fetches each project's
`system/<type>/_TEMPLATE.md` frontmatter key set and diffs it against
the central `coder-system/template/system/<type>/_TEMPLATE.md`. Any
field present in at least one project's template but absent from the
central template emits a group: `(artifact_type, field_name)`. `score`
is the count of projects that have added the field locally. This is the
signal that drives the 0047 template-promotion loop.

### `StableIdMatcher` — reusing IDs across runs

After all five kinds compute their candidates, `stable_id.py`'s
`StableIdMatcher` assigns stable `pattern_id` values. For each new
candidate, it computes Jaccard on the set of `{(project_id,
member_artifact_key)}` tuples against every prior group of the same kind
from the previous run. If overlap ≥ `patterns_stable_id_jaccard_floor`
(default **0.6**), the prior `id` is reused. Otherwise, a new id is
minted: `<kind>-<sha1(kind|sorted_member_keys)[:12]>`. Candidates are
processed in sorted order, guaranteeing determinism — the same input
always produces the same IDs.

Stable IDs mean that an `informed_by_patterns` citation in a shipped ADR
remains valid after membership drifts (e.g. a third project joins the
group), as long as Jaccard on the original membership ≥ 0.6.

## 2. How to read a pattern group

The admin API response for a single group looks like:

```json
{
  "pattern_id": "adr-cloud-run-background-a3f2c8",
  "kind": "adr",
  "title": "ADR: background job runner (2 projects)",
  "score": 0.625,
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
  ],
  "index_age_minutes": 420
}
```

**`score`** — for `adr` / `spec_problem`: Jaccard similarity (0–1, higher
= more similar). For `failure_taxonomy`: raw occurrence count across
projects. For `role_prompt_delta`: `delta_pp` (percentage-point change
in acceptance rate). For `template_drift`: count of projects that added
the field locally.

**`members`** — list of contributing artifacts. Only structural metadata
is exposed here: `project_id`, `artifact_id`, and a
`decision_pill_or_summary` of ≤ 200 characters. No artifact bodies, no
raw frontmatter, no freshness data. To read the full artifact you must
use that project's per-project knowledge API directly.

**`index_age_minutes`** — how old the latest index run is. If this is
> 1440 (24 hours), the daily tick may have missed — check
`GET /v1/_admin/patterns/index/runs` for the last run's status and
`error_kind`.

**Concrete example.** The group above was produced as follows:

1. `kinds/adr.py` tokenised coder/adr-0041:
   `{cloud, run, jobs, scheduler, background, work}` and vibetrade/adr-0009:
   `{background, job, runner, cloud, run, jobs, scheduler}`.
2. Jaccard = |{cloud,run,jobs,scheduler,background}| /
   |{cloud,run,jobs,scheduler,background,work,job,runner}| = 5/8 = 0.625 ≥ 0.5
   floor → grouped.
3. `StableIdMatcher` found no prior group with overlapping members → minted
   `adr-cloud-run-background-a3f2c8`.

## 3. How to disable a pattern kind

### Disable one kind by raising its floor to 1.0

Setting a Jaccard floor to `1.0` means only identical token sets match,
which in practice is never true for natural-language titles. This
effectively disables the kind without removing it from the codebase.

```bash
# coder-core settings API — example for the 'adr' kind
curl -s -X PATCH "$CODER_CORE_URL/v1/_admin/settings" \
  -H "Authorization: Bearer $CODER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"patterns_indexer_adr_jaccard_floor": 1.0}'
```

For `spec_problem`: set `patterns_indexer_spec_jaccard_floor=1.0`.
For `role_prompt_delta`: set `patterns_indexer_role_delta_min_pp=100.0`
(delta can never exceed 100 pp).
For `failure_taxonomy` and `template_drift` (exact / key-set, no Jaccard
floor): there is no single knob — to suppress these kinds, use the
`kinds_filter` parameter on the manual run trigger and exclude them, then
delete the resulting rows from `pattern_groups` for the current run.

### Disable fleet-wide via environment variable

```bash
# Redeploy coder-core with this env var to disable all consumption
CODER_CROSS_PROJECT_PATTERNS_ENABLED=false
```

With this flag false, all consult calls return `404 not_enabled` and the
daily indexer job exits immediately with `error_kind='disabled'`. The
`pattern_groups` data is preserved; re-enabling the flag restores
service without a re-index.

### Disable per-project (contribution)

```bash
# Stop a project contributing to the index
curl -s -X PATCH "$CODER_CORE_URL/v1/projects/{project_id}" \
  -H "Authorization: Bearer $CODER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"share_patterns": false}'
```

Setting `share_patterns=FALSE` (or `NULL`) removes the project from the
next indexer run. The serve-time re-check in the consult handler strips
that project's members from any response immediately, without waiting for
a new run.

### Disable per-project (consumption)

```bash
# Stop a project's workers from consulting the endpoint
curl -s -X PATCH "$CODER_CORE_URL/v1/projects/{project_id}" \
  -H "Authorization: Bearer $CODER_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"fleet_patterns_enabled": false}'
```

`fleet_patterns_enabled=FALSE` makes consult calls from that project's
workers return `404 not_enabled`. The project's data can still appear in
other projects' consult responses (it still contributes if
`share_patterns=TRUE`).

## 4. How to interpret a `role_prompt_delta`

A `role_prompt_delta` group signals that a role-prompt edit in one project
correlated with an approval-rate shift. The key fields are `delta_pp` and
`sample_size_n`:

- **`delta_pp`** — percentage-point change in the role's acceptance rate
  between the before and after windows. A positive value means the edit
  improved the rate; negative means it degraded it. The magnitude is
  `|after_rate - before_rate| × 100`.
- **`sample_size_n`** — number of tasks in the after window that
  contributed to the after-rate measurement.

**Why small `n` makes the delta unreliable.** With `n=20` tasks in a
7-day after window, a single unusual task acceptance or rejection can
move the rate by 5 percentage points. The indexer's minimum `n=20`
(default `patterns_indexer_role_delta_min_sample_n`) is a noise floor,
not a confidence threshold. A delta computed from `n=20` is suggestive;
a delta from `n=200` is reliable.

**Recommendation:** treat a `role_prompt_delta` group as hypothesis-worthy
only when `sample_size_n ≥ 50`. Below 50, note the signal and monitor
for the next run before acting. At `n ≥ 50`, cross-check by reading the
actual prompt diff (via the project's per-project knowledge API), asking
whether the change substantively altered the role's decision criteria, and
comparing against the role's historical baseline.

**Do not act on a negative delta below `n=50`** — reverting a prompt
change is cheap, but if the `n` is small the measured degradation may
recover on its own as the after window accumulates more tasks.

## 5. How to propose a template promotion from `template_drift`

A `template_drift` group means one or more projects have added a field to
their local `system/<type>/_TEMPLATE.md` that the central
`coder-system/template/system/<type>/_TEMPLATE.md` does not have. If the
field has proven useful in those projects, it may be worth promoting to
the central template so new projects get it by default.

**Operator steps:**

1. **Identify the group.** Browse `GET /v1/_admin/patterns?kinds=template_drift`
   and find groups with `score ≥ 2` (field present in two or more
   projects). Higher score = broader adoption.

2. **Inspect the field.** Fetch the member projects' local templates via
   their per-project knowledge APIs to see the field name, type, and any
   YAML comment documenting its intent. Verify the field is genuinely
   useful and not project-specific.

3. **Open a PR to the central template.** Edit the appropriate file in
   `coder-system/template/system/<type>/_TEMPLATE.md`. Insert the new
   field near other optional fields. Add a YAML comment above it
   explaining what it is and when to use it. Mark it as optional (empty
   list or blank value in the template). Follow the same placement
   convention as `informed_by_patterns`.

4. **Reference the 0047 migration process.** Spec 0047 (template schema
   migration) defines how existing managed repos get the new field added
   to their local templates. Add the field to spec 0047's migration
   manifest, or note in the PR body that a follow-up migration dispatch is
   needed. The PR reviewer will confirm whether a migration is required
   for the current managed-repo fleet.

5. **Close the `template_drift` signal.** Once the central template is
   updated and the managed repos have the field added (via 0047), the
   next indexer run will find no diff for this `(artifact_type,
   field_name)` pair and the group will drop out of the latest run's
   results.

## 6. Privacy boundary

The patterns surface is designed so that **no artifact body or raw
frontmatter from project A can reach project B through any worker call
path**. This is enforced at multiple layers:

### What crosses tenant lines via the consult endpoint

Only the `PatternGroupConsultSafe` Pydantic model is returned to workers:

| Field | Max length | Notes |
|---|---|---|
| `project_id` | — | The project's opaque identifier, already known to any fleet operator |
| `artifact_id` | — | Opaque path like `adrs/0041`; not the title or body |
| `decision_pill_or_summary` | **200 chars** | First sentence of `## Decision`, hard-truncated at index time |
| `pattern_id` | — | Stable identifier only |

The following are explicitly **stripped** and never cross tenant lines:
artifact `body`, raw `frontmatter` fields, `freshness` / `last_verified_at`
detail, role-prompt diff hunks (for `role_prompt_delta`, only `delta_pp +
sample_size_n` are included).

### Technical guard: `Config.extra='forbid'`

`PatternGroupConsultSafe` and `PatternMemberConsultSafe` are defined with
`class Config: extra = 'forbid'`. This means adding any field to the
model that is not explicitly listed above causes the model to raise a
`ValidationError` at import time in the test suite — any accidental
content-bearing field addition is caught before it can ship.

A schema test asserts `Config.extra = 'forbid'` on both models. This test
is the runtime-detectable invariant; the code review process is the
human-readable one. Both must pass before any change to these models
ships.

### Admin scope does not bypass `share_patterns`

Admin tokens receive the same `share_patterns=TRUE` member filter as
project tokens. An operator with an admin token cannot see a
non-contributing project's knowledge through the patterns surface. To read
that project's artifacts directly, the operator must use the per-project
`/v1/projects/{id}/knowledge/` endpoints, which have separate auth scope.

### What the indexer stores

`pattern_groups.members` stores a JSONB array of `PatternMemberFull`
rows, which do contain the full `decision_pill_or_summary` and
`artifact_id`. These rows are stored in coder-core's DB (which is
single-tenant from the indexer's perspective — it is the fleet operator's
DB, not a per-project DB). The consult endpoint never returns
`PatternMemberFull`; it always reduces to `PatternMemberConsultSafe`
before writing the response.

## Related

- Spec [0048](../product-specs/wip/0048-cross-project-patterns.md) — full spec
- Design [0048](../designs/wip/0048-cross-project-patterns.md) — implementation detail
- ADR [0022](../adrs/0022-structural-jaccard-for-pattern-discovery.md) — Jaccard rationale + stable-id design
- ADR [0023](../adrs/0023-admin-api-and-consult-endpoint-as-pattern-surfaces.md) — surface selection rationale
- ADR [0024](../adrs/0024-share-patterns-column-as-enforcement-boundary.md) — `share_patterns` column enforcement
- Spec [0047](../product-specs/wip/0047-template-schema-migration.md) — template promotion migration process
