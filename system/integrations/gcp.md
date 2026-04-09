---
id: gcp
name: Google Cloud Platform
type: integration
status: active
owner: ro
auth: service-account
secret_storage: workload-identity
used_by_services: [coder-core, coder-admin]
used_by_roles: [system-admin, sre, release-manager]
---

# Google Cloud Platform

## What it is

Cloud provider for both Coder itself **and** every project Coder manages.

The topology is **two layers**:

| Layer | GCP project | Owns |
|---|---|---|
| **Coder itself** | [`vibedevx`](https://console.cloud.google.com/welcome/new?project=vibedevx) | Coder Core, Admin Panel, Coder's own Artifact Registry, Secret Manager, IAM. The control plane. |
| **Each managed project** | its own GCP project (e.g. `vibetrade-space` for VibeTrade) | The managed product's own services, databases, secrets. The data plane for that project. |

A **new project onboarded to Coder gets a brand new GCP project**. There
is no shared GCP project between two managed projects. Billing, IAM
blast radius, and audit logs are isolated at the GCP-project boundary.
See [ADR 0009](../adrs/0009-per-managed-project-cloud-account-and-github-org.md).

## Auth model

### For Coder's own resources (`vibedevx`)

- Each role-worker has its own service account in `vibedevx` —
  `coder-{role}@vibedevx.iam.gserviceaccount.com`. See [ADR 0006](../adrs/0006-per-role-service-accounts.md).
- Locally: `gcloud auth` as `coder@vibedevx.com`.
- In Cloud Run: workload identity (no key file).

### For managed projects

- The **Coder System Admin worker** holds identities that can reach into
  every managed project's GCP project. Default mechanism: cross-project
  IAM bindings — `coder-system-admin@vibedevx.iam` is granted scoped roles
  in each managed project's GCP project at onboarding time.
- Other Coder role-workers (Developer, SRE, …) do **not** get direct
  cross-project access. They request scoped, time-bounded credentials from
  the System Admin worker for the specific managed project they're acting on.
- Alternative (more isolated, future): per-managed-project SA in the
  managed project's own GCP, with workload-identity federation back to Coder.

## Surface used

- **Cloud Run**: list, status, logs, deploy.
- **Secret Manager**: read/write under per-project prefixes.
- **Artifact Registry**: push container images (per-project AR for managed projects).
- **IAM**: System Admin only — grant scoped permissions, rotate.
- **Logging / Monitoring**: SRE — read.

## Permissions / scopes (Coder's own SAs in `vibedevx`)

- `roles/run.viewer`, `roles/run.developer`, `roles/run.invoker`
- `roles/secretmanager.secretAccessor` (scoped to relevant secrets)
- `roles/logging.viewer`
- System Admin worker additionally: `roles/iam.serviceAccountTokenCreator`,
  `roles/iam.workloadIdentityUser`, and the minimum needed to broker access.

## Limits

- Cloud Run cold starts ~1-3s for the Python container.
- IAM propagation can take up to a minute when granting cross-project bindings.

## Secret Manager naming convention

GCP Secret Manager IDs only allow `[A-Za-z0-9_-]`, so the slash-style
path `coder/{project_id}/{name}` from [ADR 0009](../adrs/0009-per-managed-project-cloud-account-and-github-org.md)
is rendered with hyphens in practice:

```
coder-{managed_project_id}-{secret_name}
```

For Coder operating on itself the project id is literally `coder`, so the
prefix doubles. That's expected, not a bug.

| Secret | Owner | Holds | Notes |
|---|---|---|---|
| `coder-coder-api-key` | project `coder` | The `coder` project's static API key for `coder-core`'s authenticated endpoints. Plaintext is the source of truth here; `coder-core-db.projects.api_key_hash` stores only the SHA-256. | Read with `gcloud secrets versions access latest --secret=coder-coder-api-key --project=vibedevx`. Rotation is manual until `POST /v1/projects/{id}/rotate-api-key` lands. |
| `GITHUB_TOKEN` | (legacy name) | Classic PAT used by the knowledge API to read GitHub. Mounted into `coder-core` via `--set-secrets`. | Pre-dates the new naming convention — kept as-is so the existing Cloud Run config keeps working. **Security follow-up:** rotate to a fine-grained PAT and rename to `coder-coder-github-pat` in the same change. |

Secrets that belong to the **managed product itself** (e.g. VibeTrade's
own DB password, its API keys to third parties) live in **that project's
own GCP Secret Manager**, not in `vibedevx`. Coder never co-mingles its
control-plane secrets with a managed project's data-plane secrets.

The Coder System Admin worker is the only role with write access to
`vibedevx` Secret Manager. Other workers get scoped read access via
`roles/secretmanager.secretAccessor` bound to specific secrets, granted
in the same commit that introduces the need.

## Notes

- Default region for Coder's control plane: `europe-west1` (`vibedevx`).
  Managed projects pick their own region.
- A new managed-project onboarding flow MUST create the GCP project,
  enable required APIs, create the project's Artifact Registry, and grant
  the Coder System Admin worker the agreed scoped roles before any other
  worker tries to act on it.
