# PRD: Spec-Enforcer Hierarchical Breakdown for Large Specs

## Summary

The `/build` pipeline's Step 7 item 3 dispatches a single `spec-enforcer`
subagent to verify every acceptance criterion against the deliverables.
The agent operates under a hard 20-tool-call budget (agents/spec-enforcer.md
lines 41-46) plus a maxTurns=8 cap. On the F026 build (2026-05-22), a
13-AC spec exhausted this budget mid-verdict at AC-009 (a test-file-split
discrepancy that required deeper investigation), and the orchestrator
had to invoke SendMessage continuation to complete verification. Future
specs with 25+ ACs will outright fail this gate.

This feature adds hierarchical chunking to /build Step 7 item 3: when
the spec carries more than a threshold count of ACs, the conductor
dispatches `spec-enforcer` once per chunk of N ACs and aggregates the
verdicts with OR-semantics (any chunk NON-COMPLIANT → overall
NON-COMPLIANT). Specs at or below the threshold continue to use the
existing single-dispatch fast path with zero overhead.

The change is dispatch-layer orchestration only. The `spec-enforcer`
agent definition (`agents/spec-enforcer.md`) is unchanged — it still
receives one verification request per invocation and emits one
verdict. The chunk size and threshold are tunable module-level
constants in `skills/build/SKILL.md` so future operators can tune
empirically.

## Scope

### In Scope

- New `skills/build/SKILL.md` Step 7 item 3 logic that:
  1. Counts ACs in the spec.md being verified.
  2. If AC count ≤ `SPEC_ENFORCER_CHUNK_THRESHOLD` (default 10), uses
     the existing single-dispatch path.
  3. If AC count > threshold, partitions ACs into chunks of
     `SPEC_ENFORCER_CHUNK_SIZE` (default 6) and dispatches one
     spec-enforcer per chunk in parallel via N Agent-tool calls in a
     single turn.
  4. Aggregates per-chunk verdicts: any NON-COMPLIANT → overall
     NON-COMPLIANT; all COMPLIANT → overall COMPLIANT; any
     INSUFFICIENT_EVIDENCE → overall NON-COMPLIANT with remediation
     guidance per chunk.
- Two tunable constants documented as module-level constants near the
  top of Step 7's prose in `skills/build/SKILL.md`:
  - `SPEC_ENFORCER_CHUNK_THRESHOLD = 10`
  - `SPEC_ENFORCER_CHUNK_SIZE = 6`
- A helper script `scripts/spec_enforcer_chunker.py` that takes a
  spec.md path and emits the chunked AC partitions as JSON, so the
  conductor can construct N briefing prompts deterministically. The
  helper handles AC parsing (matching `^\d+\. \*\*AC-\d+` markdown
  numbering or `^### AC-\d+` heading shapes), chunk emission, and
  exposes a CLI surface `python3 scripts/spec_enforcer_chunker.py
  partition <spec_path> [--chunk-size N] [--threshold M]`.
- Tests covering: small-spec single-dispatch fast path; large-spec
  chunked path with multiple verdicts; aggregation semantics; AC
  parser correctness across the two shapes; chunk-size + threshold
  CLI overrides.
- A new ADR `docs/adrs/F-2026-05-22-spec-enforcer-hierarchical-breakdown-001-conductor-owned-chunking.md`
  documenting the conductor-owned-chunking decision (per GA-005).

### Out of Scope

- Cross-chunk AC consistency checks (e.g., catching contradictions
  between AC-3 and AC-7 when they land in different chunks). Explicit
  out-of-scope per GA-004; would re-introduce the context-budget
  problem this feature is designed to solve.
- Modifications to the `spec-enforcer` agent definition at
  `agents/spec-enforcer.md`. Agent stays simple; chunking is
  dispatch-layer.
- Retroactive re-verification of F001-F026 (those already shipped via
  the single-dispatch path; no need to re-verify).
- Generalizing the chunking pattern to other long-running subagent
  dispatches (e.g., spec-coupling-check, journey-lineage-check).
  Out-of-scope; future PRD candidate if the pattern proves valuable.
- /build Step 7.4 (journey lineage gate) and Step 7.5 (spec→ADR
  coupling gate). They have their own dispatch shapes and are not
  affected.

## Requirements

