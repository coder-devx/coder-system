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

> **Worker roles:** put this content in `<role-id>/role.md` and create
> per-mode contracts under `<role-id>/tasks/<mode>.md`. Add a `Modes`
> table at the bottom (see other worker roles for the shape).
> **Non-worker roles:** keep this as a flat `<role-id>.md`.

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

## Modes you run in (worker roles only — drop this section for non-worker roles)

| Mode | Trigger | Contract |
|---|---|---|
| `<mode>` | <when this mode fires> | [`tasks/<mode>.md`](./tasks/<mode>.md) |
