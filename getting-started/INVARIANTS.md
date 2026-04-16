# SDLC Dashboard — Project Invariants

These invariants are enforced across multiple layers. Violations block merges
and edits. See `standards/process/invariants.md` for the invariants standard.

## INV-001: No hardcoded file paths — use config or environment variables
- **Layers:** agent-instructions, hook, test
- **Verify:** `grep -rn --include='*.py' -E '(open\(|Path\()["\x27]/' src/ | grep -v '# invariant-exempt' | grep -v test`
- **Fail action:** Block merge
- **Rationale:** Hardcoded absolute paths break portability across environments and CI. All paths must come from configuration, environment variables, or be relative to a well-known project root.

## INV-002: All FastAPI endpoints must have response_model
- **Layers:** agent-instructions, hook, test
- **Verify:** `grep -rn --include='*.py' '@\(app\|router\)\.\(get\|post\|put\|patch\|delete\)' src/ | grep -v 'response_model' | grep -v '# invariant-exempt'`
- **Fail action:** Block merge
- **Rationale:** Explicit response models ensure API contracts are documented, validated, and visible in OpenAPI schema. They also catch serialization errors early.

## INV-003: No direct writes to .sdlc/ or .taskmaster/ state files
- **Layers:** agent-instructions, hook, test
- **Verify:** `grep -rn --include='*.py' -E '(open\(|write|Path\().*\.(sdlc|taskmaster)' src/ | grep -v 'mode.*r' | grep -v '# invariant-exempt'`
- **Fail action:** Block edit
- **Rationale:** The SDLC Dashboard is a read-only view. State files in .sdlc/ and .taskmaster/ are managed by their respective tools. Direct writes would corrupt state and create conflicts.

## INV-004: Tests must exist for every Python module in src/
- **Layers:** hook, ci
- **Verify:** `find src/ -name '*.py' ! -name '__init__.py' ! -name 'py.typed' -exec basename {} .py \; | while read m; do test -f "tests/test_${m}.py" || echo "Missing test: tests/test_${m}.py"; done`
- **Fail action:** Block edit
- **Rationale:** Full test coverage is required. Every production module must have a corresponding test file to enforce red/green TDD workflow.

## CONCEPT-001: Organization ownership for multi-tenant queries

All database queries that return tenant-scoped data MUST filter by the
authenticated user's organization_id, not the target entity's organization_id.

- **Contexts:** IAM, Relationships, Compliance, Search
- **Precondition:** Authenticated user has a non-null organization_id
- **Postcondition:** Every row in the result set belongs to an org the user has access to (via direct membership or relationship grant)
- **Invariant:** `query.filter_org == auth_user.org_id` (never `entity.org_id`)
- **Layers:** test, hook, agent-instructions
- **Verify:** `grep -rn 'filter.*org_id' src/ | grep -v 'current_user' | grep -v '# concept-exempt: CONCEPT-001'`
- **Fail action:** Block merge

## CONCEPT-002: Vendor status vocabulary across ETL and API boundaries

The canonical vocabulary for vendor lifecycle status must be declared per context.

- **Contexts:** Salesforce ETL, Internal API, Compliance
- **Precondition:** Status values entering the system are one of the declared terms for the originating context
- **Postcondition:** Status values stored in the database use canonical terms, not context-specific synonyms
- **Invariant:** No status value exists in the database that is not in the canonical vocabulary
- **Layers:** test, ci
- **Verify:** `python3 scripts/check-vocabulary.py vendor_status`
- **Fail action:** Block merge

### Vocabulary: vendor_status
| Context | Term | Canonical |
|---------|------|-----------|
| Salesforce ETL | "Approved" | active |
| Salesforce ETL | "Onboarding In Process" | pending |
| Salesforce ETL | "Terminated" | inactive |
| Salesforce ETL | "Suspended" | suspended |
| Internal API | "active" | active |
| Internal API | "pending" | pending |
| Internal API | "inactive" | inactive |
| Internal API | "suspended" | suspended |

## CONCEPT-003: Event handler registration lifecycle

Event handlers must be registered via an explicit registration function call,
not by mutating module-level state at import time.

- **Contexts:** Events, Search, Notifications
- **Precondition:** The application has completed initialization before any event handler is invoked
- **Postcondition:** All registered handlers are callable and their registrations are reversible (for testing)
- **Invariant:** No event handler registration occurs at module import time; all registration happens in explicit setup functions
- **Layers:** test, hook, agent-instructions
- **Verify:** `grep -rn '_handlers\[' src/ | grep -v 'def register' | grep -v '# concept-exempt: CONCEPT-003'`
- **Fail action:** Block merge
