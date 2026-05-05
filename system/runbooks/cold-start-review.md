---
id: cold-start-review
title: Cold-start ingestion PR review checklist
type: runbook
status: active
owner: ro
created: 2026-05-05
updated: 2026-05-05
applies_to_services: [coder-core]
applies_to_integrations: [github]
---

# Cold-start ingestion PR review checklist

Guide for reviewing the pull request opened by `coder project ingest`.
The PR populates a brand-new knowledge repo from the project's source code
and commit history. This runbook tells you what to look for, what to fix
before merging, and what to do if a category came back empty.

## When to run this

After `coder project ingest {project} --wait` prints a PR URL, or after you
find an open `cold-start: {project}` PR in the knowledge repo.

## Who can run this

Any operator with write access to the knowledge repo. No special permissions
beyond `gh pr review` and a merge button.

## What the cold-start PR contains

The PR body includes a per-category artifact count, for example:

```
cold-start: vibetrade

Services:  4 drafted
Designs:   6 drafted (wip)
ADRs:      3 drafted
Glossary: 14 terms appended
```

The ingester writes:
- **`system/services/`** — one `.md` per detected top-level deployable unit,
  with frontmatter derived from the repo's directory structure and CI config.
- **`system/designs/wip/`** — numbered WIP design files for each major logical
  component the architect worker identified.
- **`system/adrs/`** — ADRs reconstructed from commit messages that contained
  decision rationale (keywords: `decide`, `chose`, `rejected`, `tradeoff`, etc.).
- **`system/glossary.md`** — new terms appended to the "Project terms" section.

All ingested artifacts carry `ingestion_provenance` in their frontmatter.
The `registry.yaml` files are updated in the same commit.

## How to read `ingestion_provenance`

```yaml
ingestion_provenance:
  source_paths: [src/api/routes.py, src/api/models.py]
  source_commit: "a1b2c3d"
  ingested_at: "2026-05-05T14:32:00Z"
  prompt_id: cold_start_v1
  model: claude-opus-4-6
  confidence: 78
  human_edited: false
```

