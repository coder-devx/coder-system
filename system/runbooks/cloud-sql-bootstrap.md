---
id: cloud-sql-bootstrap
title: Bootstrap Cloud SQL for coder-core
type: runbook
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-08
last_verified_at: 2026-04-08
applies_to_services: [coder-core]
applies_to_integrations: [cloud-sql, gcp]
---

# Bootstrap Cloud SQL for `coder-core`

## When to run this

- First-time setup of the `coder-core-db` Cloud SQL instance.
- After restoring from a backup if IAM bindings were wiped.
- When onboarding a new managed project that needs its own Cloud SQL instance — adapt the instance name and principals.

This was run once, on 2026-04-08, to stand up `coder-core-db` in `vibedevx`.
It is documented here so it can be reproduced per-managed-project.

## Who can run this

Someone with `roles/cloudsql.admin` and `roles/resourcemanager.projectIamAdmin`
on the target GCP project. For `vibedevx` that's the user (`ro`).

## Prerequisites

- `gcloud` authenticated. `gcloud auth list` shows the expected account as active.
- Cloud SQL Admin API enabled on the project:
  ```sh
  gcloud services enable sqladmin.googleapis.com --project=<proj>
  ```
- `cloud-sql-proxy` v2 installed locally (`brew install cloud-sql-proxy`).

## Steps

### 1. Create the instance

```sh
gcloud sql instances create coder-core-db \
  --project=vibedevx \
  --region=europe-west1 \
  --database-version=POSTGRES_17 \
  --edition=ENTERPRISE \
  --tier=db-g1-small \
  --storage-size=10GB \
  --storage-type=SSD \
  --storage-auto-increase \
  --backup-start-time=02:00 \
  --database-flags=cloudsql.iam_authentication=on \
  --quiet
```

Takes ~2-5 minutes. Wait for state `RUNNABLE`:

```sh
gcloud sql instances describe coder-core-db --project=vibedevx --format='value(state)'
```

> **Important**: Use `--edition=ENTERPRISE` explicitly. The default is
> `ENTERPRISE_PLUS`, which does NOT support shared-core tiers like
> `db-g1-small` and returns a cryptic "Invalid Tier" error.

### 2. Create the database

```sh
gcloud sql databases create coder_core --instance=coder-core-db --project=vibedevx
```

### 3. Create IAM DB users

```sh
# The runtime service account
gcloud sql users create coder-core-sa@vibedevx.iam \
  --instance=coder-core-db --project=vibedevx \
  --type=cloud_iam_service_account

# The dev user (who runs migrations from their laptop)
gcloud sql users create coder@vibedevx.com \
  --instance=coder-core-db --project=vibedevx \
  --type=cloud_iam_user
```

> **DB user name format**: for a service account
> `my-sa@my-proj.iam.gserviceaccount.com`, the DB user is
> `my-sa@my-proj.iam` (strip `.gserviceaccount.com`). For a human
> `alice@example.com`, the DB user is the full email.

### 4. Grant the runtime SA its IAM roles

`cloudsql.client` alone is **not** enough. You also need
`cloudsql.instanceUser` — that's the role that authorizes IAM auth to
the DB itself. Missing this is the most common "authentication failed"
bug.

```sh
for ROLE in cloudsql.client cloudsql.instanceUser; do
  gcloud projects add-iam-policy-binding vibedevx \
    --member=serviceAccount:coder-core-sa@vibedevx.iam.gserviceaccount.com \
    --role=roles/$ROLE --condition=None
done
```

### 5. Set the break-glass `postgres` password

The built-in `postgres` user is needed ONCE to grant initial privileges
to the IAM users (IAM users start with no schema access). Generate a
strong password, use it once, and store it in 1Password.

```sh
PG_ADMIN_PWD=$(openssl rand -base64 32 | tr -d '=+/')
gcloud sql users set-password postgres \
  --instance=coder-core-db --project=vibedevx \
  --password="$PG_ADMIN_PWD"
```

Save `$PG_ADMIN_PWD` to 1Password under "coder-core-db postgres bootstrap".

### 6. Start cloud-sql-proxy

```sh
TOKEN=$(gcloud auth print-access-token)
cloud-sql-proxy \
  --token "$TOKEN" \
  --port=5434 \
  vibedevx:europe-west1:coder-core-db &
```

> The `--token` flag bypasses Application Default Credentials, which
> don't exist after a plain `gcloud auth login`. If you want persistent
> auth, run `gcloud auth application-default login` once and drop the
> `--token` flag.

### 7. Grant initial privileges to the IAM users

