# Services Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

| ID | Name | Status | Owner | Tier | Tech | Runtime | File |
|---|---|---|---|---|---|---|---|
| `coder-core` | Coder Core | active | ro | core | python · fastapi | cloud-run (europe-west1) | [coder-core.md](./coder-core.md) |
| `coder-admin` | Coder Admin Panel | active | ro | core | typescript · react · vite · tailwind | cloud-run (europe-west1) | [coder-admin.md](./coder-admin.md) |

## Notes

- The previous `coder-agent` and `coder-agent-admin` services have been
  removed. The clean rebuild is tracked in
  [`../designs/wip/0001-generalize-coder-from-vibetrade.md`](../designs/wip/0001-generalize-coder-from-vibetrade.md).
- Worker fleet (per-role services) is intentionally not listed yet — see
  the WIP design for the planned split.
