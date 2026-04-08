---
id: run-migration-coder-core
title: Run an alembic migration against the prod coder-core DB
type: runbook
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-08
applies_to_services: [coder-core]
applies_to_integrations: [cloud-sql]
---

# Run an alembic migration against the prod `coder-core` DB

## When to run this

You have a new migration in `coder-core/migrations/versions/` that's
already merged (or at least tested locally) and you need to apply it to
the production `coder-core-db` Cloud SQL instance.

Migrations in `coder-core` happen out-of-band from deploys. The app
does NOT auto-run migrations on startup — that's deliberate, so a bad
migration can't take down the service.

## Who can run this

- `coder@vibedevx.com` (the dev IAM user on Cloud SQL) — today, that's `ro`.
- Needs `roles/cloudsql.client` on `vibedevx`.
- Needs the `coder@vibedevx.com` Cloud SQL IAM user to exist and have `GRANT ALL ON SCHEMA public` on the `coder_core` database (already set up during bootstrap — see [`cloud-sql-bootstrap.md`](./cloud-sql-bootstrap.md)).

## Prerequisites

- Local clone of `coder-core` on the branch you want to ship.
- `make check` passes locally (lint, format, typecheck, test).
- The new migration exists under `migrations/versions/` and has a sensible `down_revision`.
- `uv sync` has been run recently.
- `cloud-sql-proxy` v2 installed (`brew install cloud-sql-proxy`).
- `gcloud` authed as `coder@vibedevx.com`.

## Steps

```sh
# 1. Start the proxy (background, port 5434)
TOKEN=$(gcloud auth print-access-token)
cloud-sql-proxy \
  --token "$TOKEN" \
  --port=5434 \
  vibedevx:europe-west1:coder-core-db &
PROXY_PID=$!
sleep 3

# 2. Preview what will run
DATABASE_URL="postgresql+asyncpg://coder%40vibedevx.com:${TOKEN}@127.0.0.1:5434/coder_core" \
  uv run alembic current
DATABASE_URL="postgresql+asyncpg://coder%40vibedevx.com:${TOKEN}@127.0.0.1:5434/coder_core" \
  uv run alembic history | tail -10

# 3. Apply
TOKEN=$(gcloud auth print-access-token)   # re-fetch, tokens expire in ~1h
DATABASE_URL="postgresql+asyncpg://coder%40vibedevx.com:${TOKEN}@127.0.0.1:5434/coder_core" \
  uv run alembic upgrade head

# 4. Verify
DATABASE_URL="postgresql+asyncpg://coder%40vibedevx.com:${TOKEN}@127.0.0.1:5434/coder_core" \
  uv run alembic current

# 5. Shut down the proxy
kill $PROXY_PID
```

## Success condition

`alembic current` shows the head revision you expected. Hit
`https://coder-core-…run.app/v1/health` and then any affected endpoint
and confirm it still works.

## After adding a new table

The SA grants are set up via default privileges — **tables created by
`coder@vibedevx.com` in the `public` schema auto-grant ALL to the SA.**
This should Just Work.

If you later add a migration that creates objects in a different schema,
you'll need to re-grant explicitly. See
[`cloud-sql-bootstrap.md`](./cloud-sql-bootstrap.md) step 9.

## Rolling back

Alembic supports `downgrade`:

```sh
DATABASE_URL="postgresql+asyncpg://coder%40vibedevx.com:${TOKEN}@127.0.0.1:5434/coder_core" \
  uv run alembic downgrade -1
```

But downgrade SQL is only as good as the `down_revision` function in the
migration file. Review it before running, and prefer "fix forward" — a
new migration that un-does the bad one — over downgrades in production.

## Notes

- **Token expiry** — IAM auth over asyncpg uses the OAuth access token as the password. Tokens expire in ~1h. If the migration is slow, re-fetch a token between `preview` and `apply`.
- **Proxy does not persist** — start it fresh for each migration session; don't leave it running.
- **Don't run migrations from CI** until commit #5's push-to-main CD is actually in. Currently migrations are an explicit human action.
