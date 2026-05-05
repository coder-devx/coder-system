---
id: example-service
name: Example Service
type: service
status: active
owner: ro
tier: core
repos: [example-service]
tech: [python, fastapi]
runtime: cloud-run
region: europe-west1
depends_on:
  services: []
  integrations: [github, gcp]
  data_stores: [neon-postgres]
exposes:
  - protocol: http
    port: 8080
    path: /
implements_designs: []
decided_by: []
---

# Example Service

## What it does
A synthetic service artifact used by migration fixtures to exercise additive
and rename migrations against a realistic service frontmatter schema.

## Responsibilities
- Demonstrates a realistic service artifact shape for fixture-based testing.

## API surface
| Method | Path    | Purpose  |
|--------|---------|----------|
| GET    | /health | Liveness |

## Data model
No persistent state.

## Interactions

```mermaid
flowchart LR
  client --> svc[Example Service]
```

## Operational notes
- Fixture only — not a real deployed service.
