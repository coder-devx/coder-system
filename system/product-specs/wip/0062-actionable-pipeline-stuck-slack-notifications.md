---
id: '0062'
title: Actionable pipeline-stuck Slack notifications
type: spec
status: wip
owner: ro
created: '2026-05-02'
updated: '2026-05-02'
last_verified_at: '2026-05-02'
deprecated_at: null
reason: null
served_by_designs:
- '0067'
related_specs:
- escalations
- admin-panel
- task-orchestration
parent: pipeline-operations
---

# Actionable pipeline-stuck Slack notifications

**Phase:** wip
**Progress:** 0 / 6 acceptance criteria

## Problem

When the escalation watcher fires a Slack alert for a stuck pipeline, the message today contains no task ID, no failure stage, and no link to the admin panel. The on-call must navigate manually — project list → pipeline view → find the stalled run — costing minutes at the worst moment. The result: most escalations sit unacknowledged until morning, even when the watcher is correctly detecting and paging the stall.

## Users / personas

- **On-call human** — receives a Slack page at any hour; needs to triage in under 2 minutes and either fix the stall or hand off, without consulting runbooks.
- **Project operator** — configures escalation settings; needs confidence that any page sent will be immediately actionable and not require the on-call to dig.

## Goals

- Every Slack escalation message (L0 channel post and L1 on-call DM) contains: project name, task ID, current pipeline stage, trigger kind (stall / failure-streak / SLA breach), how long the pipeline has been stuck, and a `View in admin` button that deep-links directly to the admin panel task detail page.
- The on-call reaches the right task in the admin panel with one tap — no additional navigation.
- Mean time to first ack decreases as a measurable outcome of this change.

## Non-goals

- Changing escalation ladder thresholds, rungs, or PagerDuty routing — covered by [escalations](./escalations.md).
- Redesigning the admin panel task detail page.
- Adding new notification channels (email, SMS, mobile push).
- Quiet hours, on-call rotation, or per-project schedule changes.

## Scope

- Define the Slack Block Kit message template used for L0 channel posts and L1 on-call DMs, specifying all required fields and button layout.
- Introduce `CODER_ADMIN_BASE_URL` env var and use it to construct the per-task deep-link URL (`{base}/projects/:projectId/pipeline/:taskId`).
- Extend the escalation Slack dispatcher to populate the new fields; no new database tables required.
- Ensure the interactive `Ack` button (already wired to `POST /v1/_hooks/slack/escalation_ack`) and the new `View in admin` button both appear in L0 and L1 messages.

## Acceptance criteria

- [ ] AC1: An L0 channel Slack message for a `stall` trigger includes: project name, task ID, current pipeline stage, trigger kind label, human-readable blocked duration (e.g. "stalled for 1 h 23 m"), an `Ack` interactive button, and a `View in admin` button that resolves to `{CODER_ADMIN_BASE_URL}/projects/:projectId/pipeline/:taskId`.
- [ ] AC2: An L1 on-call DM contains the same fields and interactive buttons as the L0 message — no information is dropped when the watcher advances rungs.
- [ ] AC3: A `failure_streak` trigger message includes the streak count, the most-recent failed task's ID, and the stage at which it failed.
- [ ] AC4: Clicking `View in admin` lands the on-call directly on the stuck task's detail page — not the project pipeline list, not the escalations list — with no further navigation required.
- [ ] AC5: The `Ack` interactive button posts to `POST /v1/_hooks/slack/escalation_ack`; the escalation row transitions to `acknowledged` and the Slack message updates to show the acknowledging user's display name within 3 seconds.
- [ ] AC6: End-to-end human QA on a test project: receive a synthetic stall alert in Slack, click `View in admin`, reach the task detail page, ack from the Slack button — completed in under 2 minutes without consulting documentation or the admin panel's navigation.

## Metrics

- Mean time from escalation L0 fire to first ack (already captured in escalation row timestamps — no new instrumentation needed).
- Share of escalations acked at L0 vs L1: a higher L0 ack rate is the leading indicator that messages are now actionable.
- Escalations reaching L2 (PagerDuty) per project-week — expected to decrease once messages carry enough context to unblock the on-call without a phone call.

## Open questions

- `CODER_ADMIN_BASE_URL` must be configured for deep links to resolve. Should the dispatcher warn at startup when it is absent, or fail-open by omitting the button while still sending the text fields? Recommendation: omit the button gracefully and log a config warning so the message remains useful even in local-dev environments without a public URL.
- Should `View in admin` link to the task detail page (`/projects/:id/pipeline/:taskId`) or the escalation detail page (`/projects/:id/escalations/:escalationId`)? The task page has logs; the escalation page has rung history. Propose task page as the primary button, with a secondary plain-text "See escalation" URL for operators who need the rung view.

## Links

- Designs: (none yet — may reuse the existing escalations design once message format is locked)
- Related specs: [escalations](./escalations.md), [admin-panel](./admin-panel.md), [task-orchestration](./task-orchestration.md)
