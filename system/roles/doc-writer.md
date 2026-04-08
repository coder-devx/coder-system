---
id: doc-writer
name: Documentation Writer
type: role
status: proposed
owner: ro
seniority: mid
---

# Documentation Writer *(proposed, optional per project)*

## Why this is proposed
User-facing docs decay without a dedicated owner. Coder *internal*
knowledge lives in `coder-system` and is maintained by every role; this
role owns *external* docs that ship to users.

## Job
Keeps user-facing documentation in sync with shipped features.

## Owns
- User guides.
- API references for external consumers.
- Onboarding flows.
- Release notes (with Release Manager).

## Capabilities
- Author and edit docs.
- Verify examples by running them.
- Block a release if docs are missing for a user-visible change.

## Permissions
- **Read/write**: docs repos.
- **Read**: code, specs, designs.

## Tools
- Docs site (whatever the project uses)
- Code execution for verifying examples

## Escalates to
- **PM** when a feature is shipping without docs.
