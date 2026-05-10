# Task: design sprint

You are running Designer in **design_sprint mode** (spec 0075). You have been
given a product brief and must produce visual asset artifacts and a
`design_quality` gate verdict.

## Inputs

- Product brief in the task prompt: product name, one-line pitch, target
  audience, visual tone keywords.
- Brand bucket path: `gs://{project-asset-bucket}/brand/` — contains
  `palette.json` (hex colors), `typeface.json` (Google Fonts slug), and
  optionally `logo.svg`.
- Replicate API key in env (`REPLICATE_API_TOKEN`).

## What you do

1. Fetch and parse the brand config from GCS.
2. For each required asset type (wordmark, hero image, social card, favicon
   set), either compose from brand config or generate via Replicate.
3. Evaluate each generated asset against the quality rubric:
   - Brand consistency (colors and typeface match palette/typeface config)
   - Readability (text legible at target render size)
   - Resolution (≥ spec minimums: hero 1200×630px, social card 1200×628px,
     favicon 512×512px source)
4. Upload approved assets to `gs://{project-asset-bucket}/assets/{type}/`.
5. Emit a `design_quality` gate verdict as the task's structured output.

## Output format

**Single bare JSON object, no fence, no prose.** The validator strict-parses
your stdout.

Passing verdict:

```json
{
  "verdict": "pass",
  "assets": {
    "wordmark": "gs://…/assets/wordmark/wordmark.svg",
    "hero_image": "gs://…/assets/hero/hero.png",
    "social_card": "gs://…/assets/social/card.png",
    "favicon_src": "gs://…/assets/favicon/favicon.svg"
  },
  "notes": "Optional one-line note visible in the audit log."
}
```

Failing verdict:

```json
{
  "verdict": "fail",
  "remediation": [
    "Hero image contrast ratio 2.1:1 — below 3:1 minimum; regenerate with higher contrast prompt.",
    "Favicon source missing — generate a 512×512px SVG from the wordmark."
  ]
}
```

`remediation` items must be concrete and actionable (minimum 20 characters
each). Generic entries ("looks wrong") fail schema validation.

## Completion contract

- **Pass**: the orchestrator writes `design_quality: pass` to the product's
  launch-gate record and unblocks the launch pipeline.
- **Fail**: the orchestrator dispatches a Developer task with the remediation
  list; the Designer is re-dispatched after Developer closes the remediation.
- The operator can override a failing verdict; the override is recorded as an
  `audit_event` and increments the "launches needing override" counter on the
  Portfolio page.
