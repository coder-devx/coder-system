---
id: short-kebab-id
name: Human Readable Name
type: repo
status: active           # active | archived
owner: ro
github: org/repo
default_branch: main
hosts_services: []       # service ids this repo deploys
language: python
ci:
  provider: github-actions   # github-actions | none | …
  workflows: []
cd:
  target: cloud-run
  trigger: manual            # manual | push-to-main | tag | …
decided_by: []
---

# {Name}

## What it holds
One paragraph.

## Layout
```
src/
  …
```

## CI / CD
- CI: workflows, gates.
- CD: how a change reaches prod.

## Branching
- Default branch, PR rules, environments.

## Linked services
- See frontmatter `hosts_services`.

## Notes
- …
