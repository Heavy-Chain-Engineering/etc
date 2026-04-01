# TDD Workflow Standard

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer, Verifier

## The Red/Green/Refactor Cycle

Every code change follows this cycle without exception:

### 1. RED — Write a Failing Test

- Write a test that defines the expected behavior
- Run the test
- **Confirm it FAILS** — this step is non-negotiable
- If the test passes without implementation, the test is wrong (it validates nothing)

### 2. GREEN — Write Minimum Implementation

- Write the smallest amount of code that makes the test pass
- No extra functionality, no "while I'm here" additions
- Run the test
- Confirm it passes

### 3. REFACTOR — Clean Up

- Improve code structure without changing behavior
- Run all tests
- Confirm everything still passes

## Rules

1. **Never skip RED.** A test that passes without implementation is a test that tests nothing.
2. **Never write production code without a failing test.** The test defines what "correct" means.
3. **One behavior per test.** Each test should verify one specific behavior.
4. **Tests are documentation.** Test names describe system behavior: `should <behavior> when <condition>`.
5. **Minimum implementation.** Write only enough code to pass the current test. Resist the urge to anticipate.
6. **Run tests after every change.** Green means proceed. Red means stop and fix.
7. **Coverage threshold: 98% line and branch.** Enforced by hooks and CI. No exceptions without linked justification.

## Test File Convention

Every production file `src/<package>/<module>.py` must have a corresponding test file.
The hook `check-test-exists.sh` enforces this — edits to production code are blocked if no test file exists.

## What NOT to Do

- Do not write implementation first and tests after ("test-after" is not TDD)
- Do not skip running the failing test (you won't catch false positives)
- Do not write multiple features before running tests
- Do not use `# pragma: no cover` without a justification comment and linked issue
- Do not mock core business logic — only mock external I/O, system time, and randomness
