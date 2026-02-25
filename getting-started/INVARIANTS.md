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
