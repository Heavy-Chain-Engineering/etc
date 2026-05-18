# go — clean-code bindings

Universal rules from `standards/code/clean-code.md` mapped to Go tooling.

| Universal rule | Go tool / check | Notes |
|----------------|-----------------|-------|
| Functions are small | `golangci-lint funlen` (default off; enable in `.golangci.yml`) | Effective Go: "Don't be afraid to make small functions." |
| Function arguments minimal | `golangci-lint maintidx` / `gocognit` | Style guides recommend ≤ 3 named params; pack into a struct beyond that. |
| Single responsibility per function | `gocognit` (default off) | Cyclomatic + cognitive complexity gates surface SRP drift. |
| Names express intent | `golangci-lint revive` (default on) | Replaces deprecated `golint`. |
| No magic numbers | `golangci-lint gomnd` (default off) | Effective Go favors named constants. |
| Exported identifiers documented | `golangci-lint revive` rule `exported` | Doc comment must start with the identifier name (Effective Go). |
| No dead code | `golangci-lint unused` / `deadcode` (default on) | Catches unused vars, fields, functions. |
| No unused variables | `go vet` (always on) | Compile error in Go for unused locals; vet catches unused params. |
| Cyclomatic complexity bounded | `golangci-lint cyclop` / `gocyclo` (default off) | Recommended ceiling: 10. |
| No empty function bodies | `check-code-quality.sh` (PreToolUse grep) + `golangci-lint nolintlint` | Empty bodies are typically a stub-leak. Interfaces and `_ = foo()` patterns are legit. |

References:
- Effective Go — https://go.dev/doc/effective_go
- Google Go Style — https://google.github.io/styleguide/go/decisions
- golangci-lint linter docs — https://golangci-lint.run/usage/linters/
