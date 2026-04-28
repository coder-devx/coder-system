---
id: "0018"
title: Skip divergent managed-workflow files by default; require --force to overwrite
type: adr
status: proposed
date: 2026-04-28
deciders: [ro]
supersedes: null
superseded_by: null
relates_to_designs: ["0052"]
---

# ADR 0018 — Skip divergent managed-workflow files by default; require --force to overwrite

## Context

`install_workflow` (spec 0052 Stage 1) sweeps every managed knowledge repo and
ensures each carries the workflow files declared in the fleet manifest. When it
encounters a workflow file that already exists but whose content differs from the
template in coder-system (a *divergent* file), it must choose a default action.

Managed knowledge repos are owned by the project team, not the fleet operator.
Project maintainers may hand-tune `.github/workflows/` files for local reasons:
different `on:` triggers, additional steps, modified secret names, project-specific
environment variables. An automatic overwrite would destroy those edits without
operator awareness.

At the same time, divergence is a signal worth surfacing. It may mean:
- The template was updated in coder-system but the fleet sweep has not re-run yet
  (expected; fix by re-running `coder managed-workflows install`).
- A project made an intentional local edit that should be preserved or reviewed.

Two approaches were evaluated:

1. **Overwrite by default.** Every `coder managed-workflows install` run converges
   to the fleet template, treating managed repos as fully fleet-managed. Local edits
   are treated as drift to be corrected, not preserved.
2. **Skip by default; overwrite with `--force`.** Divergent files are flagged with a
   warning and left unchanged unless the operator passes `--force`. The operator
   explicitly acknowledges the destructive action.

## Options considered

**Option A — Overwrite by default**

- Simple: the fleet template is always authoritative.
- Risk: destroys project-specific edits without warning. A workflow may have its
  `on:` trigger adjusted for project needs, or carry an extra `env:` block that is
  required for project CI. An automatic overwrite silently breaks the project.
- Coherent only if managed repos are truly lock-stepped with the fleet — enforced
  by CODEOWNERS or branch protection. No such enforcement exists today, and adding
  it is out of scope for spec 0052.

**Option B — Skip by default; overwrite with `--force` (this ADR)**

- Divergent files surface as `SkippedDivergent` warnings in the sweep output and
  as `⚠ drift` cells in the admin matrix (Stage 2).
- Destructive overwrite requires `--force`; `coder managed-workflows diff` shows the
  delta before the operator commits.
- Risk: a workflow stays divergent until an operator runs `--force`, so a template
  security fix does not auto-propagate to repos with local edits. Mitigated by the
  admin matrix flagging drift continuously and exit code 2 providing CI-level signal.

## Decision

Adopt **Option B**: skip divergent files by default. `install_workflow` returns
`SkippedDivergent` (and logs a `WARNING`) when the installed file differs from the
template. Passing `--force` on the CLI causes `install_workflow` to open an overwrite
PR instead, returning `Created`.

## Rationale

**Managed repos are not fully fleet-managed today.** Knowledge repos contain
project-specific content owned by the project team. There is no mechanism preventing
local workflow edits, and requiring one is out of scope for spec 0052. Treating
fleet-owned files as inviolable without enforcement is a contract we cannot keep.

**Destructive actions should be operator-explicit.** The system has precedent: the
branch-cleanup GC skips branches with open PRs rather than deleting them silently;
the self-healing watchdog runs in `dry_run` before `apply`. Overwriting a live
workflow file is at least as consequential as either.

**`diff` before `--force`.** `coder managed-workflows diff` lets operators inspect
the delta before applying. This mirrors the `kubectl diff` / `terraform plan` pattern.

**ADR is reversible.** If the fleet evolves to the point where local workflow edits
are prohibited by policy and the admin matrix consistently shows drift only from
template updates (never local edits), Option A becomes the better default. The
implementation path is narrow: flip `force=True` as the default inside
`install_workflow` and update the CLI default. No schema or API changes required.

## Consequences

- **Positive.** Project-specific workflow edits survive `coder managed-workflows install`
  unless the operator explicitly overrides.
- **Positive.** Clear, auditable operator action (`--force` + an overwrite PR in the
  managed repo) for each destructive change.
- **Positive.** Exit code 2 on divergence gives CI/CD pipelines a drift signal without
  requiring any mutation.
- **Negative.** A template security update does not auto-propagate to repos with local
  edits. Operator must run `coder managed-workflows install --force [--workflow <id>]`
  after reviewing the diff.
- **Negative.** The admin matrix (Stage 2) will show `⚠ drift` cells that may be
  intentional local edits. The `diff` subcommand is the tool for disambiguation; a
  future annotation layer could distinguish "drifted from stale template" vs "drifted
  from local edit".
- **Follow-up.** After the first concrete workflow (0045 `flip-cold-start-provenance`)
  ships and the fleet sweep runs: monitor whether any repos produce `SkippedDivergent`.
  If none do (all repos show `UpdatedExisting` from the initial install), the risk of
  the default being too conservative was low and the status quo holds. If many do, and
  they are all template-lag rather than local edits, reconsider the default in a
  subsequent ADR.