This is a **one-shot DDL** run as `postgres`. In Python:

```python
import asyncio, asyncpg

PG_PWD = "<paste from step 5>"

GRANTS = [
    # SA — runtime
    'GRANT CONNECT ON DATABASE coder_core TO "coder-core-sa@vibedevx.iam";',
    'GRANT ALL ON SCHEMA public TO "coder-core-sa@vibedevx.iam";',
    # Dev user — migrations
    'GRANT CONNECT ON DATABASE coder_core TO "coder@vibedevx.com";',
    'GRANT ALL ON SCHEMA public TO "coder@vibedevx.com";',
]

async def main():
    conn = await asyncpg.connect(
        host="127.0.0.1", port=5434, user="postgres",
        password=PG_PWD, database="coder_core",
    )
    for sql in GRANTS:
        await conn.execute(sql)
    await conn.close()

asyncio.run(main())
```

### 8. Run the first migration as the dev user

```sh
cd /path/to/coder-core
TOKEN=$(gcloud auth print-access-token)
DATABASE_URL="postgresql+asyncpg://coder%40vibedevx.com:${TOKEN}@127.0.0.1:5434/coder_core" \
  uv run alembic upgrade head
```

For IAM auth over asyncpg, the URL password is the **OAuth2 access token**. It expires in ~1h; re-fetch if migrations are slow.

### 9. Grant the SA privileges on the newly-created tables

Critical: the tables created in step 8 are owned by
`coder@vibedevx.com`, not `postgres`. The built-in `postgres` user in
Cloud SQL is **not a true superuser** and can't `GRANT` on objects
owned by IAM users. You must run this step as the **table owner**
(the dev user). Also set default privileges so future migrations run
by the same user auto-grant to the SA.

```python
import asyncio, asyncpg, os

GRANTS = [
    'GRANT ALL ON ALL TABLES IN SCHEMA public TO "coder-core-sa@vibedevx.iam";',
    'GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO "coder-core-sa@vibedevx.iam";',
    'ALTER DEFAULT PRIVILEGES FOR ROLE "coder@vibedevx.com" IN SCHEMA public '
    'GRANT ALL ON TABLES TO "coder-core-sa@vibedevx.iam";',
    'ALTER DEFAULT PRIVILEGES FOR ROLE "coder@vibedevx.com" IN SCHEMA public '
    'GRANT ALL ON SEQUENCES TO "coder-core-sa@vibedevx.iam";',
]

async def main():
    token = os.environ["GCP_TOKEN"]
    conn = await asyncpg.connect(
        host="127.0.0.1", port=5434, user="coder@vibedevx.com",
        password=token, database="coder_core",
    )
    for sql in GRANTS:
        await conn.execute(sql)
    await conn.close()

asyncio.run(main())
```

Run: `GCP_TOKEN=$(gcloud auth print-access-token) uv run python /tmp/grant_sa.py`

### 10. Clean up and verify

```sh
# Kill the proxy
pkill cloud-sql-proxy

# Verify the deployed service can read and write
curl https://coder-core-<id>.europe-west1.run.app/v1/projects
```

## Success condition

- `coder-core-db` is `RUNNABLE`.
- `gcloud sql users list --instance=coder-core-db` shows `postgres`, `coder-core-sa@vibedevx.iam`, and `coder@vibedevx.com`.
- `coder-core` running on Cloud Run can successfully `SELECT` and `INSERT` via its runtime SA.

## Common mistakes

- **Forgetting `cloudsql.instanceUser`** — symptom: `InvalidAuthorizationSpecificationError: Cloud SQL IAM service account authentication failed`. Add the role and wait ~30s for IAM propagation.
- **Not using `--edition=ENTERPRISE`** — symptom: `Invalid Tier (db-g1-small) for (ENTERPRISE_PLUS) Edition`.
- **Running step 9 as `postgres`** — symptom: `permission denied for table alembic_version`. Cloud SQL's `postgres` is not a true superuser.
- **IAM user password = OAuth token that expires** — symptom: migrations work the first time, fail 1h later. Re-fetch the token.
- **App-side: Connector event loop mismatch** — symptom: `ConnectorLoopError: Running event loop does not match connector._loop`. Pass `loop=asyncio.get_running_loop()` when constructing the Connector, from inside an async context. Already handled in `coder_core/db.py`.

## Notes

- When onboarding a new managed project, this runbook is the template. Replace `coder-core-db` with `{project}-db`, `vibedevx` with the project's GCP project, and the principals with the project's service accounts.
- The break-glass `postgres` password should be rotated after every use and stored only in 1Password.
