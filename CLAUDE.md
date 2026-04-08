# CLAUDE.md

This repo follows a cross-agent contract defined in [`AGENTS.md`](./AGENTS.md).

**Read `AGENTS.md` before doing anything in this repo.** It defines the
hard rules for adding, updating, and cross-linking knowledge artifacts.

Quick reminders specific to Claude Code:

- This is a knowledge repo, not a code repo. There is no build, no tests, no
  dev server. Verification = "does the registry still parse and do all
  cross-links resolve".
- Prefer `Edit` over `Write` for existing files. Frontmatter is fragile —
  preserve field order and indentation.
- When adding files, batch the registry update into the same change.
- See [`README.md`](./README.md) for the layout.
