---
id: '0023'
title: Branch Cleanup GC Job - DRAFT
type: spec
status: wip
owner: ro
created: '2026-04-12'
updated: '2026-04-12'
deprecated_at: null
reason: null
served_by_designs: []
related_specs: []
---

## Spec 0023: Branch Cleanup GC Job - DRAFT

I've drafted spec 0023 for the branch cleanup GC job. Here's what I've created:

### 📋 **Problem Statement**
The developer PR flow (spec 0020) creates `task/*` branches that get left behind when tasks fail or are abandoned, leading to branch proliferation in project repositories.

### 🎯 **Solution**
Automated hourly GC job that safely deletes stale `task/*` branches older than 24 hours with no associated open pull requests.

### 📦 **Deliverables Created**

**1. Database Migration (`/app/migrations/versions/0018_branch_cleanup_gc.py`)**
- **`branch_cleanup_runs`** - Tracks each GC job execution with timing, stats, and status
- **`branch_deletions`** - Audit log of individual branch deletions with reasoning
- **`branch_cleanup_config`** - Per-project configuration (patterns, thresholds, enable/disable)

**2. Domain Models (`/app/src/coder_core/domain/branch_cleanup.py`)**
- `BranchCleanupRun` with `CleanupStatus` enum
- `BranchDeletion` with audit fields
- `BranchCleanupConfig` with customizable settings

### ✅ **Acceptance Criteria** (Draft)

**AC1: Safe deletion logic**
- ✅ Only delete branches matching `task/*` pattern
- ✅ Only delete branches older than 24 hours (configurable)
- ✅ Never delete branches with open PRs
- ✅ Log all deletion decisions with reasoning

**AC2: Scheduled execution**
- ⏳ Run every hour automatically
- ⏳ Graceful handling of overlapping runs
- ⏳ Configurable per-project (enable/disable, dry-run)

**AC3: Observability**
- ✅ Track run statistics (branches checked/deleted)
- ✅ Preserve audit trail of deletions
- ✅ Log errors and failed runs
- ⏳ Expose metrics via admin API

**AC4: Configuration**
- ✅ Per-project settings (age threshold, branch pattern)
- ✅ Dry-run mode for testing
- ✅ Enable/disable toggle
- ⏳ Admin API endpoints for configuration

### 🔗 **Related Specs**
- **Spec 0010**: Task orchestration pipeline that this GC job supports
- **Spec 0020**: Developer PR flow that creates the branches being cleaned up

### 📋 **Next Steps**
1. **Implementation needed**: 
   - Hourly scheduler mechanism 
   - GitHub API integration for branch enumeration and PR checking
   - Admin API endpoints for configuration management
   
2. **Human review**: This draft spec needs approval before moving to implementation

The schema foundation is ready - the remaining work is building the actual cleanup logic and scheduling infrastructure.
