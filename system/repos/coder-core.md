---
id: coder-core
name: coder-core
type: repo
status: planned
owner: ro
github: coder-devx/coder-core
default_branch: main
hosts_services: [coder-core]
language: python
ci:
  provider: github-actions
  workflows: [test, lint, build]
cd:
  target: cloud-run
  trigger: push-to-main
decided_by: ["0005", "0006"]
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

## CI / CD

- **CI**: lint, type-check, unit + integration tests on every PR.
- **CD**: push to `main` builds and deploys to Cloud Run.

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
