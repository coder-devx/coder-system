---
id: '0023'
title: Branch Cleanup Garbage Collection
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

I'll draft spec 0023 for the branch cleanup GC job. Let me first explore the project structure to understand the existing specs and template conventions.

<function_calls>
<invoke name="Read">
<parameter name="path">/app</parameter>
</invoke>
</function_calls>
<function_calls>
<invoke name="Glob">
<parameter name="pattern">**/spec*</parameter>
<parameter name="path">/app</parameter>
</invoke>
</function_calls>
<function_calls>
<invoke name="Glob">
<parameter name="pattern">**/*spec*</parameter>
<parameter name="path">/app</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Bash">
<parameter name="command">find /app -name "*spec*" -type f | head -10</parameter>
</invoke>
</function_calls>

Let me check for a specs directory or similar:

<function_calls>
<invoke name="Bash">
<parameter name="command">find /app -type d -name "*spec*" -o -name "docs" -o -name "specifications" | head -10</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Bash">
<parameter name="command">ls -la /app</parameter>
</invoke>
</function_calls>

Let me check if there's a knowledge directory or any existing specifications:

<function_calls>
<invoke name="Bash">
<parameter name="command">find /app -name "0020*" -o -name "0010*" | head -5</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Bash">
<parameter name="command">find /app -type f -exec grep -l "spec.*002" {} \; 2>/dev/null | head -5</parameter>
</invoke>
</function_calls>

Let me look for any existing product specifications or templates:

<function_calls>
<invoke name="Bash">
<parameter name="command">find /app -type f \( -name "*.md" -o -name "*.txt" \) -exec grep -l -i "specification\|acceptance.*criteria" {} \; | head -5</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Bash">
<parameter name="command">find /app -name "wip" -type d</parameter>
</invoke>
</function_calls>

Let me check if there's a knowledge system or specs directory structure:

<function_calls>
<invoke name="Read">
<parameter name="path">/app</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Bash">
<parameter name="command">ls -la /app/</parameter>
</invoke>
</function_calls>

I notice there are directories like `knowledge`, `roles`, and `services`. Let me explore the knowledge directory to understand the spec structure:

<function_calls>
<invoke name="Read">
<parameter name="path">/app/knowledge</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Read">
<parameter name="path">/app/knowledge/specs</parameter>
</invoke>
</function_calls>

Now let me look at existing specs to understand the template format:

<function_calls>
<invoke name="Read">
<parameter name="path">/app/knowledge/specs/wip</parameter>
</invoke>
</function_calls>

Let me check one of the existing specs to understand the format:

<function_calls>
<invoke name="Read">
<parameter name="path">/app/knowledge/specs/0010-git-flow.md</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Read">
<parameter name="path">/app/knowledge/specs/0020-developer-pr-flow.md</parameter>
</invoke>
</function_calls>

Perfect! Now I understand the spec format. Let me also check if there's a template:

<function_calls>
<invoke name="Bash">
<parameter name="command">find /app -name "*template*" -type f</parameter>
</invoke>
</function_calls>

<function_calls>
<invoke name="Read">
<parameter name="path">/app/knowledge/specs/template.md</parameter>
</invoke>
</function_calls>

Excellent! Now I have all the information I need. Based on the existing specs and template, I'll draft spec 0023 for the branch cleanup GC job. Let me create the draft:

<function_calls>
<invoke name="Write">
<parameter name="path">/app/knowledge/specs/wip/0023-branch-cleanup-gc.md</parameter>
<parameter name="content">---
id: 0023
title: Branch Cleanup Garbage Collection
status: wip
owner: ro
created: 2026-04-12
updated: 2026-04-12
related: [0010, 0020]
---

# Branch Cleanup Garbage Collection

## Problem
The developer PR flow (spec 0020) creates task/* branches that are left behind when tasks fail or are abandoned. Over time, these stale branches accumulate, creating repository clutter and potentially consuming unnecessary storage. We need an automated cleanup mechanism to maintain repository hygiene.

## Solution
Implement a scheduled garbage collection job that automatically removes stale task branches based on age and PR status. The job will run hourly and safely delete task/* branches that are older than 24 hours and have no associated open pull requests.

## Success Criteria
1. **Automated cleanup**: Stale task/* branches are automatically identified and removed without manual intervention
2. **Safe operation**: Branches with open PRs are never deleted, preventing accidental loss of active work
3. **Timely cleanup**: Branches are cleaned up within 24 hours of becoming stale
4. **Observability**: All cleanup operations are logged for audit and debugging purposes
5. **Reliable scheduling**: Cleanup job runs consistently on the hourly schedule

## Acceptance Criteria

### AC1: Branch Age Detection
**Given** a task/* branch exists in the repository  
**When** the GC job evaluates the branch  
**Then** it correctly determines if the branch is older than 24 hours based on the last commit timestamp

### AC2: PR Status Validation
**Given** a task/* branch has an open pull request  
**When** the GC job evaluates the branch  
**Then** the branch is excluded from deletion regardless of age

### AC3: Safe Deletion
**Given** multiple task/* branches exist, some with open PRs and some without  
**When** the GC job runs  
**Then** only branches older than 24 hours with no open PRs are deleted

### AC4: Logging and Observability
**Given** the GC job runs and deletes branches  
**When** cleanup operations complete  
**Then** each deleted branch is logged with timestamp, branch name, age, and reason for deletion

### AC5: Scheduled Execution
**Given** the GC job is configured  
**When** the system is running normally  
**Then** the job executes automatically every hour

### AC6: Error Handling
**Given** the GC job encounters errors (network issues, permission problems, etc.)  
**When** errors occur during execution  
**Then** errors are logged and the job continues processing other branches without crashing

### AC7: Pattern Matching
**Given** various branch names exist in the repository  
**When** the GC job runs  
**Then** it only considers branches matching the "task/*" pattern for deletion

## Technical Requirements

### Architecture
- Scheduled job component integrated with existing CI/CD infrastructure
- GitHub API integration for branch enumeration and PR status checking
- Configurable retention period (default 24 hours)
- Structured logging for operations and errors

### Security
- Requires repository write permissions for branch deletion
- Must authenticate with GitHub API using secure credentials
- Should implement rate limiting to avoid API quota exhaustion

### Performance
- Batch API requests where possible to minimize GitHub API calls
- Process branches in batches to handle repositories with many stale branches
- Implement timeout mechanisms to prevent job hanging

### Configuration
- Configurable branch pattern (default: "task/*")
- Configurable retention period (default: 24 hours)
- Configurable schedule (default: hourly)
- Enable/disable toggle for emergency stops

## Dependencies
- Requires GitHub API access with repository permissions
- Depends on existing git flow infrastructure (spec 0010)
- Integrates with developer PR flow patterns (spec 0020)
- Needs scheduling infrastructure (cron, GitHub Actions, or similar)

## Risks and Mitigations
1. **Accidental deletion of active work**
   - Mitigation: Strict PR status checking before deletion
   - Mitigation: Configurable retention period with safe default
2. **API rate limiting**
   - Mitigation: Implement exponential backoff and request batching
3. **Job failure leaving stale branches**
   - Mitigation: Robust error handling and logging for debugging
4. **Clock skew affecting age calculation**
   - Mitigation: Use standardized UTC timestamps for all calculations

## Success Metrics
- Number of stale branches cleaned up per hour/day
- Job execution success rate (>99%)
- Average branch lifetime before cleanup
- Zero incidents of active branch deletion

## Implementation Notes
The job should be implemented as part of the existing automation infrastructure and follow established patterns for scheduled tasks. Consider implementing a dry-run mode for initial testing and validation.
</parameter>
</invoke>
</function_calls>

I've drafted spec 0023 for the branch cleanup GC job. The specification follows the established template format and includes:

**Key Features:**
- Hourly scheduled cleanup of stale task/* branches older than 24 hours
- Safe operation that never deletes branches with open PRs
- Comprehensive logging for audit trail
- Robust error handling and security considerations

**Comprehensive Acceptance Criteria:**
- 7 ACs covering branch age detection, PR status validation, safe deletion, logging, scheduling, error handling, and pattern matching

**Technical Requirements:**
- GitHub API integration with proper authentication
- Configurable retention periods and patterns
- Performance optimizations for repositories with many branches

The spec is now saved as a draft in `/app/knowledge/specs/wip/0023-branch-cleanup-gc.md` awaiting human review and approval before promotion to active status.
