# PRD: Hook Test Suite

## Summary

A comprehensive test suite that exercises and demonstrates all 8 command hook
scripts in the etc harness. Tests validate that each hook correctly blocks
dangerous/invalid operations and allows safe ones, with clear assertions and
descriptive test names.

## Scope

### In Scope
- Unit tests for all 8 command hook scripts in `hooks/`
- Test fixtures that create temporary directories, task files, and transcripts
- Both positive (should block) and negative (should allow) test cases
- Exit code verification (0 = allow, 2 = block)
- Stderr message verification (blocked operations should explain why)
- The compile-sdlc.py compiler: verify it produces correct output from the DSL

### Out of Scope
- Testing prompt/agent hooks (these require a live Claude session with LLM calls)
- Testing the install.sh script (shell-to-shell testing is fragile)
- Integration testing of the full /implement workflow

## Tech Stack
- Python 3.11+, pytest
- subprocess for invoking shell scripts
- tempfile for isolated test directories
- No external dependencies beyond pytest

## Module Structure

```
tests/
├── conftest.py              # Shared fixtures: temp dirs, task files, transcripts
├── test_block_dangerous.py  # block-dangerous-commands.sh
├── test_tdd_gate.py         # check-test-exists.sh
├── test_invariants.py       # check-invariants.sh
├── test_required_reading.py # check-required-reading.sh
├── test_config_changes.py   # block-config-changes.sh
├── test_inject_standards.py # inject-standards.sh
├── test_reinject_context.py # reinject-context.sh
├── test_mark_dirty.py       # mark-dirty.sh
└── test_compiler.py         # compile-sdlc.py
```

## Acceptance Criteria

1. Every command hook has at least 3 test cases (block, allow, edge case)
2. `test_block_dangerous.py` covers: rm -rf, force push, --no-verify, DROP TABLE,
   safe commands, safe rm targets (node_modules), git reset --hard
3. `test_tdd_gate.py` covers: src/ file with no test (block), src/ file with test
   (allow), non-src file (allow), __init__.py (allow), non-Python file (allow)
4. `test_required_reading.py` covers: no task dir (allow), no active task (allow),
   file not in scope (allow), required files not read (block), required files
   read (allow)
5. `test_config_changes.py` covers: project_settings (block), user_settings (block),
   policy_settings (allow), skills (block)
6. `test_inject_standards.py` verifies output contains: TDD section, code standards,
   active task injection, INVARIANTS.md injection
7. `test_reinject_context.py` verifies output contains: git log, dirty marker warning,
   reminder text
8. `test_mark_dirty.py` verifies: src/ file creates .tdd-dirty, non-src file does not
9. `test_compiler.py` verifies: DSL produces valid JSON, all 13 gates present, prompt
   hooks include role prefix, command hooks reference correct scripts
10. All tests pass with `pytest tests/ -v`
11. Tests use pytest fixtures for setup/teardown (no manual cleanup)
12. Test names follow convention: `test_should_<behavior>_when_<condition>`
