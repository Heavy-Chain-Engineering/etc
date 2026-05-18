# rust — clean-code bindings

Universal rules from `standards/code/clean-code.md` mapped to Rust tooling.

| Universal rule | Rust tool / check | Notes |
|----------------|-------------------|-------|
| Functions are small | `clippy::too_many_lines` (allow-by-default) | Threshold configurable in `Cargo.toml`; recommended ceiling 100 lines. |
| Function arguments minimal | `clippy::too_many_arguments` (default warn) | Default threshold: 7. |
| Single responsibility | `clippy::cognitive_complexity` (allow-by-default) | Cognitive complexity > 25 is a smell. |
| Names express intent | `clippy::module_name_repetitions` (default warn) | Catches `module::ModuleType` redundancy. |
| No magic numbers | Hand-review (`clippy::approx_constant` for `PI`/`E` etc.) | Const definitions in the API Guidelines `C-CONST-NAMING`. |
| Public items documented | `clippy::missing_docs_in_private_items` (allow-by-default) + `#![warn(missing_docs)]` | API Guidelines `C-DOC-CRATE`. |
| No dead code | `dead_code` (compiler lint, default warn) | Always enforced by `cargo build`. |
| No unused variables | `unused_variables` (compiler lint, default warn) | `_` prefix is the explicit opt-out. |
| Cyclomatic complexity bounded | `clippy::cognitive_complexity` | See above. |
| No empty function bodies | `check-code-quality.sh` (PreToolUse grep) + `clippy::no_effect_underscore_binding` | Empty body is typically a stub-leak. Trait impls of `fn foo()` are legit. |
| No `unwrap()` outside tests | `clippy::unwrap_used` (allow-by-default) + `check-code-quality.sh` | API Guidelines `C-FAIL`. Tests OK. |

References:
- Rust API Guidelines — https://rust-lang.github.io/api-guidelines/
- Clippy lint docs — https://rust-lang.github.io/rust-clippy/master/
- The Rust Book, ch. 4 (Style) — https://doc.rust-lang.org/book/
