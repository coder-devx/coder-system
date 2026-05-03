# Worker Role Quality & Failure Analysis — 2026-05-03

**Scope.** Static analysis of the worker pipeline in `coder-core/src/coder_core/workers/` and the role/task prompts in `coder-system/system/roles/`. Cross-references runbooks, ADRs, and config defaults.

**Caveat — no live telemetry.** This repo and `coder-core` contain no `.jsonl` task logs or persisted failure history. `2026-04-21T16:02/` is an empty marker, `beads/` is the unrelated BEADS project. Frequencies cited here either come from runbook narrative (e.g. `worker-schema-failure.md`) or are inferred from the schema/prompt surface area. Operators should cross-check against live observability before acting on numbers.

---

## TL;DR

Ranked from highest to lowest expected failure rate, with the dominant failure mode for each:

| Rank | Role | Schema gate | Dominant failure modes |
|---|---|---|---|
| 1 | **Architect** | 3 schemas (`architect`, `architect_ship_draft`, `audit`) | Code-fence wrappers; missing/malformed frontmatter; non-zero-padded IDs; empty Mermaid; aspirational `affects_*` |
| 2 | **PM** | 4 modes (`pm_draft`, `pm_accept`, `pm_ship_draft`, `audit`) | Evidence regex rejection on accept; mode-detection mismatch; weak ACs that pass the schema but fail downstream |
| 3 | **Team Manager** | 1 schema (`team_manager`) | Narrow rejects (whole plan fails on one bad task); `complexity` enum violations; missing `depends_on` semantic checks |
| 4 | **Developer** | **None** | PR URL not in final message → `stage=stuck`; 40-min timeout on long tool loops; CI fix loop exhausts `MAX_FIX_ATTEMPTS=3` |
| 5 | **Reviewer** | `reviewer_ship` (ship mode only) | Verdict regex misclassification on normal reviews; ship-mode AC-mapping shape gaps |

The two roles with the **largest gap between schema enforcement and prompt-stated quality bar** are **Developer** (no schema at all) and **Architect** (schemas accept many low-quality but well-formed outputs). PM has the **most fragile mode-detection** because four modes funnel through prefix/header heuristics in `pm.py:72-92`.

---

## 1. Pipeline shape and where validation lives

```
PM draft  →  Architect design  →  Team Manager decompose  →  Developer implement
                                                                    ↓
                                            ←  Reviewer review  ←  Developer (loops)
                                            ↓
                                     PM accept  (wip → active)
```

**Compliance gate** ([_compliance_gate.py:118-208](coder-core/src/coder_core/workers/_compliance_gate.py)):
- Gated roles: `pm`, `architect`, `team-manager` only ([dispatcher.py:2696](coder-core/src/coder_core/workers/dispatcher.py:2696)).
- Re-prompt budget: `worker_output_compliance_budget=2` (default).
- Re-prompt mechanism: spawns a fresh `claude` subprocess with the validator errors and the previous raw output, max 8 turns, 300s timeout ([_reprompt.py:90-177](coder-core/src/coder_core/workers/_reprompt.py)).
- On exhaustion: task → `FAILED`, `failure_kind="schema"`, blob with `error_kind`, errors, last raw (4 KB cap), attempts, schema version ([dispatcher.py:2738-2746](coder-core/src/coder_core/workers/dispatcher.py:2738)).
- Recovery flow: [worker-schema-failure.md:83-143](system/runbooks/worker-schema-failure.md).

**Transient retry** ([ADR 0013](system/adrs/0013-worker-level-transient-retry.md)):
- Budget 3, exponential backoff base 2000 ms cap 30 000 ms, classified errors (`overloaded`, `rate_limited`, `timeout`, `connection_reset`, `dns`).
- Lives inside the worker, not the dispatcher.

