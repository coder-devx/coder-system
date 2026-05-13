---
id: 0038
title: Deny-list strip over allow-list for worker subprocess DB credentials
type: adr
status: proposed
date: '2026-05-13'
deciders:
- ro
supersedes: null
superseded_by: null
relates_to_designs:
- 0088
---

# ADR 0038 — Deny-list strip over allow-list for worker subprocess DB credentials

## Context

Design 0088 must prevent prod DB credentials from reaching worker subprocesses.
Two credible strategies exist for how to clean the env before spawning:

1. **Deny-list** — copy `os.environ`, then pop a fixed set of known-dangerous
   keys (`CLOUD_SQL_INSTANCE`, `CLOUD_SQL_USER`, `CLOUD_SQL_DATABASE`,
   `DATABASE_URL`, `PGHOST`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`).
2. **Allow-list** — start from an empty dict, then explicitly add only the env
   vars the subprocess is known to need (`PATH`, `HOME`, `GH_TOKEN`,
   `ANTHROPIC_API_KEY` / `CLAUDE_CODE_OAUTH_TOKEN`, `CODER_*` config vars, etc.).
3. **No-env** — inherit nothing; rely entirely on the Claude CLI's own
   credential resolution from disk (`~/.claude`). Rejected immediately: the
   worker needs `GH_TOKEN`, `HOME`, `PATH` at minimum.

## Options considered

**Option 1 — Deny-list**
- Low disruption: the existing env construction logic (auth env, GitHub token,
  HOME) is unchanged; the strip is one additive step.
- Risk: a new credential that leaks via an env var not in the deny-list
  (e.g. `PGSERVICEFILE`, a future `CLOUD_SQL_PROXY_*` var) would not be caught.
  Requires maintaining the deny-list as new creds are added.
- Recovery: AC4 regression test catches re-introduced prod DB access; the audit
  event shows which keys were stripped on every turn.

**Option 2 — Allow-list**
- Safer by construction: any credential not explicitly listed is excluded.
- Invasive: requires enumerating every env var the subprocess relies on today
  and in the future. The Claude CLI's own credential resolution, Alembic's
  config discovery, uv's cache paths, and OS locale vars all read from the
  environment. A missed var causes silent worker failure (not a security issue,
  but an operational one). Enumeration is non-trivial and brittle across CLI
  version upgrades.

## Decision

Deny-list (Option 1) for v1.

## Rationale

The deny-list closes the immediate incident vector (the four known Cloud SQL
vars) with minimal disruption and no risk of silent worker breakage. The
allow-list's safety margin is real but the enumeration burden is high: the
Claude CLI alone reads ~15 env vars for its own operation, and the set is not
published. A missed var breaks the worker, not prod — but worker breakage at
this volume is operationally costly.

The deny-list is self-documenting: every key on the list has a comment
explaining why it's there. AC4's regression replay provides an ongoing
safety net. If a new credential surface leaks through a deny-list gap,
the right response is to add it to the list and add a regression test — not
to switch strategies.

Revisit allow-list if the deny-list misses a second incident.

## Consequences

- Maintainers adding new DB-adjacent credentials to the Cloud Run Job spec must
  also add the corresponding env key to the deny-list in `_db_env.py`. The
  module's docstring calls this out explicitly.
- AC4 regression test provides a persistent canary: any prod DB write from a
  worker subprocess turns it red.
- The `worker.prod_creds_stripped` audit event surfaces which keys were present
  at strip time — useful for detecting env drift (e.g. a new `PGPASSWORD`
  that shouldn't be in the Job spec but is).
