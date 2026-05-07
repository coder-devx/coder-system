---
id: short-kebab-id
name: Human Readable Name
type: role
status: defined          # defined | proposed | deprecated
owner: ro
seniority: senior        # junior | mid | senior | lead
last_verified_at: YYYY-MM-DD
---

# {Name}

> Place this content at `<role-id>/role.md` (every role uses the
> folder shape — ADR 0027). Worker roles also create per-mode
> contracts under `<role-id>/tasks/<mode>.md` and populate the
> `Modes` table at the bottom; non-worker roles drop that section.

## Job (one sentence)
…

## Owns
- Bullet list of artifacts and outcomes this role owns.

## Capabilities
- What the role can *do* — verbs.

## Permissions
- What systems this role can read / write / mutate.
- What it cannot.

## Tools
- The tool catalog this role has access to.

## Inputs
- What this role consumes (specs, tasks, signals, …).

## Outputs
- What this role produces (PRs, ADRs, decisions, deploys, …).

## Escalates to
- Who/what this role escalates to when stuck.

## Interactions
- Which other roles it talks to and about what.

## Worked example
A short paragraph showing a typical task flowing through this role.

## Modes you run in (worker roles only — drop this section if the role isn't dispatched)

| Mode | Trigger | Contract |
|---|---|---|
| `<mode>` | <when this mode fires> | [`tasks/<mode>.md`](./tasks/<mode>.md) |