**Re-prompt-only remediation** ([ADR 0012](system/adrs/0012-re-prompt-only-worker-output-remediation.md)):
- No programmatic repair (no auto-fence-stripping etc.) except the single 2026-04-28 narrow exception: bare `\`\`\`json … \`\`\`` with nothing else outside the fence.
- Adopted because programmatic patches mask root causes and hide which prompts drift.

**Roles that are not gated at all:**
- **Developer** — output is parsed by regex for `PR: <url>` ([developer.py:64-74](coder-core/src/coder_core/workers/developer.py:64)); no JSON schema, no re-prompt on format failure.
- **Reviewer (normal mode)** — verdict and review URL extracted by regex ([reviewer.py:83-135](coder-core/src/coder_core/workers/reviewer.py:83)); schema only applies when prompt starts with `# Ship review`.

---

## 2. Per-role analysis

### 2.1 Developer  ⚠️ no schema gate

**Where it runs.** [developer.py:235-366](coder-core/src/coder_core/workers/developer.py:235). Timeout `coder_developer_task_timeout_seconds=2400` (40 min). `_MAX_TURNS=50` ([developer.py:47](coder-core/src/coder_core/workers/developer.py:47)). Internal CI fix loop bounded by `MAX_FIX_ATTEMPTS=3`.

**What the prompt asks for** ([roles/developer/tasks/implement.md](system/roles/developer/tasks/implement.md)):
- Final message must contain `PR: https://github.com/{org}/{repo}/pull/{number}` on its own line, OR `NO_PR: <reason>`.
- Tests must pass before pushing; new code paths must be tested.
- Branch named `task/<short-slug>` (kebab-case, NOT raw UUID).
- No `git add .`/`-A`; no secrets/binaries; PR title under 70 chars.

**What the schema enforces.** Nothing. The output contract is a **regex on the assistant's last message**.

**Failure modes (highest signal first):**

1. **Missing PR URL → `stage=stuck`.** Test fixture `test_dispatch_developer_no_pr_url` documents this. Worker reports SUCCESS, orchestrator can't extract URL, task transitions to `stuck` and waits for the post-2026-04-28 reconciliation pass. Pre-2026-04-28 this required manual intervention via [dispatching-developer-tasks.md:189-226](system/runbooks/dispatching-developer-tasks.md).
2. **Timeout on long tool-use trajectories.** 40-min ceiling; runbook calls out "very long tool-use trajectory" as the recurring cause. No partial-progress preservation.
3. **`_MAX_TURNS=50` exhausted** ([developer.py:47](coder-core/src/coder_core/workers/developer.py:47)) → `error_max_turns`. No retry; task FAILED.
4. **CI fix loop exhausts.** Up to 3 internal pytest-and-rerun cycles before escalation.
5. **Branch convention drift.** Prompt says `task/<short-slug>`; no enforcement, only post-hoc inspection at [developer.py:651-686](coder-core/src/coder_core/workers/developer.py:651).
6. **Self-approval edge case.** GitHub forbids `APPROVED` state from the same identity that pushed the branch; if the developer service account also reviews, it silently downgrades to `COMMENTED` ([dispatching-developer-tasks.md:300-313](system/runbooks/dispatching-developer-tasks.md)).

**Quality-vs-enforcement gap (biggest of any role).** The prompt's quality bar — *"tests must cover the change", "follow project conventions from AGENTS.md"* — is purely emergent. Anything from a 2-line trivial PR to an 800-line refactor that breaks unrelated callers will pass the regex.

**Recommendations:**

- **R-D1 (highest impact).** Add a lightweight **post-PR contract** the developer must echo to stdout, e.g. a bare JSON block: `{"pr_url": "...", "files_changed": N, "tests_added": N, "summary": "..."}`. Validate with a `developer.json` schema. This converts the silent `stuck` failure into a re-prompt-able schema failure. Cost: ~80 lines in `developer.py`, one schema file. Mirrors what TM/PM/Architect already do.
- **R-D2.** Tighten the prompt's "task is not complete until PR is opened" — currently buried in `implement.md`. Lift into an explicit *exit checklist* the model must walk before printing `PR:`.
- **R-D3.** Add an explicit branch-naming rule to `implement.md` with a regex example. Currently the rule is in the role doc but not the task doc.
- **R-D4.** Document the self-approval downgrade behaviour in `implement.md` — developers shouldn't try to auto-approve their own PRs.

