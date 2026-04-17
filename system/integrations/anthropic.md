---
id: anthropic
name: Anthropic API
type: integration
status: active
owner: ro
auth: api-key
secret_storage: gcp-secret-manager
used_by_services: [coder-agent]
used_by_roles: []
last_verified_at: 2026-04-08
---

# Anthropic API

## What it is
The model provider. Coder workers run on Claude (currently Claude 4.6
family) via the **Claude Agent SDK**, which wraps the API and provides the
agent loop, tool dispatch, and built-in tools (Bash, Read, Write, Edit,
Glob, Grep).

## Auth model
API key (`ANTHROPIC_API_KEY`) in GCP Secret Manager.

## Surface used
- Messages API (via Claude Agent SDK).
- Streaming with extended thinking.
- Tool use (custom MCP servers + built-in tools).

## Permissions / scopes
- N/A. Single API key.

## Limits
- Per-key rate limits and monthly quota. Watch costs in the Anthropic console.

## Notes
- Thinking block signatures must come from `stream.get_final_message()`,
  not manually accumulated stream events. Otherwise the next turn rejects
  the thinking blocks. See `coder-agent/.claude/CLAUDE.md`.
- The Dockerfile bundles Node.js 20 + Claude Code CLI because the Agent
  SDK uses them at runtime — adds ~200 MB to the image.
