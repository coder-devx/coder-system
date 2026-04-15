---
id: "0008"
title: CI validation of the knowledge repo
type: adr
status: accepted
date: 2026-04-08
deciders: [ro]
relates_to_designs: [knowledge-repo-model]
---

# ADR 0008 — CI validation of the knowledge repo

## Context

The knowledge repo's value depends on its integrity:
- Frontmatter must parse and contain required fields.
- Registry YAML must parse.
- Cross-link IDs (`decided_by`, `affects_services`, etc.) must resolve.
- Files in artifact folders must be listed in their `registry.yaml`.

Without enforcement, drift is inevitable. The future Coder API will
read these files programmatically — a broken cross-link is a runtime
bug for every worker.

## Options considered

1. **No CI, trust contributors** — shortest path, guaranteed to break.
2. **CI script in this repo running on every PR** — small Python script
   that validates frontmatter, parses every `registry.yaml`, and walks
   cross-links. Runs in GitHub Actions. Fails the PR on any error.
3. **Validation in the future Coder API** — too late, the API would
   reject already-merged content.

## Decision

CI validator in this repo. A Python script at `scripts/validate.py`
runs on every PR via `.github/workflows/validate.yml`. The script:

1. Parses frontmatter on every `*.md` under `system/` and `template/`
   (excluding `README.md`, `REGISTRY.md`, `_TEMPLATE.md`).
2. Parses every `registry.yaml`.
3. Verifies that every file in an artifact folder is listed in the
   folder's registry, and every registry entry points at a real file.
4. Walks cross-link fields and verifies referenced IDs exist.
5. Exits non-zero on any failure.

## Rationale

The cost of running a 200-line Python script is nothing. The cost of a
broken cross-link reaching `main` is real once the Coder API is reading
this repo at runtime.

## Consequences

- Positive: drift is caught at PR time, not at agent runtime.
- Positive: contributors get instant feedback.
- Negative: schema changes require updating the validator. That's a
  feature, not a bug — schema changes should be deliberate.
- Follow-up: as new artifact types are added, extend the validator's
  required-field map.
