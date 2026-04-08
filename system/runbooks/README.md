# runbooks/

Operational procedures. Step-by-step guides for things humans (or workers)
do that are too procedural for a design and too repeatable to leave to
memory.

## When to write a runbook

- A procedure runs more than once.
- Getting it wrong has a cost.
- The steps span multiple systems.

## What a runbook is not

- Not a design (designs explain *why*, runbooks explain *how-to*).
- Not a tutorial. Assume the reader knows the system.
- Not architecture documentation.

## Conventions

- One file per runbook. Filename: `{verb}-{object}.md` (e.g.
  `rotate-anthropic-key.md`, `onboard-new-project.md`).
- Each runbook has a **trigger** (when to run it) and a **success
  condition** (how you know it worked).
- Keep them tight. If a runbook grows past ~100 lines, split it.
