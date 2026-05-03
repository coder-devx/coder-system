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
  trigger: push-to-main
decided_by: ["0005", "0006", "0010"]
last_verified_at: 2026-04-26
---

# coder-core

## What it holds

The Python source for the Coder Core service: project orchestration,
worker dispatch, knowledge API, impersonation token issuance, pipeline
runner. Likely also the initial home of the role-typed workers until
they split into their own repos.

## Layout

Modular monolith per the coder-core-modular-monolith design. Routers in `api/` and `mcp/` are
thin adapters; workflow code lives in feature-package service
modules. The dependency graph is enforced in CI via `import-linter`
(see `docs/module-boundaries.md` in the repo).

```
src/coder_core/
  main.py            FastAPI app factory
  config.py          pydantic-settings
  errors.py          ServiceError base for domain errors
  access.py          load_in_project — canonical row-scope check
  contracts.py       WorkerDispatcher / KnowledgeRepository / … protocols
  admin_jwt.py       Admin JWT mint + decode
  budget.py          Project token budget policy
  api/               HTTP transport — adapters only, no workflow logic
  mcp/               MCP JSON-RPC transport — adapters only
  tasks/             Task lifecycle workflows (services)
  pipelines/         Pipeline run workflows (services)
  metrics/           Aggregation workflow (service)
  impersonation/     Broker token mint workflow (service)
  projects/          Project admin workflows (services)
  knowledge/         Read service, write_service, ship workflow
  workers/           In-process role workers + dispatcher seam
  approvals/  escalations/  ops/  rotation/  self_heal/  oauth/
  integrations/      External adapters: GitHub, GCP, Slack, Anthropic
  domain/            SQLAlchemy models — pure data layer
docs/                module-boundaries.md, architectural docs
migrations/          alembic
tests/               route-level + service-level coverage
```

## Current state (as of 2026-04-26)

- v0.0.3 in production via Cloud Run, push-to-main CD.
- 1369 tests passing. Four `import-linter` boundary contracts hold
  with zero `ignore_imports` exceptions.
- Uses **uv** for dependency management. `pip` is banned per
  `AGENTS.md`.
- Follows ADR 0010: `AGENTS.md` at root, `CLAUDE.md` and
  `.cursor/rules/coder-core.mdc` as thin pointers.

## CI / CD

- **CI** (`ci` workflow): `ruff check`, `ruff format --check`,
  `mypy src` (strict), `lint-imports` (4 contracts), `pytest`,
  `docker buildx build`, plus capability-matrix and isolation-manifest
  drift checks. Runs on every PR and push to `main`.
- **CD**: push-to-main → WIF auth → AR push → canary deploy at 0%
  traffic → `/v1/health` health check → Alembic migrations via Cloud
  Run job → recurring-jobs image sync → 100% traffic shift → Slack
  notify. See [`deploy-coder-core.md`](../runbooks/deploy-coder-core.md).

## Branching

- `main` is always deployable; pushes auto-deploy.
- Feature branches → PR → CI green → review → squash-merge → deploy.

## Linked services

- Hosts [`coder-core`](../services/coder-core.md).

## Notes

- Replaces the old `coder-agent`. Built clean from the new design.
- Worker fleet stays in-process for now. The `WorkerDispatcher`
  protocol from the coder-core-modular-monolith design is the seam an extraction would bind to;
  the bar for extracting is recorded in the design's *Extraction
  decision* section.
