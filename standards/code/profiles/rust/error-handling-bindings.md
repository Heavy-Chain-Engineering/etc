# rust — error-handling bindings

Universal rules from `standards/code/error-handling.md` mapped to Rust idioms.

| Universal rule | Rust idiom / tool | Notes |
|----------------|-------------------|-------|
| Failures surface early | `?` operator with `Result<T, E>` | The Rust Book ch. 9. |
| Errors are checked, not ignored | `#[must_use]` on `Result` (compiler lint, default warn) + `clippy::unused_result_ok` | Compiler emits a warning on discarded `Result`. |
| Context preserved in error chain | `anyhow::Context::context()` / `Error::source()` | `anyhow` for application code; `thiserror` for library code per API Guidelines. |
| No swallowing | `clippy::let_underscore_drop` + `clippy::let_underscore_must_use` | Forbids `let _ = …` on `Result`. |
| Panics are exceptional | `clippy::panic_in_result_fn` (default warn) | `panic!` in a Result-returning function is almost always a bug. |
| No `unwrap()` / `expect()` in library code | `clippy::unwrap_used` + `clippy::expect_used` (both allow-by-default; enable in lib crates) | API Guidelines `C-FAIL`. Tests may use unwrap. |
| Wrapped errors discriminate | `thiserror::Error` enum + `#[from]` conversions | Library convention; matches `?` propagation. |
| No silent thread/async error loss | `JoinHandle::join()` returns `Result`; spawned futures must report through channel/Result | Hand-review; clippy has no general check. |
| Error messages don't leak secrets | Hand-review | Same constraint as other languages. |

References:
- The Rust Book ch. 9 — https://doc.rust-lang.org/book/ch09-00-error-handling.html
- Rust API Guidelines `C-FAIL` — https://rust-lang.github.io/api-guidelines/dependability.html#functions-validate-their-arguments-c-validate
- Clippy: unwrap_used, expect_used, panic_in_result_fn — https://rust-lang.github.io/rust-clippy/master/
- thiserror — https://docs.rs/thiserror
- anyhow — https://docs.rs/anyhow
