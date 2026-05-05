---
id: example-service
name: Example Service
type: service
status: active
owner: fixture
tier: supporting
repos: [example-service]
tech: [python, fastapi]
runtime: cloud-run
region: europe-west1
depends_on:
  services: []
  integrations: []
  data_stores: []
exposes:
  - protocol: http
    port: 8080
    path: /health
implements_designs: []
decided_by: []
---

# Example Service

Synthetic fixture service artifact for local `coder migrate test` runs.
Represents a minimal but structurally valid service entry so that additive
migrations (e.g., adding a `criticality` field to all services) produce
real `FileChange` output against this fixture.

## What it does
Placeholder service — exists only inside `migrations/_fixtures/typical/`.
