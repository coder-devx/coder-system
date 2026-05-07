# reports/

Unstructured archive for time-bound analyses, audits, and one-off
write-ups that don't fit any typed artifact category.

Files here are **not** knowledge artifacts:

- No frontmatter requirement.
- Not in any `registry.yaml`.
- Not validated by `scripts/validate.py`.
- Not surfaced by `scripts/freshness.py`.
- Filenames typically include a date (`<topic>-YYYY-MM-DD.md`) so the
  point in time is obvious.

The expectation is that any **actionable** finding from a report has
already been folded into the appropriate typed artifact — a new spec,
an ADR, a runbook update, an edit to a role's task contract — by the
time the report lands here. The report itself is reference material:
useful for context, not load-bearing.

If a report grows into something the system depends on, promote it
into the right artifact type (spec, design, runbook, …) and remove it
from this folder.
