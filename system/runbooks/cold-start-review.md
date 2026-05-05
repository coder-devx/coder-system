---
id: cold-start-review
title: Cold-start ingestion PR — review checklist
type: runbook
status: active
owner: ro
created: 2026-05-05
updated: 2026-05-05
last_verified_at: 2026-05-05
applies_to_services: [coder-core]
applies_to_integrations: [github]
---

# Cold-start ingestion PR — review checklist

Guide for reviewing the PR opened by `coder project ingest`. The PR
populates a brand-new knowledge repo from the project's source code; it
must be reviewed by a human before merging. This runbook tells you what
to look for, in what order, and what to do when something looks wrong.

## When to run this

After running Step 11 of [onboard-project](./onboard-project.md): the
ingester opens a PR titled `cold-start: {project}` against the project's
knowledge repo and prints the URL. Open that URL and follow this runbook
before clicking **Merge**.

## Who can run this

Anyone with write access to the project's knowledge repo. No special
tooling required beyond a browser and `gh` CLI for spot-checks.

## What the cold-start PR contains

The PR body lists artifact counts per category:

| Category | What it contains |
|---|---|
| `services/` | One file per detected top-level deployable unit |
| `designs/wip/` | One file per detected logical subsystem or cross-cutting concern |
| `system/adrs/` | One ADR per decision reconstructed from commit history / code comments |
| `system/glossary.md` | Domain terms extracted from code identifiers, docs, and READMEs |

Each file has `ingestion_provenance` in its frontmatter (services,
designs, ADRs) or in the PR body (glossary). The PR body also shows the
source repo, commit SHA, model version, and overall confidence
distribution.

## How to read `ingestion_provenance`

```yaml
ingestion_provenance:
  source_paths: [src/auth/, src/api/auth_router.py]
  source_commit: "a3f9c12"
  ingested_at: "2026-05-05T14:22:01Z"
  prompt_id: cold_start_v1
  model: claude-opus-4-6
  confidence: 82
  human_edited: false
```

| Field | Meaning |
|---|---|
| `source_paths` | The files the ingester read to produce this artifact. Use these to cross-check the artifact's claims against the actual code. |
| `source_commit` | The git SHA the ingester read at. If the repo has moved on, some details may be stale. |
| `ingested_at` | When the artifact was generated. |
| `prompt_id` | The ingestion prompt template used. `cold_start_v1` is the baseline; future revisions will use a higher version. |
| `model` | The Claude model that produced the artifact. |
| `confidence` | 0–100. Reflects how directly `source_paths` supports the artifact's claims. **≥80**: high-signal, read but trust; **60–79**: review for gaps; **<60**: treat as a draft, verify all claims before merging. |
| `human_edited` | Starts `false`. A post-merge GitHub Action flips it to `true` the first time a human commit touches the file. Once `true`, a re-run skips this artifact. |

## Review order

Work top-to-bottom in confidence: highest-signal categories first.

### 1. `services/` — highest signal

Services are the most concrete: does the ingester's list of deployable
units match what you know about the codebase?

- **Check completeness**: are any obvious services missing? Look for
  top-level Dockerfiles, Cloud Run service definitions, or
  separate `package.json` / `pyproject.toml` files in sub-dirs that
  weren't picked up.
- **Check accuracy**: does each service file's "What it does" match
  the actual service?
- **Check `source_paths`**: a service whose only source path is a
  README is lower-confidence than one rooted in the service's main
  module.

### 2. `designs/wip/` — medium signal

Designs capture logical cross-cutting concerns (auth, multi-tenancy,
background tasks). They're more interpretive than services.

- Verify the `implements_specs` and `affects_services` links resolve
  (the registry validates these, but a newly minted registry starts
  empty, so links to non-existent entries will fail validation).
- For each design, check that the "Design" section reflects real
  behaviour, not aspirational comments in the code.
- Drop designs that describe library internals the project doesn't own
  (e.g. an `orm-internals` design extracted from SQLAlchemy usage).

### 3. `system/adrs/` — lowest confidence tolerated

ADRs reconstructed from commit history may have stale rationale.

- **Read the `source_paths`**: ADRs sourced only from commit messages
  (e.g. `source_paths: [.git/log]`) carry more uncertainty than those
  backed by an `ARCHITECTURE.md` or a design doc.
- **When to drop vs. edit**:
  - **Drop** if: the commit evidence is thin (a single merge commit,
    no design doc), the decision is obsolete, or the stated
    alternatives were never real candidates.
  - **Edit** if: the substance is correct but the framing is wrong,
    the rationale section is too generic, or the consequences are
    missing but inferable.
- ADRs are append-only once merged. If you edit one here before
  merge, that's fine — it hasn't been merged yet.

### 4. `system/glossary.md` — review last

- Check for `(alt)` entries: these are alternative definitions for
  the same term. Pick the better one, delete the `(alt)` entry, and
  remove the confidence annotation (`*(confidence: N/100)*`).
- Remove any confidence annotations you don't want to keep in the
  permanent glossary.
- Add missing terms that are obvious from the codebase but weren't
  picked up (the ingester focuses on identifiers — it may miss
  business-domain concepts that aren't in code).

## When a category came back empty

| Empty category | What it means | What to do |
|---|---|---|
| `services/` | The repo isn't structured by top-level deployable unit (e.g. a monolith or a library) | Author `services/` entries manually after the review; a single entry for the monolith is fine |
| `designs/wip/` | The architect worker found no identifiable logical subsystems, or the repo is very small / a library | Check if the codebase is under ~2 kLoC or is a pure library; if so, empty designs is correct — skip |
| `system/adrs/` | Commit history lacks explicit decision rationale | Normal; nothing to do. The first ADRs will be written by the Architect worker as the project runs |
| `system/glossary.md` | Very focused codebase with few domain-specific terms | Optional to fill manually. Not a blocker for merge |

## How to handle `(alt)` glossary entries

The ingester appends `(alt)` when it detects conflicting definitions
for the same term from different source paths:

```
**pipeline (alt)** — the sequence of Cloud Run Jobs triggered per
task. *(confidence: 61/100)*
```

Resolution steps:

1. Read both entries (the original and the `(alt)` version).
2. Pick the definition that is more precise and more project-specific.
3. Delete the entry you didn't pick (including the `(alt)` suffix and
   confidence annotation on the one you keep).
4. Normalise the term casing to match usage in the rest of the file.

If both definitions are equally good but complementary, merge them
into one entry rather than keeping two.

## Re-running the ingester

After the cold-start PR is merged, you can re-run the ingester at any
time to pick up changes to the source repo:

```sh
coder project ingest {project} --from https://github.com/{org}/{repo} --ref main --wait
```

Re-run behaviour:
- Artifacts where `human_edited: true` are **skipped** — the ingester
  assumes a human has taken ownership of those files.
- Artifacts where `human_edited: false` are **proposed as updates** if
  the ingester's output differs from the current file.
- New artifacts (services, designs, ADRs) not present in the current
  knowledge repo are **always proposed**.

The re-run opens a new PR with the same title prefix (`cold-start:
{project}`) and a timestamp suffix. Review it with the same checklist.

## Related

- Runbook: [onboard-project](./onboard-project.md) — Step 11 runs the
  ingester.
- Spec: 0045 — cold-start ingestion spec (defines `ingestion_provenance`
  schema and ingester behaviour).
- Templates: `template/system/services/_TEMPLATE.md`,
  `template/system/designs/_TEMPLATE.md`,
  `template/system/adrs/_TEMPLATE.md` — all carry the optional
  `ingestion_provenance` comment block.
