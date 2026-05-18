# go — import-discipline bindings

Universal rules from `standards/code/import-discipline.md` mapped to Go tooling.

| Universal rule | Go tool / check | Notes |
|----------------|-----------------|-------|
| Imports grouped: stdlib, third-party, local | `goimports` (or `gci`) | The canonical grouping: stdlib first, then third-party, then local; blank lines between. |
| No unused imports | `go vet` / `goimports` | Compile-time error in Go; never silently allowed. |
| No dot imports | `golangci-lint revive` rule `dot-imports` | Allowed only in `_test.go` for matchers (e.g. ginkgo). |
| Imports sorted within group | `goimports` | Lexicographic sort within each block. |
| No circular imports | `go build` / `go vet` | Compiler rejects import cycles. |
| Local vs stdlib explicit | `gci --custom-order` | `gci` adds first-party vs third-party split using module prefix. |
| No relative imports | Not allowed in modern Go | `import "../foo"` is illegal since Go modules. |
| Explicit alias for ambiguous names | Hand-review or `golangci-lint goimports` | Aliasing only to disambiguate clashing package names. |

References:
- Effective Go — Imports — https://go.dev/doc/effective_go
- goimports — https://pkg.go.dev/golang.org/x/tools/cmd/goimports
- gci — https://github.com/daixiang0/gci
- golangci-lint: goimports, gci, revive — https://golangci-lint.run/usage/linters/
