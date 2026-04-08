# Repos Registry

> Generated view of [`registry.yaml`](./registry.yaml). Do not hand-edit.

| ID | GitHub | Status | Hosts | Language | CI | CD | File |
|---|---|---|---|---|---|---|---|
| `coder-core` | coder-devx/coder-core | planned | coder-core | python | github-actions | cloud-run (push-to-main) | [coder-core.md](./coder-core.md) |
| `coder-admin` | coder-devx/coder-admin | planned | coder-admin | javascript | github-actions | cloud-run (push-to-main) | [coder-admin.md](./coder-admin.md) |
| `coder-system` | coder-devx/coder-system | active | — | markdown | github-actions (validate) | none | [coder-system.md](./coder-system.md) |

## Notes

- `coder-agent` and `coder-agent-admin` have been removed in favor of a
  clean rebuild as `coder-core` and `coder-admin`. See
  [`../designs/wip/0001-generalize-coder-from-vibetrade.md`](../designs/wip/0001-generalize-coder-from-vibetrade.md).
- Worker fleet repos (per-role) are not listed yet — likely live inside
  `coder-core` until the fleet split lands.
