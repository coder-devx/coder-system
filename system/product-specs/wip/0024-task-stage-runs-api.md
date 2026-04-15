---
id: '0024'
title: Task Stage Runs API
type: spec
status: wip
owner: ro
created: '2026-04-14'
updated: '2026-04-15'
served_by_designs:
- '0024'
related_specs: []
---

# Product Specification: Task Stage Runs API Endpoint

## Overview
**ID**: `task-stage-runs-api`  
**Type**: Feature  
**Status**: Draft (WIP)  
**Owner**: Product Manager  
**Created**: 2026-04-14

## Problem Statement
Add a `/v1/projects/{project_id}/tasks/{task_id}/stage-runs` endpoint that returns the archived TaskStageRunRow rows for a task, ordered by recorded_at ascending. Response shape: TaskStageRunRead (defined in domain/task_stage_run.py). Include an integration test. Keep scope tight — no admin UI work, just the API endpoint.

## Context
The TaskStageRunRow table was added in migration 0018 as a per-dispatch archive for offline debugging. The live TaskRow shows only the most recent run, but this table preserves every historical stage dispatch so operators can walk previous stages without diving into Cloud Run logs. 

Currently, there's no API endpoint to access this archived data, limiting its utility for debugging and operational analysis.

## Requirements

### Functional Requirements

#### FR-1: List Task Stage Runs Endpoint
**Endpoint**: `GET /v1/projects/{project_id}/tasks/{task_id}/stage-runs`

**Path Parameters**:
- `project_id` (required): Project identifier (kebab-case)
- `task_id` (required): Task UUID

**Query Parameters**:
- `limit` (optional): Maximum rows returned. Default: 100, Range: 1-500
- `stage` (optional): Filter by pipeline stage (e.g., "executing", "testing", "reviewing")  
- `status` (optional): Filter by status (e.g., "succeeded", "failed", "timed_out")

**Response Codes**:
- **200 OK**: `list[TaskStageRunRead]` ordered by `recorded_at` ascending
- **404 Not Found**: Task not found or belongs to different project
- **422 Unprocessable Entity**: Invalid limit, stage, or status values

#### FR-2: Data Ordering
Results MUST be ordered by `recorded_at` ascending to provide chronological view of task execution history.

#### FR-3: Response Format
Use existing `TaskStageRunRead` schema (unchanged) containing:
- Basic identifiers: `id`, `task_id`, `project_id`
- Execution context: `stage`, `role`, `prompt`
- Results: `status`, `result`, `error`
- Artifacts: `transcript_uri`, `commit_sha`, `pr_url`, `review_verdict`
- Metrics: `cost_input_tokens`, `cost_output_tokens`
- Timestamps: `started_at`, `finished_at`, `recorded_at`

### Non-Functional Requirements

#### NFR-1: Security & Multi-tenancy
- Enforce `X-Api-Key` header validation via `require_project_auth` dependency
- Filter by both `project_id` AND `task_id` to enforce tenant isolation
- Return 404 (not 403) for cross-tenant access to avoid information leakage

#### NFR-2: Performance
- Leverage existing `(task_id, recorded_at)` database index
- Default limit of 100 rows, maximum of 500 (follows task_messages pattern)
- Return empty list (200) for tasks with no runs yet

#### NFR-3: Error Handling
Follow established project patterns:
- Use `HTTPException` with structured `detail` containing `code` and `message`
- Error codes: `task_not_found`, `invalid_limit`, `invalid_stage`, `invalid_status`

## Implementation Plan

### 1. API Router Module
**File**: `/app/src/coder_core/api/task_stage_runs.py`

Create new router following established patterns:
```python
router = APIRouter(
    prefix="/v1/projects/{project_id}/tasks/{task_id}/stage-runs", 
    tags=["task_stage_runs"]
)
```

### 2. Main App Registration  
**File**: `/app/src/coder_core/main.py`
```python
from coder_core.api import task_stage_runs as task_stage_runs_api
app.include_router(task_stage_runs_api.router)
```

### 3. Database Query Pattern
Follow task logs endpoint pattern:
- Multi-tenant filtering by `project_id` AND `task_id`
- Use `order_by(TaskStageRunRow.recorded_at.asc())`
- Apply optional filters before ordering
- Convert to Pydantic using existing `to_read()` helper

## Acceptance Criteria

### AC-1: Basic Functionality ✅
**Given** a task with multiple stage runs  
**When** I call `GET /v1/projects/{project_id}/tasks/{task_id}/stage-runs`  
**Then** I receive a list of `TaskStageRunRead` objects ordered by `recorded_at` ascending

### AC-2: Multi-tenant Security ✅
**Given** I have API key for project A  
**When** I attempt to access stage runs for a task in project B  
**Then** I receive a 404 Not Found response (not 403)

### AC-3: Empty Result Handling ✅
**Given** a task with no stage runs yet  
**When** I call the stage runs endpoint  
**Then** I receive an empty list `[]` with 200 OK status

### AC-4: Query Parameter Filtering ✅
**Given** stage runs with different stages and statuses  
**When** I call with `?stage=executing&status=succeeded`  
**Then** I receive only runs matching both filters, chronologically ordered

### AC-5: Input Validation ✅
**Given** invalid query parameters  
**When** I call with `?limit=1000` (exceeds max of 500)  
**Then** I receive 422 error with code "invalid_limit"

### AC-6: Integration Test Coverage ✅
**Given** the implementation is complete  
**When** integration tests are run  
**Then** all core functionality is validated including cross-tenant security

## Test Requirements

**Test File**: `/app/tests/integration/test_task_stage_runs_api.py` (new)

**Key Test Cases**:
1. Empty result returns `[]` (200) for task with no runs
2. Chronological ordering by `recorded_at`
3. Cross-tenant access returns 404
4. Query parameter filtering works correctly
5. Limit validation (1-500 range)
6. Invalid enum values return 422
7. Non-existent task returns 404

## Dependencies & Assets
✅ **Ready**: 
- `TaskStageRunRow` ORM model 
- `TaskStageRunRead` Pydantic schema
- Database table with proper index
- Auth patterns and error handling conventions

## Risks & Mitigations
- **Performance**: Large result sets → Limited by max 500 rows per request
- **Security**: Cross-tenant data access → Enforced by dual filtering on project_id + task_id

## Out of Scope
- Admin UI or frontend components
- Schema modifications to existing models  
- Real-time updates or streaming
- Advanced pagination (offset-based)
- Performance optimizations beyond existing index

---

**Status**: Ready for implementation  
**Next Steps**: 
1. Implement API router module following established patterns
2. Register router in main application  
3. Create integration tests
4. Validate against all acceptance criteria

This specification provides a clear, implementable plan that leverages existing infrastructure and follows established project conventions. The scope is appropriately tight while ensuring security and usability requirements are met.
