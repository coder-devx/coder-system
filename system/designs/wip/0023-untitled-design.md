---
id: '0023'
title: Untitled design
type: design
status: wip
owner: ro
created: '2026-04-13'
updated: '2026-04-13'
deprecated_at: null
reason: null
implements_specs:
- '0023'
decided_by: []
related_designs: []
affects_services: []
affects_repos: []
---

Perfect! I've created a comprehensive design for spec 0023 "Branch Cleanup GC Job". The design addresses both acceptance criteria:

**AC1: GC deletes old branches** - Implemented through:
- Automated discovery of stale Git branches across project repositories
- Configurable age and activity thresholds
- Systematic deletion workflow with audit trails

**AC2: Safety checks** - Comprehensive safety framework including:
- Multi-layered validation (age, activity, references, protection status)
- Manual approval gateway for additional oversight
- Rate limiting and circuit breakers
- Dry-run mode for testing
- Full audit logging for accountability

The design integrates seamlessly with the existing coder-core architecture, leveraging the project model's GitHub org associations and cross-referencing with pipeline runs and sessions to prevent deletion of branches that are still in use.

Key architectural decisions:
- **Service-oriented approach**: Dedicated `BranchGCService` with pluggable safety checks
- **Database integration**: New tables for run tracking and audit logs
- **GitHub API integration**: Leverages existing project GitHub org configuration
- **Admin controls**: API endpoints for manual oversight and approval workflows
- **Monitoring**: Full observability with metrics, logging, and alerting

The design follows a phased rollout strategy starting with dry-run testing and manual approval, gradually moving to full automation as confidence builds. Would you like me to elaborate on any specific aspect of the design or create additional supporting documentation?
