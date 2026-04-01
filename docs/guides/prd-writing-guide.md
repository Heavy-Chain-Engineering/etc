# PRD Writing Guide: From Research to Buildable Requirements


## What a PRD Is (and Isn't)

A PRD describes **WHAT** you're building. It defines scope, entities, business rules, and acceptance criteria — everything an implementation team (human or AI) needs to know about the *problem and requirements*.

A PRD does **NOT** describe HOW to build it. Technology choices, implementation patterns, library selections, and architecture decisions belong in ADRs. Mixing WHAT and HOW in a single document creates a specification that's simultaneously too vague on requirements and too rigid on implementation.

**The test**: Can an implementation team read this PRD and build the right product using *any* reasonable technology stack? If the PRD assumes a specific database, framework, or deployment model, those assumptions should be extracted into ADRs.

## The PRD Writing Process

### Step 1: Scope the Bounded Context

Each PRD covers one bounded context — a coherent slice of the domain with clear boundaries. Signs you need to split a PRD:

- Two distinct user personas with non-overlapping workflows
- Two entity clusters with no direct relationships
- A cross-cutting concern (search, audit, notifications) that serves multiple contexts

One focused PRD is better than one sprawling one. Cross-context concerns (search, audit, notifications) get their own PRD.

### Step 2: Start From Research

PRDs are synthesized from research, not invented from scratch. Before writing:

- Read all research reports touching this context
- Identify entities, relationships, and business rules mentioned across reports
- Note contradictions between reports (these become open questions, not silent choices)
- Catalog domain vocabulary — use the same terms the domain experts use

### Step 3: Write the PRD

Use the template below. Not every section applies to every PRD — scale each section to its complexity. A simple CRUD context might have 3 business rules and no domain events. A complex workflow context might have 30 business rules and 12 events.

### Step 4: Number Everything Testable

Business rules, acceptance criteria, and non-functional requirements all get identifiers. Format: `PRD-{nn}-BR-{nn}` for business rules, `PRD-{nn}-AC-{nn}` for acceptance criteria. This creates a direct traceability path from PRD to test.

### Step 5: Specify Seed Data

If the domain has catalog tables, type enums, default configurations, or reference data — list them explicitly. Agents inventing seed data is one of the most common sources of inconsistency across a project.

## PRD Template

```markdown
# PRD-{nn}: {Context Name}

**Date:** YYYY-MM-DD
**Status:** Draft | In Review | Approved
**Author:** {name}
**Bounded Context:** {context name}
**Depends On:** PRD-{nn} (if applicable)

## 1. Overview

One paragraph: what this context does, who it serves, and why it exists.

## 2. Users and Personas

Who interacts with this context? What are their goals?

| Persona | Role | Primary Goal |
|---------|------|-------------|
| ... | ... | ... |

## 3. User Stories

Numbered stories in standard format. Group by persona or workflow.

- **US-01**: As a {persona}, I want to {action} so that {outcome}.
- **US-02**: ...

Keep stories at the right altitude — not so high they're meaningless ("As a user, I
want the system to work"), not so low they're implementation tasks ("As a developer,
I want a database migration").

## 4. Entity Definitions

Schema-level detail for every entity in this context. This is the single most
important section — ambiguity here cascades into every implementation decision.

### {Entity Name}

| Field | Type | Constraints | Notes |
|-------|------|-------------|-------|
| id | UUID | PK | |
| name | text | required, unique per {scope} | |
| status | text | one of: {list values} | COMPUTED — see BR-03 |
| ... | ... | ... | ... |

**Relationships:**
- Belongs to {Parent} (many-to-one)
- Has many {Children} (one-to-many)
- References {OtherContext.Entity} via {foreign key or event}

Repeat for each entity.

## 5. Business Rules

Numbered, testable, unambiguous. An implementation agent should be able to write a
test directly from each rule.

- **PRD-{nn}-BR-01**: {Plain language rule}. Example: "A project cannot transition
  to Build phase until all Design DoD items are checked."
- **PRD-{nn}-BR-02**: {Rule}. Example: "Status is COMPUTED from {inputs}. It is
  never stored as an editable field."
- **PRD-{nn}-BR-03**: ...

**What makes a good business rule:**
- Testable: you can write an assertion for it
- Unambiguous: one interpretation, not two
- Scoped: it belongs to THIS context, not another
- Numbered: traceable from PRD to test

**What is NOT a business rule:**
- Implementation details ("Use PostgreSQL RLS for tenant isolation")
- Architectural decisions ("Events are published via LISTEN/NOTIFY")
- UI layout preferences ("Show the status badge in the top-right corner")

## 6. API Endpoints (if applicable)

Define the contract, not the implementation. Focus on resources, verbs, payloads,
and response shapes.

### {Resource}

| Method | Path | Description | Request Body | Response |
|--------|------|-------------|-------------|----------|
| POST | /api/{resource} | Create a new {entity} | `{fields}` | `201: {entity}` |
| GET | /api/{resource}/{id} | Get by ID | — | `200: {entity}` |
| PATCH | /api/{resource}/{id} | Update | `{partial fields}` | `200: {entity}` |
| GET | /api/{resource} | List with filters | Query: `?status=active` | `200: [{entity}]` |

**Error responses** follow a consistent shape across all endpoints:
```json
{"error": {"code": "VALIDATION_ERROR", "message": "...", "details": [...]}}
```

## 7. Domain Events

Events this context publishes and consumes. Events are the integration contract
between bounded contexts — get these wrong and contexts couple in hidden ways.

### Published Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `{context}.{entity}.created` | New entity created | `{id, key fields}` |
| `{context}.{entity}.status_changed` | Status transition | `{id, old_status, new_status}` |
| ... | ... | ... |

### Consumed Events

| Event | Source Context | Action Taken |
|-------|--------------|-------------|
| `{other_context}.{entity}.completed` | {Other Context} | {What happens} |
| ... | ... | ... |

## 8. Seed Data and Reference Values

Explicit values for catalog tables, type enums, and default configurations.
Implementation agents MUST use these values — do not invent alternatives.

### {Catalog Name}

| Value | Description |
|-------|-------------|
| ... | ... |

## 9. Non-Functional Requirements

| Requirement | Target | Rationale |
|-------------|--------|-----------|
| Response time | < 200ms for reads, < 500ms for writes | User-facing API |
| Storage | {estimate} per {unit} | Based on {assumption} |
| Concurrency | {N} simultaneous {operations} | Peak usage estimate |
| Retention | {period} | Regulatory or business need |
| Security | {requirement} | e.g., "PII fields encrypted at rest" |

## 10. Acceptance Criteria

The checklist that determines whether this context is "done." Each criterion maps
to one or more business rules or user stories.

- [ ] **PRD-{nn}-AC-01**: {Criterion tied to US-01 or BR-01}
- [ ] **PRD-{nn}-AC-02**: ...

## 11. Out of Scope

Explicitly state what this PRD does NOT cover. This prevents scope creep and gives
implementation agents clear boundaries.

- NOT building {feature} (deferred to v2)
- NOT integrating with {system} (separate PRD)
- NOT handling {edge case} (documented in {location} for future consideration)

## 12. Open Questions

Unresolved items that need stakeholder input before implementation. Each question
should identify who can answer it.

- [ ] **OQ-01**: {Question}. Ask: {stakeholder/SME}.
- [ ] **OQ-02**: ...
```

