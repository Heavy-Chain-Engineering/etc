# rust — import-discipline bindings

Universal rules from `standards/code/import-discipline.md` mapped to Rust tooling.

| Universal rule | Rust tool / check | Notes |
|----------------|-------------------|-------|
| Imports grouped: std, third-party, local | `rustfmt` `group_imports = "StdExternalCrate"` (nightly) + hand-review on stable | Three groups: `std::*` first, then external crates, then `crate::*` / `super::*`. |
| No unused imports | `unused_imports` (compiler lint, default warn) | Always enforced. |
| Imports sorted within group | `rustfmt` `imports_granularity = "Module"` | Lexicographic sort within each block. |
| No circular imports | `cargo build` (compiler check) | Rust modules are a tree by construction; circular `use` is rejected. |
| No glob imports | `clippy::wildcard_imports` (allow-by-default; enable in lib crates) | `use foo::*;` is a smell except for prelude modules. |
| Module paths explicit | Hand-review + `clippy::module_name_repetitions` | Prefer `use foo::Bar;` over `foo::Bar::new()` qualified at every call site. |
| Explicit alias for ambiguous names | `use foo::Bar as FooBar;` | Aliasing only to disambiguate clashing type names. |

References:
- The Rust Book ch. 7 — https://doc.rust-lang.org/book/ch07-00-managing-growing-projects-with-packages-crates-and-modules.html
- rustfmt configuration — https://rust-lang.github.io/rustfmt/
- Clippy: wildcard_imports, module_name_repetitions — https://rust-lang.github.io/rust-clippy/master/