### BR-001: AC-count threshold gates the chunking path
The conductor counts ACs in `spec.md` (matching `^\d+\. \*\*AC-\d+\b`
markdown numbering OR `^### AC-\d+\b` heading shape). If the count is
≤ `SPEC_ENFORCER_CHUNK_THRESHOLD` (default 10), the existing single-
dispatch path is used unchanged. If the count is > threshold, the
chunked path is used. The threshold is exposed as a module-level
constant in `skills/build/SKILL.md`.

### BR-002: Chunk size is configurable
When chunking, ACs are partitioned into chunks of
`SPEC_ENFORCER_CHUNK_SIZE` (default 6). The last chunk may be smaller
than the chunk size (e.g., 13 ACs → 6 + 6 + 1). The chunk size is
exposed as a module-level constant in `skills/build/SKILL.md`.

### BR-003: Chunked dispatch is parallel
All N spec-enforcer dispatches in the chunked path fire in a single
turn (N Agent-tool calls in one orchestrator response), not serially.
Mirrors the existing /build Step 6a parallel-fan-out rule.

### BR-004: Per-chunk briefing prompts are deterministic
Each spec-enforcer dispatch receives a briefing prompt that includes:
- The spec.md path (always; for path-based grep)
- The chunk's AC list verbatim (so the agent doesn't waste tool calls
  re-parsing the spec for which ACs it owns)
- The same User-flow reachability-evidence clause from the current
  single-dispatch prompt (verbatim — preserves F001 contract)
- An instruction limiting verdict output to the chunk's ACs only

### BR-005: Verdict aggregation uses OR-semantics
Per-chunk verdicts are aggregated as follows:
- Overall verdict = COMPLIANT iff every chunk returned COMPLIANT.
- Any chunk returning NON-COMPLIANT → overall NON-COMPLIANT.
- Any chunk returning INSUFFICIENT_EVIDENCE → overall NON-COMPLIANT
  with the per-chunk INSUFFICIENT_EVIDENCE entries preserved in the
  aggregated remediation report.

### BR-006: AC-parser helper exposes a CLI
`scripts/spec_enforcer_chunker.py` provides a `partition` subcommand:
```
python3 scripts/spec_enforcer_chunker.py partition <spec_path> \
    [--chunk-size N] [--threshold M]
```
Emits JSON to stdout: `{"strategy": "single"|"chunked", "chunks":
[{"chunk_id": 0, "ac_numbers": [1,2,3,4,5,6], "ac_text": "..."}, ...]}`.
Strategy `"single"` is returned when AC count ≤ threshold; strategy
`"chunked"` is returned otherwise. CLI flags `--chunk-size` and
`--threshold` override the defaults for ad-hoc operator inspection.

### BR-007: Backward compatibility — small specs unchanged
For any spec with AC count ≤ threshold, the chunked path is NOT
invoked. The single-dispatch shape, briefing prompt, and verdict
shape match the current /build Step 7 item 3 byte-for-byte. F001-F026
re-verification (if ever needed) produces identical results.

### BR-008: Helper is sandbox-safe and argv-style
`scripts/spec_enforcer_chunker.py` uses Python stdlib only (re,
argparse, json, pathlib, sys). No shell-outs, no network calls, no
writes outside stdout. Designed for `subprocess.run` invocation from
the /build conductor.

## Acceptance Criteria

1. **AC-001 — Chunker CLI exists and parses spec.md.** Running
   `python3 scripts/spec_enforcer_chunker.py partition
   .etc_sdlc/features/shipped/F026-python-installer-rewrite/spec.md`
   emits valid JSON with `strategy: "chunked"` (F026 has 13 ACs > 10
   threshold) and 3 chunks of sizes 6, 6, 1.

2. **AC-002 — Single-dispatch fast path for small specs.** Running
   the CLI against a spec with ≤10 ACs emits
   `strategy: "single"` with one chunk containing all ACs. Verified
   against an F022 / F024 spec.md sample (both have ≤10 ACs).

3. **AC-003 — Chunk size + threshold CLI overrides honored.** Running
   `partition <spec> --chunk-size 4 --threshold 5` against an 8-AC
   spec emits `strategy: "chunked"` (8 > 5) with 2 chunks of sizes
   4 + 4.

4. **AC-004 — AC parser handles both markdown shapes.** The CLI
   correctly identifies ACs whether numbered `1. **AC-001 — ...` or
   headed `### AC-001 — ...`. Tested across both F026 (numbered) and
   F019 (heading-style) sample specs.