| Field | Meaning |
|---|---|
| `source_paths` | Files the ingester read to draft this artifact. Use these to verify the artifact against the actual code. |
| `source_commit` | The HEAD commit of the source repo at ingestion time. Diffs against this commit show what's changed since. |
| `ingested_at` | ISO-8601 timestamp. Artifacts ingested more than a week ago before you're reviewing them may already be stale. |
| `prompt_id` | The ingestion prompt template used. `cold_start_v1` is the initial release; later versions may produce different shapes. |
| `model` | The model that generated the artifact. Useful context when judging confidence thresholds. |
| `confidence` | 0–100. Reflects the model's self-assessed faithfulness to the source: how well the artifact's claims can be backed by `source_paths`. Below 50 warrants extra scrutiny; below 30 consider dropping or rewriting. |
| `human_edited` | Starts as `false`. Flips to `true` after merge when the knowledge-freshness Action runs. Once `true`, future re-runs of the ingester skip this artifact (it won't be overwritten). |

## Review order

Work through the categories in descending signal quality:

### 1. Services (highest signal — check first)

**Goal:** Do the detected services match the actual deployable units in the repo?

- Open each file under `system/services/`. Check `id`, `name`, and the `What it does` section.
- Cross-reference `source_paths` with the repo layout. A service inferred from `Dockerfile` or a Cloud Run config is usually accurate; one inferred from a directory name alone is weaker.
- Common problems:
  - A monolith detected as multiple services — merge the files and update `registry.yaml`.
  - A library or tool incorrectly classified as a service — delete it.
  - Missing a service the ingester didn't detect (no clear deployment boundary) — author it manually after merging.
- If `confidence < 50`, read `source_paths` carefully. Edit the artifact rather than deleting unless the service simply does not exist.

### 2. Designs (medium signal)

**Goal:** Do the WIP designs describe real logical components?

- Check `system/designs/wip/`. Each file should describe one coherent logical unit.
- Verify the `implements_specs` field is blank (cold-start designs have no spec yet — leave it empty; the PM will wire it up on the first spec cycle).
- Watch for designs that overlap heavily — the ingester may have split one component across two files. Merge them, keep the lower-numbered ID, delete the other, and update `registry.yaml`.
- `confidence` below 60 for a design usually means the architect worker saw conflicting patterns (e.g. the component is being rewritten mid-flight). Mark it with a comment and lower `confidence` manually if you edit it significantly.

### 3. ADRs (lowest confidence tolerated)

**Goal:** Are the decisions real, still relevant, and correctly framed?

ADRs reconstructed from commit history are inherently noisier than the other categories. Review each one:

1. Read the `Context` and `Decision` sections.
2. Check `source_paths` — it will point to the commit(s) that mentioned the decision. Is the rationale still accurate?
3. Decide: **keep and edit**, or **drop**.

**When to drop an ADR:**
- The commit-message evidence is thin (a single line mentioning "chose X" with no rationale).
- The decision has been reversed or superseded since the commit.
- The `Context` section contains hallucinated details not present in `source_paths`.

**When to edit an ADR:**
- The substance is right but the framing is wrong (e.g. the "Consequences" section is too optimistic).
- The rationale is real but the `Options considered` section is sparse — expand it.
- The decision is still live but the language is ambiguous.

Never edit a merged ADR's `Decision` or `Rationale` sections — if the decision has changed, mark the existing ADR `superseded` and write a new one per the repo rules.

### 4. Glossary (check last)

**Goal:** Useful terms, no duplicates, no `(alt)` entries remaining.

- Scroll the appended terms in `system/glossary.md`.
- Any term with `(alt)` in its name is an alternative definition the ingester wasn't sure about. Pick the better definition, delete the duplicate entry, and rename the winner to remove the `(alt)` suffix.
- Remove terms that are too generic (e.g. "Service", "Model") — these add noise rather than domain clarity.
- Terms with very low `confidence` (visible in the PR diff comments if the ingester emits them) may need a rewrite; otherwise a quick sense-check is sufficient.

## What to do when a category came back empty

| Category empty | What it means | Action |
|---|---|---|
| **Services** | The repo isn't structured by top-level deployable unit (e.g. a monorepo with no clear service boundaries, or a pure library). | Author `system/services/` entries manually after reviewing the repo's deployment config. Mark them with no `ingestion_provenance` (human-authored). |
| **Designs** | The architect worker found no clear logical components — common for very small repos or pure library packages with no internal subsystem structure. | Check repo size. Under ~2 kLoC or a library with a single public API, no designs may be correct. Otherwise run `coder project ingest {project} --re-analyze designs` to retry with a relaxed threshold. |
| **ADRs** | Commit history lacks decision rationale. Normal for projects that use a separate ADR directory or a linear squash-merge workflow. | No action required. Author ADRs manually as decisions are made going forward. |
| **Glossary** | Very focused codebase with domain terms already familiar from the language / framework. | No action required. Add terms manually as the team identifies ambiguous vocabulary. |

## Handling `(alt)` glossary entries

The ingester appends an `(alt)` suffix when it found two plausible definitions
for the same term in different files. Example:

```
**Pipeline (alt)** — the ordered sequence of worker roles that process a spec from draft to merge. *(source: src/core/pipeline.py)*
**Pipeline** — a Cloud Run Job that executes a single worker task. *(source: docs/architecture.md)*
```

To resolve:
1. Identify which definition is more precise and consistent with how the term is used in the codebase.
2. Keep that entry; delete the other.
3. Remove the `(alt)` suffix from the kept entry's term.
4. If both are correct but cover different scopes, rename them to be unambiguous (e.g. `Pipeline (orchestration)` vs `Pipeline (infra)`).

## Re-running the ingester

After the cold-start PR is merged and the knowledge-freshness Action has run
(it flips `human_edited: true` on any artifact you touched), it is safe to
re-run the ingester:

```sh
coder project ingest {project} --from https://github.com/{org}/{repo} --ref main --wait
```

Re-run behavior:
- Artifacts where `human_edited: true` are **skipped** — the ingester will not overwrite human edits.
- New artifacts detected since the first run are proposed in a fresh PR.
- Updated artifacts (same ID, source has changed significantly) are proposed as edits in the same PR.

Re-runs are safe at any time after the first merge. Running before merge risks
a conflict between the open PR and the new run's output.

## Related

- Spec: [product-specs/wip/0045-cold-start-ingestion.md](../product-specs/wip/0045-cold-start-ingestion.md) (if present)
- Runbook: [onboard-project](./onboard-project.md) — Step 11 triggers this checklist
- Template: `template/system/services/_TEMPLATE.md`, `template/system/designs/_TEMPLATE.md`, `template/system/adrs/_TEMPLATE.md` — all carry the optional `ingestion_provenance` block
