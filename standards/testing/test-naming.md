# Test Naming Convention

## Status: MANDATORY
## Applies to: Backend Developer, Frontend Developer, Code Reviewer

## Pattern

```
test_should_<expected_behavior>_when_<condition>
```

## Examples

Good:
- `test_should_return_applicable_status_when_product_matches_drnsg`
- `test_should_raise_validation_error_when_chunk_size_is_negative`
- `test_should_return_empty_list_when_no_documents_match_query`
- `test_should_preserve_legal_hierarchy_when_ingesting_regulation`

Bad:
- `test_query` (what about it?)
- `test_chunking_works` (what does "works" mean?)
- `test_error_handling` (which error? which handling?)
- `test_1` / `test_case_a` (meaningless)

## Rules
- Test name must describe the expected behavior AND the condition
  - **Enforce:** none / **Fallback:** required-reading
- Use domain language in test names (not implementation language)
- One assertion per test (or closely related assertions on the same behavior)
  - **Enforce:** none / **Fallback:** required-reading
- Test file names mirror production file names: `test_<module>.py`
