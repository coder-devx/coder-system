# Task: funnel review

You are running Analyst in **funnel_review mode** (spec 0075). Interpret the
PostHog event stream for one Studio product and emit a funnel interpretation
report plus ranked experiment proposals.

## Inputs

- Task prompt: product name, project ID, funnel stage focus (optional; if
  omitted, review the full funnel top-to-bottom), lookback window (default
  30 days).
- PostHog event data fetched via PostHog Query API:
  - Funnel conversion: `POST /api/projects/{project_id}/insights/funnel/`
  - Retention: `POST /api/projects/{project_id}/insights/retention/`
  - Breakdown by property (e.g. cohort, referrer): standard PostHog
    breakdown query.
- Experiment log from `GET /v1/projects/{id}/studio/experiments` — read to
  avoid re-proposing already-tested interventions.

## What you do

1. Fetch funnel conversion rates for each stage (visitors → signups →
   activations → paying) over the lookback window.
2. Identify the stage with the largest relative drop (the inflection point).
3. Drill into the inflection point: break down by cohort, referrer, or user
   property to find a directional explanation.
4. Check the experiment log for prior interventions at this inflection point.
5. Propose up to three experiments targeting the inflection point, ranked by
   estimated impact-to-effort ratio.
6. Emit structured output (see below).

## Output format

**Single bare JSON object, no fence, no prose.**

```json
{
  "project_id": "<uuid>",
  "lookback_days": 30,
  "funnel_summary": {
    "visitors": 1200,
    "signups": 340,
    "activations": 89,
    "paying": 12
  },
  "inflection_point": "signup_activation",
  "interpretation": "Markdown paragraph — what the data shows and the directional explanation. Minimum 50 characters.",
  "experiment_proposals": [
    {
      "rank": 1,
      "hypothesis": "Prompting users toward 'create first task' on day 2 will increase activation rate.",
      "metric": "signup_activation_rate",
      "effort": "low",
      "estimated_lift_pp": [10, 20]
    }
  ],
  "report_markdown": "Full Markdown interpretation report (echoes interpretation + proposals in human-readable form)."
}
```

`experiment_proposals` must have at least one item. Each `hypothesis` must be
≥ 30 characters.

## Completion contract

The orchestrator writes the `report_markdown` to the product's knowledge
artifacts and appends `experiment_proposals` to the experiment queue
(`POST /v1/projects/{id}/studio/experiments`). The Founder reads both at the
next weekly review. Exit 0 on success.
