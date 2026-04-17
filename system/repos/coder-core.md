---
id: coder-core
name: coder-core
type: repo
status: active
owner: ro
github: coder-devx/coder-core
default_branch: main
hosts_services: [coder-core]
language: python
ci:
  provider: github-actions
  workflows: [ci]
cd:
  target: cloud-run
  trigger: manual
decided_by: ["0005", "0006", "0010"]
last_verified_at: 2026-04-08
---

# coder-core

## What it holds

The Python source for the Coder Core service: project orchestration,
worker dispatch, knowledge API, impersonation token issuance, pipeline
runner. Likely also the initial home of the role-typed workers until
they split into their own repos.

## Layout (proposed)

```
src/coder_core/
  api/                 FastAPI app
    projects.py
    knowledge.py
    workers.py
    impersonate.py
    chat.py
  domain/              project, worker, task, pipeline models
  pipeline/            enrich / execute / fix / test runner
  knowledge/           GitHub-backed knowledge repo client + cache
  workers/             role-typed worker implementations
    architect.py
    pm.py
    tm.py
    developer.py
    reviewer.py
    sysadmin.py
    consultant.py
  integrations/        github, gcp, slack, notion, anthropic clients
  auth/                project ACL, role-scoped tokens
migrations/            alembic
tests/
```

## Current state (as of commit #1 · 2026-04-08)

- Repo exists at [`github.com/coder-devx/coder-core`](https://github.com/coder-devx/coder-core) on GitHub.
- v0.0.1 walking skeleton: FastAPI on Python 3.12, `GET /v1/health` only.
- Uses **uv** for dependency management. `pip` is banned per this repo's `AGENTS.md`.
- Follows ADR 0010: `AGENTS.md` at root, `CLAUDE.md` and `.cursor/rules/coder-core.mdc` as thin pointers.
- Not yet deployed. Commit #2 adds the manual Cloud Run deploy.

## CI / CD

- **CI** (`ci` workflow): `ruff check`, `ruff format --check`, `mypy src` (strict), `pytest`, `docker buildx build`. Runs on every PR and push to `main`. Passed clean on the first push.
- **CD**: not wired yet. Manual `make deploy` runbook lands in commit #2; push-to-main CD lands in commit #5.

## Branching

- `main` is always deployable.
- Feature branches → PR → review → merge → deploy.

## Linked services

- Hosts [`coder-core`](../services/coder-core.md).

## Notes

- Replaces the old `coder-agent`. Built clean from the new design — does
  **not** lift code from `coder-agent` wholesale.
- Worker fleet may eventually move to per-role repos
  (`coder-worker-developer`, etc.) — track that as a future ADR when the
  size warrants it.