---

### 2.2 Team Manager

**Where it runs.** [team_manager.py:92-150](coder-core/src/coder_core/workers/team_manager.py:92). Schema gate on `team_manager` ([compliance_gate.py:80-81](coder-core/src/coder_core/workers/_compliance_gate.py:80)). Legacy parse fallback at [team_manager.py:57-89](coder-core/src/coder_core/workers/team_manager.py:57) (bare array or `{spec_id, tasks}` envelope).

**Schema** ([schemas/team_manager.json](coder-core/src/coder_core/workers/schemas/team_manager.json)):
- Required: `spec_id` (4-digit string), `tasks` (`minItems: 1`).
- Per task: `id` (int ≥1), `role` (pattern `^[a-z][a-z0-9-]{1,30}$`), `prompt` (10-100 000 chars), `complexity` (enum `S|M|L`), `depends_on` (int array, unique), optional `repo` (slug pattern).
- `additionalProperties: false` everywhere.

**What the prompt asks for** ([decompose.md](system/roles/team-manager/tasks/decompose.md)):
- 3-8 tasks per spec, each sized for a 1-2 hour developer session.
- Each task independently testable.
- Dependencies respected and ordered.
- Each task targets exactly one repo (per `repos.yaml`).
- Each task prompt is "detailed and contextual" so Developer doesn't re-read the spec.

**Failure modes:**

1. **`complexity` enum violation.** Prompt explicitly warns against `small|medium|large|low|high`; schema rejects them. Re-prompt usually fixes it but consumes budget.
2. **JSON fence/preface.** Same root cause as the 2026-04-28 fence-wrapper wave that drove the [ADR 0012](system/adrs/0012-re-prompt-only-worker-output-remediation.md) amendment.
3. **Whole-plan rejection on one bad task.** Schema validates the whole array; one bad `complexity` or one missing `prompt` field aborts the whole decomposition. No partial repair.
4. **Empty plan / single-task plan.** Schema permits 1 task; prompt asks for 3-8. Schema is too lax here.
5. **`depends_on` references nonexistent task IDs.** Schema only checks types, not referential integrity. Cycles also not rejected.
6. **Aspirational repo names.** Prompt says "exactly one repo (per repos.yaml)"; schema only checks slug pattern, not membership.

**Quality-vs-enforcement gap:**

- **Task-prompt depth.** `prompt` field has `minLength: 10`. A useful task prompt for a 1-2 hour developer session is rarely under 200-300 chars. Schema is two orders of magnitude too lax.
- **Dependency DAG.** Schema does not check (a) referenced IDs exist, (b) DAG is acyclic, (c) topological order is respected.
- **Repo membership.** No `enum` against the live repo registry.
- **Plan size band.** No `minItems: 3, maxItems: 8`.

**Recommendations:**

- **R-TM1.** Tighten schema: `prompt.minLength: 200` (or higher), `tasks.minItems: 2`, `tasks.maxItems: 12`. Cheap and high-signal.
- **R-TM2.** Add a dispatcher-side post-schema check for (a) `depends_on` references resolve, (b) DAG is acyclic. Surface as a synthetic schema failure so the re-prompt loop can recover. Don't bake in JSON Schema (oneOf gymnastics get ugly) — do it in code immediately after `validate()`.
- **R-TM3.** Inject `repos.yaml` slugs into the prompt as the canonical list and add `repo` enum to the schema (compute at gate time, not statically — registry changes).
- **R-TM4.** The role/task prompt already says "3-8 tasks", "1-2 hour each" — but burying it in prose means re-prompts often retain bad sizes. Add an explicit *self-check* section the model must walk before emitting JSON.

