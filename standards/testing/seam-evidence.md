# Seam Evidence Standard

## Purpose

The seam evidence standard ensures that integration tests exist for
architecturally significant boundaries between bounded contexts. It
complements the existing test tier system (see `testing-standards.md`)
by adding structural verification that the middle layer of the testing
pyramid is not empty at critical seams.

## The Seam Manifest (SEAMS.md)

Each project MAY declare a `SEAMS.md` file at its root. The file is
human-readable markdown that is also machine-parseable. Each seam is a
level-2 heading following this structure:

```markdown
## SEAM-001: Short description of the integration seam
- **Producer:** path/to/producer/directory/
- **Consumer:** path/to/consumer/directory/
- **Interface:** Description of the contract (model, API endpoint, event, etc.)
- **Integration test:** path/to/tests/integration/test_file.py
- **Evidence level:** L1 | L2 | L3
- **Critical path:** User-facing flow that depends on this seam
```

### Required fields

- **ID** (in heading): `SEAM-NNN` for standard seams, `SEAM-DEV-NNN` for
  fixture fidelity seams.
- **Producer:** Directory path of the producing bounded context.
- **Consumer:** Directory path of the consuming bounded context.
- **Interface:** Human-readable description of what crosses the boundary.
- **Integration test:** Path to the test file that exercises this seam.
- **Evidence level:** One of L1, L2, or L3.

### Optional fields

- **Critical path:** The user-facing flow that depends on this seam.
- **Concept:** Reference to a CONCEPT entry in INVARIANTS.md.
- **Constraint:** (SEAM-DEV entries only) Invariant the dev simulation must
  satisfy.

## Evidence Levels

### L1: Test exists

The minimum evidence. The check verifies:

1. The file declared in **Integration test** exists on disk.
2. The file contains the `@pytest.mark.integration` marker (or a
   `pytestmark = [pytest.mark.integration]` module-level assignment).

L1 answers: "is there a test file tagged as an integration test?"

### L2: Test exercises both sides

Everything in L1, plus:

3. The test file contains an import from the **Producer** package.
4. The test file contains an import from the **Consumer** package.

The import check derives the Python package name from the directory path
by stripping any `src/` prefix and converting `/` to `.`. For example,
`src/venlink/iam/` becomes `venlink.iam`.

L2 answers: "does the test actually import code from both sides of the
boundary?"

### L3: Test uses real dependencies

Everything in L2, plus:

5. The test file contains the marker comment `# seam-evidence: L3-real`
   on a line by itself (not inline).
6. The test file does NOT mock or patch the declared producer or consumer
   packages. The check flags `mock.patch`, `@patch`, `MagicMock`, and
   `monkeypatch.setattr` calls that target the producer or consumer
   package names.

Mocking of unrelated modules is allowed. Only mocks targeting the declared
producer or consumer packages are flagged.

L3 answers: "does the test exercise the real data flow between producer
and consumer, without faking either side?"

## SEAM-DEV Entries

Entries with the `SEAM-DEV-NNN` prefix declare fixture fidelity seams:
where a dev simulation or test fixture is the producer and a real service
is the consumer. These entries support an additional **Constraint** field
that documents the invariant the dev simulation must satisfy.

SEAM-DEV entries follow the same evidence level checks as standard entries.
The Constraint field is informational and is not mechanically verified by
the check script.

## Progressive Adoption

1. **No SEAMS.md:** The check exits 0 with a warning. No enforcement.
2. **SEAMS.md with entries:** Only declared seams are enforced.
3. **Drift detection (future):** A `/drift` skill will scan for cross-
   boundary imports that lack seam declarations.

Projects are never blocked for not having a SEAMS.md. The manifest is
opt-in, and enforcement is per-declared-seam only.

## Verification

The `check-seam-evidence.sh` hook runs at verify phase (Stop event). It
parses SEAMS.md, checks evidence at the declared level for each seam, and
exits 0 (all pass) or 2 (any failure). Diagnostics are printed to stderr
naming the failing seam and the specific check that failed.

## Relationship to Other Standards

- **Testing standards (`testing-standards.md`):** Seam evidence uses the
  existing `@pytest.mark.integration` marker from Tier 2. No new markers
  are introduced.
- **Invariants (`invariants.md`):** SEAMS.md is a separate artifact from
  INVARIANTS.md. Both use the same machine-parseable markdown convention
  (H2 headings with structured fields) but serve different purposes.
- **Definition of Done (`definition-of-done.md`):** The seam evidence
  check adds "integration tests exist for declared seams" to the verify
  phase, complementing "all tests pass."
