# ADR-F021-003: Zero-tolerance contract (no delta, no exception flag)

**Date:** 2026-05-20
**Status:** Accepted

**Context:** Step 6c's per-wave gate must define when a wave fails. Two contract families are available: (a) delta-tolerance — `errors_after > errors_before` fails (grandfathers pre-existing debt); (b) zero-tolerance — `errors > 0` fails unconditionally (operator must clean up debt before `/build` will proceed). The user's stated intent: "going forward, we should never have them once this is installed."

**Decision:** Zero-tolerance, applied to type + lint + format errors via F020 profile dispatch (mypy + ruff + ruff-format for Python; tsc + eslint + prettier for TS; go vet + golangci-lint + gofmt for Go; clippy + rustfmt for Rust; whatever future profiles bind). Any non-zero `verify-green.sh` exit fails the wave; `phase-N/done` tag is NOT written. No `--legacy-baseline`, no `--allow-N-errors`, no per-project threshold tunable.

**Consequences:** *Positive:* structurally simple contract; no threshold drift; the philosophical anchor ("we never have errors once installed") holds by construction; no exception flag for operators to reach for under deadline pressure. *Negative:* adoption-day friction on projects with pre-existing debt — first `/build` against the redacted-project's 4323 mypy errors fails wave 0 immediately; operator must clean up before using `/build`. Documented as BR-005 (operator owns legacy cleanup).

**Alternatives considered:** Delta contract (rejected — grandfathers debt indefinitely). Hybrid (zero for lint/format, delta for types) rejected as adding complexity without principled justification. Opt-in `--legacy-baseline` flag rejected — would become the default escape, defeating the contract per the "low-friction-bypass-compounds" anti-pattern this PRD exists to prevent.
