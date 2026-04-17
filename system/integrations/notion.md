---
id: notion
name: Notion
type: integration
status: active
owner: ro
auth: integration-token
secret_storage: gcp-secret-manager
used_by_services: [coder-agent]
used_by_roles: [product-manager, software-architect]
last_verified_at: 2026-04-08
---

# Notion

## What it is
Long-form documentation, architecture notes, and the `vibetrade-architecture`
docs. Used by PM and Architect roles for human-readable context that doesn't
fit a knowledge-repo file.

## Auth model
Notion integration token (`NOTION_TOKEN`) in GCP Secret Manager.

## Surface used
- Search pages.
- Read pages and databases.
- Create pages under a parent.
- Append content.

## Permissions / scopes
- Read/write on pages explicitly shared with the integration.

## Limits
- 3 req/sec average per integration.

## Notes
- `notion-client` v3 broke `databases.query()`. Coder bypasses the SDK and
  calls the REST API directly via `httpx`. **Don't revert.** See
  `coder-agent/.claude/CLAUDE.md`.
- URLs containing `?v=` are database views — the ID before `?v=` is a
  database ID, not a page ID. Use `notion_get_database`, not `notion_get_page`.
- Once Coder is fully generalized, prefer `coder-system` knowledge files
  over Notion for anything machine-queryable. Notion is for long-form
  human prose only.
