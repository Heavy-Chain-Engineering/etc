# standards/architecture/

**Purpose:** 3 architecture standards that govern when and how to create abstractions, how to document architectural decisions, and how to enforce layer boundaries in application structure. Referenced primarily by the architect, backend-developer, and code-reviewer agents.

## Key Components
- `abstraction-rules.md` -- (Status: MANDATORY) Core rules: abstract only after a pattern appears twice, YAGNI (build for current task only), every abstraction has an indirection cost it must justify, name it or inline it. Abstract: shared business rules, external service interfaces, complex algorithms. Do NOT abstract: one-time operations, configuration, "just in case" library wrappers, thin delegating methods.
- `adr-process.md` -- (Status: MANDATORY) Architecture Decision Records required for technology choices, architectural pattern decisions, data model design, integration patterns, and any decision constraining future development. Template: Title, Date, Status (Proposed/Accepted/Superseded), Context, Decision, Consequences. ADRs live in `docs/adr/`, are numbered sequentially, immutable once accepted (supersede with a new ADR). Maximum 1 page.
- `layer-boundaries.md` -- (Status: MANDATORY) Dependencies flow inward: API Layer -> Service Layer -> Domain Layer, with Infrastructure Layer injected at boundaries. Four rules: no reverse dependencies (domain must not import API or infrastructure), no skip-layer imports (API must not import infrastructure directly), framework isolation (business logic must not depend on FastAPI/SQLAlchemy/LlamaIndex), dependency injection for infrastructure (constructor or FastAPI `Depends()`). Automatic review flags: UI importing data layer, business logic depending on HTTP objects, domain models inheriting ORM models.

## Dependencies
- Referenced by `architect.md`, `architect-reviewer.md`, `backend-developer.md`, and `code-reviewer.md` agent definitions
- Layer boundary violations flagged during code review by `code-reviewer.md` and `architect-reviewer.md`
- ADR process followed during Design phase (governed by `standards/process/sdlc-phases.md`)

## Patterns
- **Anti-over-engineering stance:** The abstraction rules explicitly favor concrete code over premature abstraction, requiring demonstrated duplication before extracting.
- **Immutable decision records:** ADRs are never edited after acceptance -- changes are recorded as new superseding ADRs, preserving the decision history.
- **Inward dependency direction:** The layer boundary standard enforces clean architecture where the domain layer has zero framework dependencies.

## Constraints
- All 3 standards are MANDATORY.
- ADRs must be 1 page maximum -- if longer, the decision needs to be decomposed.
- Domain layer code must have zero framework imports (no FastAPI, no SQLAlchemy, no LlamaIndex).
- Abstractions require demonstrated need (2+ occurrences) -- speculative abstraction is explicitly prohibited.