---

### 2.3 PM (Product Manager) — 4 modes

**Where it runs.** [pm.py:249-340](coder-core/src/coder_core/workers/pm.py:249). Mode resolved by [pm.py:72-92 `parse_pm_mode`](coder-core/src/coder_core/workers/pm.py:72) — prefix `draft:`/`accept:` or header `# Knowledge ship draft`/`# Knowledge audit`. Defaults differ silently if header is malformed.

**Schemas:**
- `pm_draft`: full spec authoring; required `id`/`title`/`frontmatter`/`body`; `body` minLength 100 with regex `- \[ \]` (must contain at least one AC checkbox).
- `pm_accept`: per-AC verdict array; `evidence.minLength: 30` and a regex requiring mention of `PR #`, `pull/`, test path, metric, screenshot, test env, or the explicit phrase "no observable".
- `pm_ship_draft`: pins `artifact_type = "spec"`.
- `audit`: mode `verified`/`needs_rewrite`/`uncertain` shape (shared with architect audit).

**Failure modes (per mode):**

**draft mode.**
1. Body missing the `- [ ]` checkbox pattern → schema reject.
2. Frontmatter `last_verified_at` not in `YYYY-MM-DD` format.
3. Re-emitting an existing spec ID (despite preinjected "next free spec ID").
4. Numeric `id` instead of zero-padded string.
5. Owner field empty after strip (schema only checks string presence).

**accept mode.**
1. **Evidence regex rejection.** The pattern requires concrete observables; "Done.", "yes", "AC met." all fail. This is the single most common failure I'd expect because PMs default to terse acceptance.
2. **Source-code grep used as evidence.** Prompt says it's last-resort and almost always means `fail`; models drift toward grepping when no PR is found.
3. **`all_pass: true` with mixed verdicts.** Schema doesn't enforce the consistency relation; downstream code does.

