# Definition of Done

## Status: MANDATORY
## Applies to: All agents, Verifier (enforces)

A task is "done" when ALL of the following are true:

## Code
- [ ] Implementation matches the spec/PRD/acceptance criteria
- [ ] Code follows all standards in `~/.claude/standards/code/`
- [ ] No dead code, no commented-out code, no TODO without linked issue
- [ ] Existing components, modules, and patterns surveyed before adding
      new ones. A new sibling is justified only when no existing one can
      be composed, extended, or have its props/scope widened to fit. The
      check is mechanical: read the relevant directory listing, name
      what was considered, name why each candidate was rejected. "I
      didn't see one" is not acceptable — the spec is the requirement,
      the existing tree is the constraint.

## Tests
- [ ] Tests written FIRST (red/green TDD workflow followed)
- [ ] All tests pass
- [ ] Coverage >= 98% line and branch (enforced by hook + CI)
- [ ] Coverage did not decrease from baseline
- [ ] Test names follow `should <behavior> when <condition>` convention

## Quality
- [ ] mypy strict passes with zero errors
- [ ] Linter passes with zero warnings
- [ ] Code reviewed against standards (Code Reviewer approved)
- [ ] Security review passed (no OWASP Top 10 violations)
- [ ] No secrets in source code

## Documentation
- [ ] `.meta/description.md` updated if module purpose changed
- [ ] API docstrings on all public interfaces
- [ ] ADR written if architectural decision was made

## Integration
- [ ] Changes are backward-compatible OR all references updated
- [ ] CI pipeline passes all stages
- [ ] For backend schema or new-endpoint changes: hit the running stack
      and assert 2xx (curl, browser load, equivalent). A green test suite
      is not sufficient — test runs typically build state from scratch
      and never see the long-lived dev environment, so migration drift
      and config drift go undetected until a human opens the page.