## Common Mistakes

### 1. Mixing WHAT and HOW

**Wrong**: "User authentication uses JWT tokens stored in HttpOnly cookies with a 15-minute expiry and refresh token rotation."

**Right (PRD)**: "Users must be able to authenticate with email and password. Sessions expire after inactivity. Users should not need to re-enter credentials on every visit."

**Right (ADR)**: "ADR-15: JWT with HttpOnly cookies, 15-minute access token, 7-day refresh token with rotation."

The PRD states the requirement. The ADR makes the technology decision.

### 2. Unstestable Business Rules

**Wrong**: "The system should be fast."

**Right**: "PRD-03-BR-12: Search results return within 200ms for queries matching fewer than 10,000 records."

### 3. Implicit Seed Data

**Wrong**: "The system supports multiple project types."

**Right**: A table listing every project type with its description, default behavior, and constraints.

### 4. Missing Domain Events

If two bounded contexts need to coordinate, the integration mechanism must be explicit. "Context A needs data from Context B" is not a specification — it's a hand-wave. Define the events, their payloads, and what the consumer does with them.

### 5. PRD Scope Creep

A PRD that covers "everything about users" is too broad. Split by bounded context: authentication is separate from user profiles is separate from user preferences is separate from user analytics.

### 6. Invented Terminology

Use the language your domain experts use. If the business calls it a "vendor," don't rename it to "supplier" because it sounds better. Mismatched terminology creates translation overhead that compounds across every document and conversation.

## Scaling the Template

### For Simple Contexts

Skip sections that don't apply. A simple CRUD context might only need:
- Overview (2 sentences)
- Entity Definitions (one entity)
- Business Rules (3-5 rules)
- API Endpoints (standard CRUD)
- Acceptance Criteria (3-5 items)

### For Complex Contexts

Expand sections that need it. A workflow engine context might have:
- 30+ business rules covering every state transition
- 12+ domain events
- Complex entity relationships with computed fields
- Extensive seed data for workflow stages and actions
- Multiple personas with distinct permission models

### For Cross-Cutting Concerns

Search, audit, notifications, and similar horizontal concerns need their own PRD, but the template shifts:
- Entity Definitions becomes "What data is indexed/logged/delivered"
- API Endpoints becomes "Integration points with other contexts"
- Domain Events becomes the primary section (these contexts are event-driven by nature)

## After the PRD

Once PRDs are written and reviewed (Phase 3: Stakeholder Review), they feed into the Architecture Review (Phase 4). During architecture review, expect PRDs to get amended as ADR decisions refine or override initial requirements. That's normal — the PRD is a living document until the Build Candidate is tagged.

Track contradictions between PRDs and ADRs. The gap analysis (Phase 5) specifically looks for these.
