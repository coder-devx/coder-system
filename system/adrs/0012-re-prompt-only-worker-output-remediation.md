---
id: "0012"
title: Re-prompt only, no programmatic repair, for malformed worker JSON
type: adr
status: accepted
date: 2026-04-15
deciders: [ro]
relates_to_designs: ["0025"]
---

# ADR 0012 — Re-prompt only, no programmatic repair, for malformed worker JSON

## Context

Spec 0025 (worker output compliance) introduces schema validation for
PM, Architect, and Team Manager worker output. When the model's JSON
is malformed we need a remediation strategy. Two kinds of malformation
appear in practice:

1. **Wrapper noise** — code fences around the JSON, a leading
   "Sure, here it is:" sentence, a trailing markdown explanation.
   Cheap to strip in code, always.
2. **Structural errors** — missing required fields, wrong types,
   semantic violations (non-kebab slugs, unbalanced Mermaid fences,
   acceptance criteria with zero checkboxes). No reliable programmatic
   fix.

A tempting middle path is "repair wrapper noise, re-prompt on
structural errors". We considered and rejected it.

## Options considered

1. **Re-prompt only.** Any validation failure — wrapper, structural,
   or both — goes back to the model with the errors and the raw
   output. The worker never edits the model's bytes.
2. **Repair wrapper, re-prompt structural.** A small whitelist of
   known-safe transformations (strip triple-backtick fences, trim
   preamble/postamble to the outermost `{`/`}`) runs before
   validation. Structural errors still re-prompt.
3. **Repair as much as possible.** Apply wrapper-strip plus
   permissive JSON parsing (trailing commas, single quotes) plus
   field-by-field coercion. Re-prompt only when repair fails.

## Decision

Adopt **option 1 — re-prompt only**. Workers do not modify model
output before validation beyond stripping the outermost trailing
newline and whitespace. Everything else — including code fences —
is treated as a schema failure and fed back to the model.

## Rationale

Programmatic repair in a system that writes to a knowledge repo and
a task database is a silent-corruption risk. A fence-strip today is
a comma-tolerant parser next quarter is a "just coerce the type
field" the quarter after that. The repair code becomes a second,
undocumented schema that drifts from the real one. Operators can't
tell whether a given artifact was produced clean or patched.

Re-prompting keeps the model responsible for its own output format.
The feedback loop also *teaches* the model within a single task — if
the first response had fences, the second usually doesn't. We measure
this directly via `worker_schema_retries_total{outcome=success}`; if
the retry-success rate stays high, the approach is working.

The cost objection (a re-prompt is ~2× the tokens of a repair) is
real but bounded: retry budget defaults to 2, and the metric surfaces
chronic retry patterns for prompt improvement. That's a better feedback
signal than a repair path that quietly hides prompt quality problems.

The one exception — stripping trailing whitespace — is so trivial and
so clearly "transport noise" that excluding it would mean re-prompting
on a literal `"…}\n"` mismatch. Anything past that boundary is model
output and gets treated as such.

## Consequences

- **Positive.** The validator is the single source of truth for
  "is this output acceptable". No hidden repair layer to audit.
- **Positive.** Retry-success rate becomes a real prompt-quality
  metric. A worker whose retry rate trends upward is a prompt that
  needs attention; the signal isn't masked by repair.
- **Positive.** Failed runs produce actionable `failure_detail` the
  operator can read — the raw output is the model's, not a
  half-repaired mutant.
- **Negative.** Higher token cost per failed attempt than a repair
  approach. Mitigated by the 2-attempt default budget and the cost
  regression alert in spec 0032.
- **Negative.** A single malformed closing fence forces a full
  re-prompt even though a human could fix it in a second. Acceptable
  given the silent-corruption alternative.
- **Follow-up.** If operational data shows that >50% of schema
  failures are wrapper-only (fence, preamble), revisit with a
  narrow, logged, opt-in repair pass. Do not add repair quietly.
