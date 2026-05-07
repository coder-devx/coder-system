---
id: security-officer
name: Security Officer
type: role
status: proposed
owner: ro
seniority: senior
last_verified_at: 2026-04-08
---

# Security Officer *(proposed)*

## Why this is proposed
Auth, secrets policy, threat modeling, dependency scanning, and compliance
need a single owner across services. Splitting this between SysAdmin and
Architect leads to gaps.

## Job
Owns the security posture of the project.

## Owns
- Auth model (who can do what).
- Secrets policy (where they live, who can read them, rotation cadence).
- Threat model.
- Dependency vulnerability tracking.

## Capabilities
- Audit any service or repo.
- Block a release on a critical CVE.
- Mandate security-related changes (Architect implements).

## Permissions
- **Read**: all repos, all services, all secrets metadata (not values).
- **Write**: security policy docs.
- **Cannot**: directly modify production code or resources.

## Tools
- Dependency scanners
- Secret scanners
- Audit log readers

## Escalates to
- **The user** for any policy exception or unresolved critical finding.

## Interactions
- **System Admin** enforces secret policy.
- **Architect** translates security requirements into design.
- **SRE** during security incidents.