**ship mode.**
1. Numeric artifact ID (e.g. `"0023"`) instead of subject-named slug (`knowledge-freshness`).
2. Missing frontmatter fence in `patch`.
3. `artifact_type: "design"` (architect's territory) — schema rejects.

**audit mode.**
1. Defaulting to `verified` without doing the work — schema can't catch this.
2. `gaps[]` items shorter than 20 chars ("outdated").
3. Generic complaints ("could be clearer") that pass the length check but fail PM intent.

**Quality-vs-enforcement gap:**

- **Mode detection is fragile.** Header-based detection ([pm.py:72-92](coder-core/src/coder_core/workers/pm.py:72)) silently drops to a default mode if the header isn't exact. A typo in the dispatcher's prompt assembly produces a wrong-schema validation failure that looks like model error.
- **AC quality on draft.** Schema requires *one* checkbox; prompt asks for 4-7 testable ACs. Massive gap.
- **Audit `verified` default risk.** No machine-checkable signal that the model actually compared spec against running system.
- **`pm_accept.summary`** has `minLength: 1` only; could be a single character.

**Recommendations:**

- **R-PM1 (highest impact).** Make mode detection explicit and authoritative: the dispatcher should pass a `mode` field, not depend on header parsing inside the worker. Today the worker re-derives mode from prompt content ([pm.py:72-92](coder-core/src/coder_core/workers/pm.py:72), [dispatcher.py:170-191](coder-core/src/coder_core/workers/dispatcher.py:170)) — these can disagree silently.
- **R-PM2.** `pm_draft.body` should require `minItems` of AC checkboxes via a post-schema count or via a regex like `(?s)(- \[ \].*?){4,}`. Today one checkbox is enough.
- **R-PM3.** `pm_accept` schema: add `summary.minLength: 30`. Cheap signal; matches the per-evidence bar.
- **R-PM4.** `pm_accept`: add a post-schema invariant `all_pass == all(v.verdict == "pass" for v in verdicts)`. Catch contradictions before they leak.
- **R-PM5.** `audit` schema should require, when `decision == "verified"`, a `summary` that mentions a concrete observable (PR/test/metric) — same regex pattern used in `pm_accept.evidence`. This blocks drive-by `verified` answers.
- **R-PM6.** Consider splitting `pm_draft` minimum acceptance criteria check into a dispatcher-side validator with a clear message ("4-7 checkboxes required, found 1") rather than a regex. Re-prompts repair this faster when the error is human-readable.

---

### 2.4 Reviewer

**Where it runs.** [reviewer.py:138-230](coder-core/src/coder_core/workers/reviewer.py:138). Two paths:

- **Normal review:** ungated. Verdict extracted by regex ([reviewer.py:83-126](coder-core/src/coder_core/workers/reviewer.py:83)) looking for `VERDICT: approve` or `VERDICT: request_changes`.
- **Ship review** (prompt starts with `# Ship review`): gated by `reviewer_ship` schema.

**`reviewer_ship` schema** ([schemas/reviewer_ship.json](coder-core/src/coder_core/workers/schemas/reviewer_ship.json)):
- Required: `verdict` (enum `approve|request_changes`), `review_url`, `ship_attestation`.
- `ship_attestation`: `reviewer` (string), `acs` array (`minItems: 0`).
- AC items: `ac` (text), `merged_into?`, `section?`, `dropped` (default false), `reason` (required when `dropped=true` — but schema doesn't enforce the conditional).

**Failure modes:**

1. **Verdict regex misclassification.** `VERDICT: Approve` (capitalised) or `VERDICT:approve` (no space) silently becomes null. Test fixture `test_dispatch_reviewer_no_verdict_in_output` documents this.
2. **Review URL parsing failures** ([reviewer.py:127-135](coder-core/src/coder_core/workers/reviewer.py:127)) — regex doesn't cover all GitHub URL shapes.
3. **Self-approval downgrade.** GitHub blocks; review state silently becomes `COMMENTED` ([dispatching-developer-tasks.md:300-313](system/runbooks/dispatching-developer-tasks.md)).
4. **Ship-mode AC array empty.** Schema permits `minItems: 0` — a ship review can attest *zero* ACs and pass. This is almost certainly a bug.
5. **`dropped=true` without `reason`.** Schema treats both as optional fields independently; no `if/then` clause.
6. **`merged_into` references nonexistent active artifact.** No registry lookup at validation time.

**Quality-vs-enforcement gap:**

- **No schema for normal reviews** — the most common reviewer code path. All quality is regex + emergent.
- **`acs.minItems: 0`** undermines the entire purpose of ship-attestation.
- **Mutual exclusivity** between `dropped` and `merged_into` is documented in the prompt but not in the schema.

**Recommendations:**

- **R-R1 (highest impact).** Add a `reviewer.json` schema for normal reviews — `{"verdict": "approve|request_changes", "review_url": "...", "summary": "...", "concerns": [{"severity": "...", "path": "...", "line": N, "note": "..."}]}`. Converts silent regex failures into re-promptable schema failures.
- **R-R2.** `reviewer_ship.acs.minItems: 1`. The ship gate has no purpose if it accepts an empty attestation.
- **R-R3.** Add JSON Schema `oneOf` (or post-schema check) to enforce: AC item is either `{merged_into, section?, dropped: false}` or `{dropped: true, reason}`.
- **R-R4.** Tolerate verdict casing/whitespace in the regex ([reviewer.py:83-126](coder-core/src/coder_core/workers/reviewer.py:83)). `re.IGNORECASE`, `\s*` between `:` and verdict — until the schema lands. Cheap one-line fix.
- **R-R5.** Document the self-approval downgrade in `review.md` so the model expects it and doesn't loop trying to fix it.

---

### 2.5 Architect — highest schema failure rate

**Where it runs.** [architect.py:192-261](coder-core/src/coder_core/workers/architect.py:192). Three modes (`design`/`audit`/`ship`) detected by header. Design mode also gets the PM spec INDEX preloaded ([dispatcher.py:621-624](coder-core/src/coder_core/workers/dispatcher.py:621)).

**Schemas:**
- `architect`: `oneOf` of two shapes — nested `{design, adrs}` (canonical) or flat `{id, title, frontmatter, body, adrs}` (legacy). `oneOf` is itself a frequent source of validation confusion. `body.minLength: 200` and pattern requires a Mermaid fence.
- `architect_ship_draft`: pins `artifact_type = "design"`.
- `audit`: shared with PM audit.

**Failure modes (in order of expected frequency, with citations):**

1. **JSON code-fence wrappers.** The 2026-04-28 Wave 1 dispatch had 6 of 8 architect tasks fail; ~75% were fence-wrapper rejections. This drove the [ADR 0012 amendment](system/adrs/0012-re-prompt-only-worker-output-remediation.md) for a single narrow fence-strip exception. Even with that exception, anything beyond bare ` ```json … ``` ` still fails.
2. **`oneOf` ambiguity.** When the model emits something close to one shape but with a stray field, JSON Schema reports both branch failures, often confusingly. The re-prompt may try to satisfy the wrong branch.
3. **Missing/malformed frontmatter fields.** `affects_services` and `affects_repos` required as arrays (can be empty); date pattern strict; `type: "design"` const.
4. **Numeric IDs / wrong padding.** Required to be 4-digit zero-padded strings; models occasionally emit integers or 3-digit values.
5. **No Mermaid fence.** `body` pattern requires ` ```mermaid ` substring; an architect that draws an ASCII diagram fails.
6. **Empty Mermaid block.** Pattern matches the fence; an empty fence still passes. Quality gap.
7. **Non-kebab-case ADR slugs.** ADR IDs follow same `^[0-9]{4}$` pattern; ADR titles need to slug down properly downstream.
8. **`affects_*` empty.** Schema permits empty arrays; prompt explicitly calls this a "design smell". The freshness scorer marks these designs unmaintainable.

**Quality-vs-enforcement gap:**

- **Mermaid syntax not validated** — only the fence is checked.
- **Body length 200 chars** — far below the prompt's "30-80 lines" target.
- **Empty `affects_*` allowed by schema** but explicitly flagged as a smell by the prompt and by the freshness scorer.
- **`adrs` array can be empty** — no check that decisions described in body have corresponding ADRs.
- **Title length ≤200** but no semantic check that title reflects scope.
- **Date relations** — no enforcement that `updated >= created` or `last_verified_at` is recent.
- **`oneOf` shape support** is a maintenance burden. The flat shape is "legacy" but kept; either a clear deprecation or a unifying schema would reduce ambiguity.

**Recommendations:**

- **R-A1 (highest impact).** Drop the `oneOf` legacy shape. Either keep nested `{design, adrs}` only and migrate the legacy callers, or keep flat only. Today the dual shape causes both parser and validator confusion. Mark a deprecation date and write an ADR.
- **R-A2.** Lift `body.minLength` to ~800 (rough proxy for 30 lines). Today's 200 is essentially unenforced.
- **R-A3.** Add a schema-side or post-schema check that `affects_services` and `affects_repos` each have `minItems: 1`. Schema today says optional-empty; prompt says it's a smell — close the gap. For abstract designs that genuinely affect nothing, require an explicit override field (`affects_services_intentionally_empty: true`).
- **R-A4.** Validate Mermaid fence content is non-empty and parses (call `mermaid-cli` or a lightweight parser at gate time, surface as synthetic schema error). High signal.
- **R-A5.** Add a registry-aware enum validator on `affects_services` (cross-check `system/services/registry.yaml`) and `affects_repos` (cross-check `system/repos/repos.yaml`). Catches the "aspirational service name" failure mode mentioned in the role doc.
- **R-A6.** Tighten the JSON-only instruction in `_common.md` with a one-line example showing what passes the fence-strip exception vs. what doesn't. The 2026-04-28 amendment helps after-the-fact, but prevention beats cure.

---

### 2.6 Cross-cutting prompt issues (`_common.md`)

The shared preamble does heavy lifting. Two notes:

- **JSON output discipline is stated three times in different words** but never with a worked example showing what's accepted and what isn't (especially since the 2026-04-28 fence exception). One short positive/negative example pair in `_common.md` would prevent a class of recurring schema failures across PM/Architect/TM.
- **Prompt cache reuse** depends on stable preamble ordering. Any addition to `_common.md` invalidates the cache for every gated worker. Consolidating recommendations from R-PM, R-A, R-TM into a single coordinated `_common.md` revision is cheaper than three rolling edits.

---

## 3. Recommendations summary, prioritised

| ID | Role | Change | Cost | Expected impact |
|---|---|---|---|---|
| **R-D1** | Developer | Add `developer.json` schema and post-PR JSON contract | M | **High** — closes the largest enforcement gap in the system |
| **R-A1** | Architect | Drop `oneOf` legacy shape | M | **High** — removes the biggest source of `oneOf` validator noise |
| **R-PM1** | PM | Make mode an explicit dispatcher input, not a re-derived header | S | **High** — eliminates a class of silent wrong-schema failures |
| **R-A4** | Architect | Validate Mermaid fence is non-empty + parses | S | **High** — catches the most common design-mode quality regression |
| **R-PM2** | PM | Require ≥4 AC checkboxes in `pm_draft.body` | S | High |
| **R-R1** | Reviewer | Add `reviewer.json` for normal reviews | M | High |
| **R-R2** | Reviewer | `reviewer_ship.acs.minItems: 1` | XS | High |
| **R-TM1** | Team Manager | Tighten `prompt.minLength` and add `tasks.minItems`/`maxItems` | XS | Medium |
| **R-TM2** | Team Manager | Post-schema DAG/reference check | S | Medium |
| **R-A3** | Architect | `affects_services`/`affects_repos.minItems: 1` (or explicit override) | XS | Medium |
| **R-A5** | Architect | Registry-enum validation on `affects_*` | M | Medium |
| **R-PM4** | PM | `pm_accept.all_pass` consistency invariant | XS | Medium |
| **R-PM5** | PM | `audit.verified` requires concrete-observable summary | XS | Medium |
| **R-R4** | Reviewer | Tolerate verdict casing/whitespace in regex | XS | Medium |
| **R-D2/3** | Developer | Tighten task prompt's exit checklist + branch rule | XS | Low-medium |

Cost legend: XS (≤30 lines), S (~100 lines), M (multi-file change with tests).

---

## 4. What I could not measure

- **Live failure rate per role.** No persisted task history in either repo. Numbers in §1's TL;DR are rank ordering inferred from schema surface area and runbook narrative, not measured frequencies.
- **Re-prompt success rate.** Compliance gate emits `worker_output_compliance.ok|failed` counters but they aren't materialised here. To convert this analysis into a data-grounded prioritisation, query those counters in the live observability stack and re-rank.
- **Drift over time.** The 2026-04-28 fence-wrapper wave is documented in [ADR 0012](system/adrs/0012-re-prompt-only-worker-output-remediation.md); without a time series I can't say whether it's gotten better or worse since then.

If the goal is to drive these recommendations to a backlog, a one-week spike collecting `worker_output_compliance.failed{role,error_kind}` and `tasks.failure_kind` rates would let us re-rank R-* by actual return on engineering time, not surface-area heuristics.
