---
id: update-agent-context
title: Update Coder Agent context without redeploy
type: runbook
status: active
owner: ro
created: 2026-04-08
updated: 2026-04-08
applies_to_services: [coder-agent]
applies_to_integrations: [gcp]
---

# Update Coder Agent context without redeploy

## When to run this
You changed `coder-agent/AGENT_CONTEXT.md` and want the live agent to pick
up the new context without rebuilding the container.

## Who can run this
Architect or System Admin.

## Prerequisites
- `gcloud` authenticated as `coder@vibedevx.com`
- Push access to GCP Secret Manager in the `vibedevx` project

## Steps

1. Edit `coder-agent/AGENT_CONTEXT.md`.
2. Push it as a new secret version:
   ```bash
   cat coder-agent/AGENT_CONTEXT.md | gcloud secrets versions add AGENT_CONTEXT \
     --data-file=- --project=vibedevx --account=coder@vibedevx.com
   ```
3. The Coder Agent reloads `AGENT_CONTEXT` on its next request — no restart needed.

## Success condition
The next agent reply reflects the new context.

## If something goes wrong
- "Permission denied" → confirm you're using `coder@vibedevx.com`.
- New context not visible → confirm a new version was created with
  `gcloud secrets versions list AGENT_CONTEXT --project=vibedevx`.
