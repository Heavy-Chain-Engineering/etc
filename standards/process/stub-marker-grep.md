# Stub-Marker Grep Contract for spec-enforcer

## Status: MANDATORY
## Applies to: spec-enforcer

## The Problem

A spec-enforcer can return COMPLIANT on an acceptance criterion whose cited
evidence file contains a live stub marker — a `TODO(F005-013)`, an
`InlineComposerStub` placeholder component, or a `<div data-testid="composer-stub" />`
empty state — because the agent reads the AC, reads the evidence summary, and
trusts the cited line range without ever scanning the file for stub tokens.
This failure mode shipped in venlink-platform's F005 discussion-threads build
(2026-05-05): a live `TODO(F005-013)` plus a `composer-stub` empty state
passed through five gates (the implementer's TDD loop, code-reviewer,
verifier, security-reviewer, and three independent spec-enforcer dispatches),
and the bug was caught only when the user opened `localhost:5174` and clicked
the Reply button.

This standard defines the contract that closes the gap at verify time: after
spec-enforcer determines an AC is SATISFIED, a Step 2d post-pass greps each
cited evidence file against three rule classes — universal hard-fail
patterns, universal warning patterns, and a per-project hard-fail token list
— and downgrades the verdict to `INSUFFICIENT_EVIDENCE` on any unsuppressed
hit. The grep is the smallest mechanical gate that does not trust the layers
above it; it reads the file directly.

## Universal Hard-Fail Patterns

Per BR-002 of F007. Any match of the following case-sensitive Python regex
patterns in a cited evidence file (subject to the BR-005 tests-path skip
below) overrides the AC's SATISFIED verdict to `INSUFFICIENT_EVIDENCE`:

- `TODO\(F[0-9]+` — feature-id-prefixed TODO marker (e.g., `TODO(F005-013)`,
  `TODO(F007-001)`). The literal backslash-paren around `F[0-9]+` matches the
  opening parenthesis of the feature-id reference; the closing paren is
  unconstrained so abbreviated forms still match.
- `FIXME` — conventional code-comment marker for known-broken code paths.
- `XXX` — conventional code-comment marker for danger / incomplete sections.

