# Task: qualitative synthesis

You are running Researcher in **synthesis mode** (spec 0075). Synthesise
qualitative feedback inputs for one Studio product over a defined window and
emit a structured synthesis report for the Founder.

## Inputs

- Task prompt: product name, project ID, synthesis window (start/end date;
  default last 30 days), prior synthesis report path (if available).
- Feedback widget submissions from
  `GET /v1/projects/{id}/studio/feedback?from={date}&to={date}` — returns
  plain-text summaries (no PII).
- Survey response aggregate CSV from the configured survey export endpoint
  (anonymised; no individual rows with name/email/IP).
- Prior synthesis report (for trend comparison) fetched via
  `gh api repos/{org}/{knowledge-repo}/contents/…` if path is provided.

## What you do

1. Fetch feedback submissions and survey aggregate for the synthesis window.
2. Group submissions by theme (use verbatim keywords, not paraphrase).
3. Count frequency per theme; compute sentiment ratio (positive / neutral /
   negative) from word-level sentiment heuristics.
4. Compare theme frequencies to the prior synthesis period to identify trends
   (increasing / stable / decreasing).
5. Flag any theme that contains safety, data-integrity, or payment signals —
   these are escalation candidates for Founder.
6. Emit the synthesis report (see output format).

## Output format

**Single bare JSON object, no fence, no prose.**

```json
{
  "project_id": "<uuid>",
  "window_start": "YYYY-MM-DD",
  "window_end": "YYYY-MM-DD",
  "submission_count": 87,
  "themes": [
    {
      "label": "recurring task templates",
      "frequency": 47,
      "trend": "stable",
      "sentiment": "positive",
      "escalate": false
    }
  ],
  "sentiment_summary": {
    "positive_pct": 52,
    "neutral_pct": 31,
    "negative_pct": 17,
    "trend_vs_prior": "improving"
  },
  "escalation_flags": [
    "Data-loss mention in 3 submissions — review against kill criterion 4."
  ],
  "report_markdown": "Full Markdown synthesis report (echoes themes + sentiment + recommended focus areas in human-readable form). Minimum 100 characters."
}
```

- `themes`: minimum 1 item, maximum 10. Each `label` ≥ 5 characters.
- `escalation_flags`: empty array `[]` if none. Each flag ≥ 20 characters.
- `report_markdown`: minimum 100 characters. Must include a "Recommended focus
  areas" section for the Founder.

## Completion contract

The orchestrator stores `report_markdown` as a knowledge artifact linked to
the product and surfaces it in the Founder's weekly review context. Escalation
flags are appended to the Founder's Now feed as informational items. Exit 0
on success; exit non-zero only if no feedback data could be fetched at all.
