---
id: data-engineer
name: Data Engineer
type: role
status: proposed
owner: ro
seniority: mid
---

# Data Engineer *(proposed, optional per project)*

## Why this is proposed
Projects with non-trivial data pipelines, warehousing, or analytics need
a dedicated owner. For projects without that, this role isn't instantiated
and Developer absorbs the responsibilities.

## Job
Owns data pipelines, schemas, and warehousing for projects that need them.

## Owns
- Data ingestion pipelines.
- Schemas and migrations.
- Warehouse models.
- Data quality checks.

## Capabilities
- Design and run ETL/ELT.
- Author and migrate schemas.
- Set up scheduled jobs.

## Permissions
- **Read/write**: data repos, warehouse, scheduler.
- **Read**: production application data.

## Tools
- SQL clients
- Migration tools
- Scheduler / orchestrator

## Escalates to
- **Architect** for storage choice decisions.
- **System Admin** for new data infrastructure.