Hard-fail patterns are case-sensitive. These are conventional code-comment
markers; lowercasing them creates false-positive risk on prose ("a fixme
button label", "the xxx-rated movie") and the harness deliberately treats
the conventional uppercase form as load-bearing.

## Universal Warning Patterns

Per BR-003 of F007. Any match of the following case-insensitive Python regex
patterns in a cited evidence file (subject to the BR-005 tests-path skip
below) downgrades the AC's SATISFIED verdict to `INSUFFICIENT_EVIDENCE` with
a "warning-class" evidence note distinguishing them from hard-fail hits:

- `stub\s+until\s+task\s+[0-9]+` — e.g., `stub until task 12`,
  `STUB UNTIL TASK 7`.
- `placeholder\s+until\s+task\s+[0-9]+` — e.g., `placeholder until task 4`.
- `until\s+task\s+[0-9]+\s+lands` — e.g., `until task 9 lands`,
  `Until Task 11 Lands`.

Warning matches signal probable but lower-confidence stubs: the prose form
is intentional ("we know this is a stub and we said so out loud"), but the
phrasing convention is softer than the conventional code-comment markers
above. Warning hits are a clear signal that a deliverable is incomplete; the
verdict still downgrades to `INSUFFICIENT_EVIDENCE`, and the operator opens
the file to confirm.

## Per-Project Token List

Per BR-004 of F007 (and GA-005 of the spec). spec-enforcer reads
`.etc_sdlc/stub-tokens.txt` if present and treats each non-blank,
non-`#`-prefixed line as an additional regex pattern. All entries act as
**hard-fail** — semantics identical to the universal BR-002 set; matches
override SATISFIED to `INSUFFICIENT_EVIDENCE`.

File format:

- One regex per line.
- Lines beginning with `#` are comments and skipped.
- Blank lines are skipped.
- Absent file → no extra patterns added.
- Empty file (only comments and blank lines) → no extra patterns added.

The harness regex set never grows; project-specific stub tokens live here.
This is where projects put tokens like:

```
# venlink-platform stub tokens (example)
composer-stub
InlineComposerStub
placeholder-component
```

The split keeps the universal set small and conventional, and lets each
project encode the names that signal stubs in its own codebase without
requiring a harness change.

## Tests-Path Skip

Per BR-005 of F007 (and GA-006 of the spec). Cited files whose paths contain
any of the following substrings are skipped entirely — no grep run, no hits
recorded — before any pattern matching:

- `tests/`
- `__tests__/`
- `.test.`
- `.spec.`

The skip set is fixed (not configurable in v1).

Rationale: stub markers are legitimate in test files. Mocks, fakes, test
fixtures, and spec scaffolding routinely contain `FIXME`-shaped scaffolding,
`composer-stub`-style intentional doubles, and `TODO(F<NNN>)`-formatted
test-only placeholders. Grepping them yields false positives that train
operators to ignore the gate. The skip applies before pattern matching so
the test-file false-positive case never reaches the verdict mapping below.

## Verdict Mapping

Per BR-006 of F007. The post-pass mutates only the SATISFIED → INSUFFICIENT_EVIDENCE
transition; verdicts NOT_SATISFIED, NOT_APPLICABLE, INSUFFICIENT_EVIDENCE,
and BLOCKED are not touched. The post-pass discipline guarantees Step 2d
only DOWNGRADES verdicts; it never promotes anything.

1. **Hard-fail hit** (universal BR-002 OR per-project BR-004): AC verdict
   becomes `INSUFFICIENT_EVIDENCE`. Evidence string format:
   `<file>:<line>: <quoted match>` prefixed with `stub-marker (hard-fail): `.
2. **Warning hit** (universal BR-003 only): AC verdict becomes
   `INSUFFICIENT_EVIDENCE`. Evidence string format:
   `<file>:<line>: <quoted match>` prefixed with `stub-marker (warning): `.
3. **Multiple hits in one file**: record the FIRST hit only. The operator
   opens the file to find the rest. Avoids verbose evidence strings while
   preserving the failure signal.
4. **Hard-fail and warning both present**: hard-fail wins. Its evidence is
   the recorded one; the warning is dropped.

## Security Constraints

Three rules are load-bearing for F007's threat model:

- **No automatic Read of cited files.** Step 2d uses `Grep` only — never
  `Read`. spec-enforcer records cited evidence paths verbatim but MUST NOT
  invoke `Read` on the artifact file itself. This prevents directory-traversal
  attacks via a hostile AC pointing the agent at `/etc/passwd`,
  `~/.aws/credentials`, or other sensitive files outside the project tree.
  Mirrors F002's `## Security Constraints` rule for manual-reachability
  artifact paths.

- **Control-character stripping on `.etc_sdlc/stub-tokens.txt` entries.**
  Each line read from the per-project token list is sanitized via the regex
  `[\x00-\x1f\x7f]` (the C0 control set plus DEL) before being compiled as
  a regex pattern. Mirrors F001's Phase 1 "Other" sanitization contract and
  F002's operator-name sanitization. Mitigates log-injection and
  CSV-injection attacks against downstream auditing tools that may parse
  the spec-enforcer JSON output.

- **Maximum 1024-character cap on each token-list entry.** Each line read
  from `.etc_sdlc/stub-tokens.txt` is truncated to 1024 characters before
  regex compilation. Bounds worst-case regex-compilation cost and protects
  against catastrophic backtracking from operator-supplied patterns. A
  truncation emits a stderr warning naming the affected line number; the
  truncated pattern is still loaded.

## Cross-References

- `standards/process/user-flow-completeness.md` — the F001+F002+F003
  user-flow completeness defense. Architectural sibling: same three-layer
  defense-in-depth shape (authorship + verify + dispatch) applied to a
  different failure mode (orphan user-facing surfaces vs. live stub
  markers).
- `agents/spec-enforcer.md` — the agent that enforces this contract via
  Step 2d, inserted between Step 2c (Reachability Recording Rules) and
  Step 3 (Emit JSON).
- `hooks/inject-standards.sh` — the SubagentStart hook that surfaces a
  one-section summary of this contract to every spawned subagent's
  onboarding context.
