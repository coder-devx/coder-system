---
id: slack
name: Slack
type: integration
status: active
owner: ro
auth: bot-token + socket-mode
secret_storage: gcp-secret-manager
used_by_services: [coder-agent]
used_by_roles: [team-manager, sre, release-manager]
last_verified_at: 2026-04-08
---

# Slack

## What it is
Team communication. Coder posts deploy notifications, incident updates,
and replies to `/coder` slash command + @mentions in real time.

## Auth model
Slack app with bot token (`SLACK_BOT_TOKEN`), signing secret
(`SLACK_SIGNING_SECRET`), and app token for Socket Mode (`SLACK_APP_TOKEN`).
All in GCP Secret Manager.

## Surface used
- Post messages to channels (`#deployments`, `#incidents`, `#general`).
- Send DMs.
- List channels.
- Read recent messages.
- Receive events via Socket Mode (slash command, mentions, DMs).

## Permissions / scopes
- `chat:write`, `channels:read`, `groups:read`, `im:read`, `im:write`
- `commands` (for `/coder`)
- `app_mentions:read`

## Limits
- Standard Slack tier rate limits.

## Notes
- Use `AsyncWebClient` (not sync) — sync client breaks the asyncio loop.
- Channels for incidents/deployments are conventions, not enforced — see
  `coder-agent/AGENT_CONTEXT.md` for the current list.
