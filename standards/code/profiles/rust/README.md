# rust profile

Per F020 ADR-F020-006 (adopt-not-author), etc adopts community-canonical
Rust references rather than authoring its own. The bindings in this
directory map the universal rules at `standards/code/{clean-code,
error-handling,import-discipline}.md` to specific Rust tooling and
idioms drawn from:

- [Rust API Guidelines](https://rust-lang.github.io/api-guidelines/) —
  the canonical Rust API design checklist, maintained by the Rust
  library team.
- [The Rust Book](https://doc.rust-lang.org/book/) — the canonical
  language reference, covering idiomatic style and error-handling
  patterns.
- [Clippy lints](https://rust-lang.github.io/rust-clippy/master/) —
  the canonical Rust linter; default-enabled lints form the
  enforcement floor.
- [Rust Style Team](https://github.com/rust-lang/style-team) — the
  team that maintains `rustfmt` defaults and formatting policy.

## Files

| File | Purpose |
|------|---------|
| `detection.yaml` | Markers (`Cargo.toml`) and globs (`*.rs`) for profile detection |
| `clean-code-bindings.md` | Universal clean-code rules → clippy lint mapping |
| `error-handling-bindings.md` | Universal error-handling → Result + thiserror/anyhow |
| `import-discipline-bindings.md` | `use` ordering and grouping (rustfmt + clippy) |
| `verify-green.sh` | Stop-hook gate: `cargo test` + `cargo clippy -- -D warnings` + `cargo fmt --check` |
| `check-test-exists.sh` | PreToolUse: `src/foo.rs` requires `#[cfg(test)]` block OR sibling `tests/` integration test |
| `check-code-quality.sh` | PreToolUse: fast block for empty function bodies, `unwrap()` outside test |

## What is enforced today

- **F020 dispatch**: `.rs` files route to this profile via `scripts/profile_loader.py`.
- **TDD gate**: `check-test-exists.sh` blocks edits to a non-test `src/*.rs`
  without a `#[cfg(test)]` block in the file itself OR a corresponding
  `tests/<module>.rs` integration test.
- **Code quality**: `check-code-quality.sh` blocks empty function bodies
  (CQ-RS-001) and `unwrap()` calls outside `#[cfg(test)]` modules
  (CQ-RS-002).
- **Verify green**: `cargo test --workspace` + `cargo clippy --workspace
  --all-targets -- -D warnings` + `cargo fmt --all -- --check`.
- **Skipped when tooling absent**: each step in `verify-green.sh` skips
  cleanly when `cargo` isn't on PATH (per F020 EC-007).

## What is NOT enforced today

The deeper Rust API Guidelines patterns (`AsRef` / `Into` conventions,
trait-object boundary placement, `Send + Sync` correctness on public
types) are advisory in the bindings but not machine-checked. Operators
can opt into stricter enforcement by enabling additional clippy lints
in their `Cargo.toml` `[lints.clippy]` block.
