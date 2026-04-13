---
id: '0023'
title: Draft Specification Complete
type: spec
status: wip
owner: ro
created: '2026-04-13'
updated: '2026-04-13'
deprecated_at: null
reason: null
served_by_designs: []
related_specs: []
---

## Draft Specification Complete

I've successfully drafted **Spec 0023: Branch Cleanup GC Job** and saved it to `/tmp/draft-spec-0023-branch-cleanup-gc.md` for your review.

### Key Features of This Spec:

**Problem Solved:** Automated cleanup of stale feature branches created by the developer worker to prevent repository clutter and GitHub API rate limit issues.

**Core Components:**
1. **Database Schema**: New `branch_name` column on tasks table to track created branches
2. **GC Worker**: New role worker that safely deletes eligible branches
3. **GitHub API Integration**: Extensions for branch listing, PR checking, and deletion
4. **Safety Mechanisms**: Multi-layer verification (naming patterns, PR status, age gates)

**Integration with Related Specs:**
- **Spec 0010** (Task Orchestration): Uses task stages to identify cleanup-eligible branches
- **Spec 0020** (Developer PR Flow): Correlates branches with PR status for safe cleanup

**Risk Mitigation:** Comprehensive safety checks to prevent accidental deletion of active work, including branch pattern verification, PR status validation, and configurable retention periods.

### Next Steps:
1. **Your review and feedback** on the acceptance criteria and technical approach
2. **Approval** to promote from draft to active spec status  
3. **Handoff to Team Manager** for implementation task breakdown

The spec follows your established patterns with numbered ACs, migration-based schema changes, and integration with existing workers and GitHub client. Would you like me to adjust any aspects of the specification before approval?
