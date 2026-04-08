---
id: short-kebab-id
name: Human Readable Name
type: service
status: active           # active | wip | deprecated
owner: ro
tier: core               # core | supporting | experimental
repos: [repo-id]
tech: [language, framework]
runtime: cloud-run       # cloud-run | local | container | serverless | …
region: europe-west1
depends_on:
  services: []           # other service ids
  integrations: []       # integration ids (github, gcp, …)
  data_stores: []        # neon-postgres, upstash-redis, …
exposes:
  - protocol: http
    port: 8001
    path: /
implements_designs: []   # design ids
decided_by: []           # adr ids
---

# {Name}

## What it does
One paragraph. The job-to-be-done.

## Responsibilities
- Bullet list of what this service owns.

## API surface
| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Liveness |

## Data model
What persistent state it owns (if any).

## Interactions

```mermaid
flowchart LR
  client --> this[{Name}]
  this --> dep1[Dependency]
```

## Operational notes
- Deployment, scaling, secrets, on-call.

## Open questions / known issues
- …
