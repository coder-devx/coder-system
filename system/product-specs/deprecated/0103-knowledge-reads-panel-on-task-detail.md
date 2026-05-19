---
id: '0103'
title: Knowledge reads panel on task detail
type: spec
status: deprecated
owner: ro
created: '2026-05-18'
updated: '2026-05-19'
last_verified_at: '2026-05-19'
deprecated_at: '2026-05-19'
reason: >-
  Superseded by canonical spec 0099 (Worker Knowledge-Read
  Transparency). This was one of seven near-duplicate specs the
  founder/PM calibration loop emitted on 2026-05-18 for the same idea
  (surface worker knowledge-repo fetches on the task detail page).
  Consolidated 2026-05-19; distinct contributions folded into 0099.
served_by_designs: []
related_specs:
- admin-panel
- knowledge-api
- observability
parent: knowledge-and-admin
---

# Knowledge reads panel on task detail

**Phase:** wip
**Progress:** 0 / 5 acceptance criteria

## Problem

When a PM or Architect task completes with poor output — a stale spec, a surface-name cross-link, a missed sibling — operators have no quick way to see which knowledge artifacts the worker actually fetched. The only signal is the raw task transcript, behind a download link. Operators can't tell at a glance whether a bad draft was caused by missing grounding reads, misrouted artifact choices, or a reasoning failure. Diagnosing grounding quality today means downloading the transcript, searching for `gh api` calls, and manually mapping URLs to artifact paths — minutes of context-switching per task.

## Users / personas

- **Operators** reviewing a completed PM or Architect task to determine whether poor output was a grounding failure or a reasoning failure.
- **Operators** spot-checking grounding quality across a pipeline run to validate that workers are following their task contracts.

## Goals

- Make every knowledge artifact fetched during a task run visible inline on the task detail page, without downloading the transcript.
- Give operators a one-glance signal when a PM or Architect task ran with zero knowledge reads — the clearest indicator of a grounding failure.

## Non-goals

- Automated grounding scoring or pass/fail verdicts (that belongs to the consultant evaluate loop).
- Surfacing non-knowledge tool calls (general Bash commands, local file reads, edits) — those stay in the transcript.
- Alerting or Slack notifications based on knowledge-read counts.
- Real-time streaming of reads for an in-progress task.

## Scope

- A "Knowledge reads" section on the existing task detail page, listing each knowledge-repo artifact fetched during the run in call order, with artifact path and response byte count.
- A count chip on the task detail header alongside the existing cost and turn-count chips.
- A "No knowledge reads" warning state for completed PM and Architect tasks that have zero reads.
- A project-scoped admin API endpoint backing the panel.

## Acceptance criteria

- **AC1.** The task detail page for any completed task shows a "Knowledge reads" section listing each knowledge-repo artifact fetched during the run, in call order, with the artifact path and the response byte count.
- **AC2.** The section renders without downloading the task transcript; data is served by a dedicated endpoint accessible to any admin-panel user with access to the task's project.
- **AC3.** A count chip on the task detail header shows the total number of knowledge reads alongside the existing turn-count and cost chips; a zero count is visually distinct from a non-zero count.
- **AC4.** Completed PM or Architect tasks with zero knowledge reads display a "No knowledge reads" warning in the section, so operators can immediately distinguish a grounding failure from a task type that legitimately makes few reads.
- **AC5.** The Knowledge reads section is covered by at least one automated test asserting correct rendering for both a zero-read fixture and a non-zero-read fixture.

## Metrics

- Fraction of PM and Architect draft-mode tasks with zero knowledge reads, visible from the panel; target below 5% once the feature has been live for 30 days.
- Qualitative drop in operator time-to-diagnose grounding failures (no SLO set at this stage).

## Open questions

- Should reads that go to non-knowledge paths (e.g. source-repo code searches) be excluded from the panel, shown separately, or mixed in with a distinct label?
- Does the panel need pagination for tasks that made a large number of fetches, or is a capped list with a "view all" link sufficient for the common case?

## Links

- Related specs: [admin-panel](../knowledge/admin-panel.md), [knowledge-api](../knowledge/knowledge-api.md), [observability](../pipeline/observability.md)
