---
id: qa-engineer
name: QA Engineer
type: role
status: proposed
owner: ro
seniority: mid
last_verified_at: 2026-04-08
---

# QA Engineer *(proposed)*

## Why this is proposed
Test strategy, coverage, and regression suites are heavy enough to deserve
a dedicated owner separate from the Developer who writes the production
code. Without this role, test quality drifts because each Developer only
sees their own task.

## Job
Owns test strategy and overall coverage across the project.

## Owns
- The test pyramid (unit / integration / e2e ratios).
- Regression suites.
- Coverage targets per service.
- Acceptance test scaffolding for new specs.

## Capabilities
- Write tests, especially e2e and regression.
- Review Developer PRs for test adequacy.
- Block merge on coverage regression.
- Curate fixtures and seed data.

## Permissions
- **Read/write**: test directories in all repos.
- **Read**: production code.
- **Cannot**: edit production code outside test scaffolding.

## Tools
- Code editing
- Test environment tools
- CI logs

## Escalates to
- **Architect** when the system shape makes a category of tests impossible.
- **PM** when acceptance criteria aren't testable.

## Interactions
- **Developer** — collaboratively closes coverage gaps.
- **SRE** — shares signals (e.g., flaky tests = unstable system).
- **Consultant** — feeds patterns about test failures.
