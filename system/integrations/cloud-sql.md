---
id: cloud-sql
name: Cloud SQL
type: integration
status: active
owner: ro
auth: iam-service-account
secret_storage: none
used_by_services: [coder-core]
used_by_roles: [system-admin, developer]
last_verified_at: 2026-04-08
---

# Cloud SQL

## What it is

Google's managed Postgres. `coder-core` stores projects, workers, tasks,
pipeline runs, and audit log rows here.

Like every other piece of Coder infrastructure, the **control-plane**
Cloud SQL instance lives in `vibedevx`; **each managed project** gets
its own Cloud SQL instance in its own GCP project (per [ADR 0009](../adrs/0009-per-managed-project-cloud-account-and-github-org.md))
when it needs one.

| Instance | GCP project | Purpose |
|---|---|---|
| `coder-core-db` | `vibedevx` | Coder's own control-plane DB — projects table, worker/task state, pipeline runs |
| _per project_ | _project's GCP_ | Managed-project app DBs (provisioned on demand) |

## Instance details — `coder-core-db`

| Setting | Value |
|---|---|
| Engine | Postgres 17 |
| Edition | `ENTERPRISE` (not ENTERPRISE_PLUS — shared-core tiers aren't supported there) |
| Tier | `db-g1-small` (1 vCPU, 1.7 GiB) |
| Region | `europe-west1` |
| Storage | 10 GiB SSD, auto-increase |
| Backups | Daily at 02:00 local |
| IAM auth | **On** (`cloudsql.iam_authentication=on`) |
| Databases | `coder_core` |

## Auth model — IAM only, zero passwords in the app

Authentication to the DB is via **Cloud SQL IAM** — no passwords in code
or Secret Manager. Three kinds of principals are defined as DB users:

| Principal | DB user | Use |
|---|---|---|
| `coder-core-sa@vibedevx.iam.gserviceaccount.com` | `coder-core-sa@vibedevx.iam` | Runtime — the Cloud Run service |
| `coder@vibedevx.com` | `coder@vibedevx.com` | Dev — runs migrations from laptop via cloud-sql-proxy |
| built-in `postgres` | `postgres` | Break-glass admin. Password in 1Password; rotated after every use. |

### Required IAM roles on `vibedevx`

| Principal | Role | Why |
|---|---|---|
| `coder-core-sa` | `roles/cloudsql.client` | Permits the Cloud SQL Python Connector to open the tunnel |
| `coder-core-sa` | `roles/cloudsql.instanceUser` | **Required in addition to `client`** — authorizes IAM auth to the DB itself. Missing this is the most common "authentication failed" bug. |
| `coder-core-sa` | `roles/logging.logWriter` | App logs |
| `coder-core-sa` | `roles/monitoring.metricWriter` | Metrics |

### Required DB privileges (granted once, manually)

IAM DB users start with **no** privileges on a database. After creation,
someone with `CREATE`/`GRANT` on the `public` schema has to grant the
service account access. The built-in `postgres` user in Cloud SQL is
**not a true superuser** and can only grant on objects it owns —
meaning the user who runs a migration must also be the one who grants
future-table defaults.

The sequence used for `coder-core-db` on 2026-04-08:

1. `postgres` granted `CONNECT` + `ALL ON SCHEMA public` + default privileges to `coder-core-sa@vibedevx.iam`.
2. `postgres` did the same for `coder@vibedevx.com` so it could run migrations.
3. `coder@vibedevx.com` ran `alembic upgrade head` — tables became owned by `coder@vibedevx.com`.
4. `coder@vibedevx.com` (as the table owner) granted `ALL ON ALL TABLES/SEQUENCES IN SCHEMA public` to `coder-core-sa@vibedevx.iam`, AND set `ALTER DEFAULT PRIVILEGES FOR ROLE coder@vibedevx.com` so future migrations automatically grant to the SA.

The procedural detail is in [`runbooks/cloud-sql-bootstrap.md`](../runbooks/cloud-sql-bootstrap.md).

## Connection patterns

### From Cloud Run (`coder-core`) — Cloud SQL Python Connector

The `coder_core.db` module uses [`google-cloud-sql-connector[asyncpg]`](https://pypi.org/project/cloud-sql-python-connector/).
The Connector opens a mutually-authenticated TLS tunnel to the instance
and logs in with the service account's IAM identity. Env vars:

```
CLOUD_SQL_INSTANCE=vibedevx:europe-west1:coder-core-db
CLOUD_SQL_USER=coder-core-sa@vibedevx.iam
CLOUD_SQL_DATABASE=coder_core
```

Pitfall: the Connector binds to an event loop. When constructed
without an explicit `loop=...`, it spins up its own internal loop in a
background thread, and `connect_async()` then refuses because the
caller is in a different loop. Fix (already in `coder_core.db`):
lazy-init the Connector inside the async creator callback and pass
`loop=asyncio.get_running_loop()`.

### From a developer's laptop — `cloud-sql-proxy`

Migrations and ad-hoc admin connect via [`cloud-sql-proxy`](https://github.com/GoogleCloudPlatform/cloud-sql-proxy)
v2, which forwards `localhost:5434` into the instance:

```sh
# One-shot authentication if gcloud isn't available in ADC form:
cloud-sql-proxy \
  --token "$(gcloud auth print-access-token)" \
  --port=5434 \
  vibedevx:europe-west1:coder-core-db

# Then in another shell:
TOKEN=$(gcloud auth print-access-token)
DATABASE_URL="postgresql+asyncpg://coder%40vibedevx.com:${TOKEN}@127.0.0.1:5434/coder_core" \
  uv run alembic upgrade head
```

See [`runbooks/run-migration-coder-core.md`](../runbooks/run-migration-coder-core.md).

## Limits

- Maintenance windows can briefly interrupt connections. Retry logic is
  the app's responsibility (commit #4+).
- `db-g1-small` is shared-core; expect latency spikes under contention.
  Upgrade to `db-custom-N-M` when sustained load demands it.

## Notes

- **No public IP on the DB is exposed to the internet in a raw sense** —
  the Python Connector and cloud-sql-proxy both use GCP-authenticated
  tunnels over the public endpoint. No authorized-networks needed.
- The `postgres` user's password is used once for bootstrap, then kept
  in 1Password. It's the break-glass root for when IAM auth is
  misconfigured and nobody can get in.
