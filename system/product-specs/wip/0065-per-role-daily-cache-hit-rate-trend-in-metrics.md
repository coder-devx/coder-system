---
id: '0065'
title: Per-role daily cache hit rate trend in metrics
type: spec
status: wip
owner: ro
created: '2026-05-03'
updated: '2026-05-03'
last_verified_at: '2026-05-03'
deprecated_at: null
reason: null
served_by_designs: []
related_specs: []
parent: pipeline-operations
---

# Per-role daily cache hit rate trend in metrics

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

The metrics page at `/projects/{id}/metrics` shows an aggregate prompt-cache hit rate per role for the selected period (1d / 7d / 30d) via `cache_stats: RoleCacheStats[]`. Operators can see *that* a role has a low hit rate, but cannot tell *when* it dropped. After a prompt-assembly change lands (e.g. coder-devx/coder-core#80 reordered prompt sections for cache reuse today), the stable prefix may break for one or more roles — the aggregate masks whether the regression is new or chronic. Operators currently have no way to correlate a cache-hit-rate drop with a specific day or PR without manually inspecting individual task rows.

## Users / personas

- **Operators** using the `/projects/{id}/metrics` page who run prompt-engineering changes or want to verify that a cache-optimisation PR is working as expected.

## Goals

- Expose a per-role, per-day breakdown of cache hit rate on the metrics page for the selected period.
- Make a sudden day-over-day drop visually obvious so operators can identify the regression date at a glance.
- Keep the existing period-aggregate table as the quick summary; the daily breakdown is a secondary, scrollable section beneath it.

## Non-goals

- Real-time cache-drop alerts or push notifications (belongs to escalations spec).
- Per-task cache token detail (already on the task detail page).
- Cache-optimisation recommendations or automatic remediation.
- Sub-day granularity.
- Changing the shape of the existing `cache_stats` aggregate field.

## Scope

Backend: a new `daily_cache_stats` array added to the `GET /v1/projects/{id}/metrics` response. Each element covers one (date × role) pair for the selected period and carries: `date` (ISO-8601 `YYYY-MM-DD`), `role`, `cache_read_tokens`, `cache_creation_tokens`, `total_input_tokens`, `cache_hit_rate` (`cache_read_tokens / total_input_tokens`, or `null` when `total_input_tokens = 0`), and `task_count`.

Frontend: a new "Daily Cache Trend" section on the Metrics page. Dates are columns (oldest → newest), roles are rows. Each cell shows the hit rate coloured by threshold. A `▼` indicator marks any cell where the hit rate fell ≥ 30 pp versus the preceding day for that role.

## Acceptance criteria

- [ ] AC1: `GET /v1/projects/{id}/metrics?period=7d` returns a `daily_cache_stats` array with one object per (date, role) pair covering the 7-day window; `date` is `YYYY-MM-DD` UTC; `cache_hit_rate` is `null` when `total_input_tokens = 0`.
- [ ] AC2: The Metrics page `/projects/{id}/metrics` renders a "Daily Cache Trend" section below the existing aggregate table; for a 7-day or 30-day period, dates appear as columns and roles as rows; the 1d period shows a single date column.
- [ ] AC3: Cells with `cache_hit_rate ≥ 0.50` render in green, `0.20–0.49` in amber, `< 0.20` in red; `null` cells render as `—`.
- [ ] AC4: Any cell where the hit rate dropped ≥ 30 percentage points compared to the same role's preceding-day cell renders a `▼` indicator, enabling operators to spot the regression date without scanning the whole table.
- [ ] AC5: A backend integration test seeds tasks with known `cache_creation_input_tokens` and `cache_read_input_tokens` values across two roles and two dates, calls the metrics endpoint, and asserts the `daily_cache_stats` rollup matches the expected per-(date, role) aggregates.

## Open questions

- For a 30-day period, should the daily breakdown default to weekly buckets to keep the table width manageable, or always show daily columns?
- Should the section be collapsed by default (disclosure triangle) to avoid growing the metrics page length significantly?

## Links

- Metrics page: `coder-admin/src/pages/Metrics.tsx`
- Existing aggregate type: `RoleCacheStats` in `coder-admin/src/api/client.ts`
- Prompt-reorder PR that motivates this spec: coder-devx/coder-core#80 (merged 2026-05-03)
