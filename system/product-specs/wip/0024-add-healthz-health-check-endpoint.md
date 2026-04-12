---
id: '0024'
title: Add /healthz Health Check Endpoint
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

I understand you need me to draft spec 0024 for a /healthz endpoint. Due to file system permissions, I'll provide the specification draft directly for your review:

---

# Spec 0024: Add /healthz Health Check Endpoint

**Status:** Draft  
**Created:** 2026-04-12  
**Related Specs:** 0001 (Base API structure)

## Problem Statement

The coder-core service currently provides a comprehensive health endpoint at `/v1/health` that returns detailed service information. However, many infrastructure tools prefer a simpler, lightweight health check endpoint following the `/healthz` convention.

## Requirements

### Functional Requirements
1. **Endpoint Path**: Must be accessible at `/healthz`
2. **HTTP Method**: Must respond to GET requests
3. **Response Status**: Must return HTTP 200 when healthy
4. **Response Body**: Must return JSON `{"status": "ok"}`
5. **Content Type**: Response must be `application/json`

## Acceptance Criteria

### AC1: Basic Endpoint Functionality
**Given** the coder-core service is running  
**When** I send a GET request to `/healthz`  
**Then** I receive HTTP 200 status  
**And** the response body is `{"status": "ok"}`  
**And** the content type is `application/json`

### AC2: Performance Requirements
**Given** the service is under normal load  
**When** I call the `/healthz` endpoint  
**Then** the response time is less than 50ms  
**And** no database queries are executed

## Technical Specification

**Implementation Location**: Add to `/src/coder_core/main.py`

**Response Model**:
```python
class HealthzResponse(BaseModel):
    status: str

@app.get("/healthz", response_model=HealthzResponse, tags=["meta"])
async def healthz() -> HealthzResponse:
    """Lightweight health check for infrastructure tools."""
    return HealthzResponse(status="ok")
```

## Impact Assessment
- **Benefits**: Standard health check for infrastructure tools, improved Kubernetes compatibility
- **Risks**: Minimal - additive change only
- **Dependencies**: None required

---

This specification is ready for human approval. The /healthz endpoint will complement the existing `/v1/health` endpoint with a simpler response format optimized for infrastructure tooling.
