# go profile

Per F020 ADR-F020-006 (adopt-not-author), etc adopts community-canonical
Go style guides rather than authoring its own. The bindings in this
directory map the universal rules at `standards/code/{clean-code,
error-handling,import-discipline}.md` to specific Go tooling and
idioms drawn from:

- [Effective Go](https://go.dev/doc/effective_go) — the canonical Go
  style and idiom reference, maintained by the Go team.
- [Google Go Style Guide](https://google.github.io/styleguide/go/) —
  Google's internal style guide, the most prescriptive of the public
  references.
- [Uber Go Style Guide](https://github.com/uber-go/guide/blob/master/style.md)
  — a widely-cited industry guide that fills gaps in the official docs.
- [golangci-lint](https://golangci-lint.run/usage/linters/) — the
  canonical Go linter aggregator; default-enabled checks form the
  enforcement floor.

## Files

| File | Purpose |
|------|---------|
| `detection.yaml` | Markers and globs for profile detection (F020 BR-003) |
| `clean-code-bindings.md` | Universal clean-code rules → golangci-lint linter mapping |
| `error-handling-bindings.md` | Universal error-handling rules → Go idiom mapping |
| `import-discipline-bindings.md` | Import order / grouping → goimports + golangci-lint |
| `verify-green.sh` | Stop-hook gate: `go test ./...` + `go vet` + `gofmt -l` + golangci-lint |
| `check-test-exists.sh` | PreToolUse: `foo.go` requires sibling `foo_test.go` |
| `check-code-quality.sh` | PreToolUse: fast block for obvious anti-patterns |

## What is enforced today

- **F020 dispatch**: `.go` files route to this profile via `scripts/profile_loader.py`.
- **TDD gate**: `check-test-exists.sh` blocks edits to a non-`_test.go`
  file under `cmd/`, `pkg/`, or `internal/` without a sibling
  `_test.go`.
- **Code quality**: `check-code-quality.sh` blocks obvious anti-patterns
  (empty function bodies; `panic()` outside `main`) at PreToolUse time;
  `golangci-lint` at Stop time provides the deeper sweep.
- **Verify green**: `go test ./...` + `go vet ./...` + `gofmt -l` (zero
  unformatted files) + `golangci-lint run` (when installed).
- **Skipped when tooling absent**: each step in `verify-green.sh` skips
  cleanly when its toolchain isn't available (per F020 EC-007 — go
  present but golangci-lint not installed is WARN, not ERROR).

## What is NOT enforced today

The deeper Effective Go conventions (interface segregation, package
naming, doc comments on exported identifiers) are captured in the
bindings as advisory guidance but not yet machine-checked. Operators
can opt into stricter enforcement by enabling the relevant
golangci-lint linters in their own `.golangci.yml`.