5. **AC-005 — skills/build/SKILL.md Step 7 item 3 documents the new
   logic.** The Step 7 item 3 prose in `skills/build/SKILL.md`
   explicitly describes: (a) the AC count step; (b) the
   threshold-gated branch; (c) the chunked dispatch shape (N parallel
   Agent calls); (d) the aggregation rules.

6. **AC-006 — Tunable constants documented inline.**
   `skills/build/SKILL.md` declares the two constants
   `SPEC_ENFORCER_CHUNK_THRESHOLD` and `SPEC_ENFORCER_CHUNK_SIZE`
   with their default values (10 and 6) and a one-line rationale for
   each value.

7. **AC-007 — Aggregation OR-semantics asserted in tests.** A test
   `tests/test_spec_enforcer_chunker.py::TestAggregation` covers all
   three cases: all COMPLIANT → COMPLIANT, any NON-COMPLIANT →
   NON-COMPLIANT, any INSUFFICIENT_EVIDENCE → NON-COMPLIANT.

8. **AC-008 — ADR for conductor-owned chunking exists.**
   `docs/adrs/F-2026-05-22-spec-enforcer-hierarchical-breakdown-001-conductor-owned-chunking.md`
   exists with Status: Accepted, Context, Decision, Consequences
   sections per `standards/architecture/adr-process.md`.

9. **AC-009 — Backward compat: F026 single-dispatch re-verification
   produces same verdict.** A regression test asserts that running
   the chunker against F026's spec with the chunked path produces a
   verdict shape identical (modulo per-chunk wrappers) to a single-
   dispatch invocation against the same spec.

10. **AC-010 — Full pytest + verify-green pass.** `python3 -m pytest
    --tb=short -q` and `verify-green.sh` both exit 0 after the
    feature ships.

## Edge Cases

1. **Spec with exactly threshold-count ACs (10 ACs).** Uses the
   single-dispatch path (≤ threshold is inclusive). Test asserts.

2. **Spec with threshold+1 ACs (11 ACs).** Uses the chunked path.
   Produces 2 chunks: one of size 6, one of size 5.

3. **Spec with chunk-size-multiple ACs (12 ACs at chunk size 6).**
   Produces exactly 2 equal chunks of 6.

4. **Spec with 1 AC.** Uses single-dispatch (trivially). CLI emits
   `strategy: "single"`, one chunk with one AC.

5. **Spec with 0 ACs.** CLI emits `strategy: "single"`, zero chunks.
   The Step 7 conductor's existing zero-AC handling (which already
   exists) is preserved; this feature does not add new behavior for
   the zero-AC case.

6. **Spec with malformed AC numbering** (e.g., `AC-3` skipping
   `AC-2`). CLI emits chunks based on the ACs it finds, in encounter
   order; does not raise. The downstream spec-enforcer agent reports
   any logical issues.

7. **CLI invoked without --chunk-size or --threshold flags.** Uses
   the SKILL.md default values (6 / 10). CLI prints the effective
   values it used to stderr for operator transparency.

8. **CLI invoked with --chunk-size 0 or --threshold 0.** Reject with
   `ValueError`; exit 1 with a one-line error to stderr. Documented
   in --help.

9. **Spec.md path does not exist.** CLI exits 1 with a one-line error
   to stderr mentioning the path.

10. **AC parsing finds zero ACs in a non-empty spec.** CLI emits
    `strategy: "single"` with zero chunks and prints a warning to
    stderr ("spec.md contained no recognizable AC markers; downstream
    spec-enforcer will produce a trivial verdict").

11. **Spec contains both numbered (`1. **AC-001**`) and heading
    (`### AC-001`) shapes.** CLI accepts both; deduplicates by AC
    number; emits chunks in encounter order.

12. **Per-chunk verdict missing from one spec-enforcer dispatch.**
    The conductor treats it as INSUFFICIENT_EVIDENCE for that
    chunk's ACs and aggregates per BR-005. Documented in
    skills/build/SKILL.md Step 7 item 3 prose.

13. **One chunk's spec-enforcer hits its tool budget mid-verdict.**
    The agent returns INSUFFICIENT_EVIDENCE per the existing agent
    contract (agents/spec-enforcer.md lines 38). The conductor
    aggregates per BR-005 — overall NON-COMPLIANT with remediation
    guidance.

14. **Spec with > 100 ACs.** Chunked path produces >16 chunks. The
    conductor dispatches all chunks in a single turn (parallel
    fan-out). No special handling for "extremely large" specs in v1;
    document as a future PRD candidate if real specs cross this
    threshold.
