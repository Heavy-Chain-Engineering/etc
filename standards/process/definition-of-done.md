# Definition of Done

## Status: MANDATORY
## Applies to: All agents, Verifier (enforces)

A task is "done" when ALL of the following are true:

## Code
- [ ] Implementation matches the spec/PRD/acceptance criteria
- [ ] Code follows all standards in `~/.claude/standards/code/`
- [ ] No dead code, no commented-out code, no TODO without linked issue

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
