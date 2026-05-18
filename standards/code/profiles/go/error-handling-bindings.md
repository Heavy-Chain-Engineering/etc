# go — error-handling bindings

Universal rules from `standards/code/error-handling.md` mapped to Go idioms.

| Universal rule | Go idiom / tool | Notes |
|----------------|-----------------|-------|
| Failures surface early | `if err != nil { return ... }` immediately after the call | Effective Go: "Indent error flow." |
| Errors are checked, not ignored | `golangci-lint errcheck` (default on) | Detects discarded `err` values. |
| Context preserved in error chain | `fmt.Errorf("doing X: %w", err)` (Go 1.13+) | `%w` chains errors for `errors.Is` / `errors.As` traversal. |
| No swallowing | `golangci-lint errcheck` + `golangci-lint nilerr` (default on) | Forbids `_ = …` on error returns and "return nil; err != nil". |
| Panics are exceptional | `golangci-lint gocritic` (rule `exitAfterDefer`) | Panic should be recoverable bug-state, not control flow. Use `errors.New`. |
| No bare `panic()` in library code | `check-code-quality.sh` (PreToolUse grep outside `main`) | Library packages should return errors; main may exit. |
| Wrapped errors discriminate | `errors.Is(err, target)` / `errors.As(err, &t)` | Replace string-comparison-on-error with sentinel + Is/As. |
| No silent goroutine error loss | Hand-review (no good linter) | Goroutines must report errors through a channel or shared structure. |
| Error messages don't leak secrets | Hand-review | Same constraint as Python/TS; no machine-check. |

References:
- Effective Go — Errors section — https://go.dev/doc/effective_go#errors
- Go blog: Error handling and Go — https://go.dev/blog/error-handling-and-go
- Go blog: Working with Errors in Go 1.13 — https://go.dev/blog/go1.13-errors
- golangci-lint: errcheck, nilerr, errorlint — https://golangci-lint.run/usage/linters/
