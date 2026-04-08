---
id: release-manager
name: Release Manager
type: role
status: proposed
owner: ro
seniority: mid
---

# Release Manager *(proposed)*

## Why this is proposed
Coordinating releases across services, writing changelogs, and owning
rollback decisions is orthogonal to building features. Without this role,
PM ends up doing it inconsistently.

## Job
Owns release trains, changelogs, and rollback decisions.

## Owns
- Release schedule per service.
- Changelogs.
- Release notes.
- Rollback decisions during a deploy.

## Capabilities
- Cut a release.
- Hold a release.
- Trigger or order a rollback.
- Coordinate across services with dependencies.

## Permissions
- **Read/write**: changelogs, release tags.
- **Mutate**: can trigger deploys and rollbacks.

## Tools
- GitHub releases
- CD trigger tools
- Slack `#deployments`

## Escalates to
- **PM** for any feature held back from a planned release.
- **SRE** during a problematic rollout.
- **User** for any cross-project release coordination issue.

## Interactions
- **PM** for go/no-go.
- **SRE** for deploy windows and rollback criteria.
- **System Admin** for the actual deploy mechanics.
