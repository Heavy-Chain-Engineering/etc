# Layer Boundary Standards

## Status: MANDATORY
## Applies to: Architect, Backend Developer, Code Reviewer

## Dependency Direction
Dependencies flow INWARD toward core business logic:

```
API Layer -> Service Layer -> Domain Layer
                ^
Infrastructure Layer (DB, external services)
```

- **Domain Layer:** Pure business logic, domain models, no framework imports
- **Service Layer:** Orchestrates domain operations, depends on domain
- **API Layer:** HTTP concerns only (routing, serialization, auth), depends on service
- **Infrastructure Layer:** Database, external APIs, file I/O — injected at boundaries

## Rules
1. **No reverse dependencies.** Domain must not import from API or infrastructure.
2. **No skip-layer imports.** API must not import directly from infrastructure.
3. **Framework isolation.** Business logic must not depend on FastAPI, SQLAlchemy, or LlamaIndex directly. Use abstractions at boundaries.
4. **Dependency injection.** Infrastructure dependencies injected via constructor or FastAPI `Depends()`.

## Layer Violations (automatic review flag)
- UI importing from data layer
- Business logic depending on HTTP request/response objects
- Domain models inheriting from ORM models
- Shared utils importing from feature modules
