# Dispatch Example 2 — technical-writer (simple ADR)

**Source:** /build F023 Wave 0 task 003 — "docs/adrs/F023-001-temp-id-format.md NEW"
**Dispatched:** 2026-05-21 ~14:30 UTC (parallel with example 1)
**Result:** Completed; 21-line ADR; 5 standard sections present; 4 alternatives discussed.

---

## Section A — System overlay (from `hooks/inject-standards.sh`)

**Identical to example 1.** Same ~1,600 tokens. The system overlay is invariant across every dispatch under the etc harness, regardless of role.

(See `example-1-backend-developer-substantial.md` for the verbatim text.)

---

## Section B — Role manifest (`agents/technical-writer.md`)

This is the persistent identity for technical-writer. Same for every technical-writer dispatch — but different from backend-developer's manifest.

```markdown
---
name: technical-writer
description: >
  Clear, concise, audience-aware documentation specialist. Docs-as-code practitioner.
  Writes and maintains API docstrings, architecture overviews, setup guides, READMEs,
  and .meta/ descriptions. Use when documentation is missing, stale, or needs to be
  created for new features. Do NOT use for writing code or modifying tests.

  <example>
  Context: A new module has been implemented but has no documentation.
  user: "The payments module is done but has no docs yet."
  assistant: "I'll use the technical-writer agent to inventory what exists, create API docstrings, a .meta/description.md, and update the README."
  <commentary>New code without docs is the core trigger for technical-writer.</commentary>
  </example>

  <example>
  Context: A developer changed an API but the docs still describe the old behavior.
  user: "We refactored the auth endpoints last sprint but the docs are outdated."
  assistant: "I'll use the technical-writer agent to detect stale docs and update them to match the current code."
  <commentary>Stale-doc detection and correction is a technical-writer responsibility.</commentary>
  </example>
tools: Read, Edit, Write, Grep, Glob
model: opus
maxTurns: 30
---

You are a Technical Writer -- clear, concise, audience-aware. Docs-as-code. If it is not documented, it does not exist.

[... full Before-Starting, Responsibilities, Process, Templates, .meta/ format, Quality Criteria, Output Format, Boundaries, Error Recovery, Coordination sections — 121 lines total ...]
```

**~121 lines, ~1,300 tokens. Invariant across every technical-writer dispatch.**

Notable differences from backend-developer's manifest:
- Allowed tools: no `Bash` (no shell access; doc work doesn't need it)
- `maxTurns: 30` (vs backend-developer's 50; doc tasks should converge faster)
- No TDD content (the role doesn't write tests)
- Different antipatterns + decision frameworks (audience-aware writing rules instead of async-vs-sync, ORM-vs-raw-SQL, etc.)

(The full file lives at `agents/technical-writer.md`; truncated above for readability.)

---

## Section C — Per-dispatch prompt

This is what the orchestrator wrote for THIS specific task. Notice it's about 1/4 the size of example 1's dispatch — the task is genuinely smaller (one file, structured template, no TDD cycle).

```
You are dispatched by /build (F023 Wave 0) to write ADR-F023-001.

**Task YAML:** `.etc_sdlc/features/active/F023-distributed-id-allocation-discipline/tasks/003-docs-adrs-f023-001-temp-id-format-md-new.yaml`

**Required reading (in order):**
1. `.etc_sdlc/features/active/F023-distributed-id-allocation-discipline/spec.md` — BR-001, EC-001, EC-009
2. `.etc_sdlc/features/active/F023-distributed-id-allocation-discipline/design.md` — Data Model Entity 1 + Trade-off #1
3. `standards/architecture/adr-process.md` — canonical ADR template + section ordering
4. `docs/adrs/F021-001-structural-not-phrase-grep.md` — closest stylistic cousin (size, prose density)

**Files in scope:**
- `docs/adrs/F023-001-temp-id-format.md` (NEW, one page)

**Acceptance criteria (4 ACs):**

1. **ADR-F023-001 documents the decision:** Branch-local temp F-ID format is `Ftmp-<8-char-hex>` derived from `secrets.token_hex(4)`. One page per `standards/architecture/adr-process.md`.

2. **Trade-off recorded:** 4 bytes of entropy chosen as the smallest size that's operationally collision-free for the use case. Birthday-problem 50% collision at ~65k allocations; operational rate is single-digit allocations per developer per week; collision-free in practice.

3. **`Ftmp-` prefix cited as deliberately greppable** for `/metrics` + audit tooling. Make distinct from `F<NNN>` sequential form.

4. **Standard ADR sections present:** Status, Context, Decision, Consequences, Alternatives Considered. Status: Accepted.

**Alternatives to discuss in the ADR:**
- **Pure UUID (`Ftmp-01HGW3K7VQXJB...`):** rejected — overkill entropy; loses readability; doesn't sort cleanly.
- **Shorter hex (4 chars = 2 bytes):** rejected — birthday-problem 50% at ~256 allocations; not collision-free at any plausible operational scale.
- **Longer hex (16 chars = 8 bytes):** rejected — gains no operational value; loses terseness in tags and dir names.
- **Hashids-style (`Ftmp-jVbXa`):** rejected — extra dependency; no entropy benefit.

**Architectural constraints:**
- One page. No emoji. Match the voice of `docs/adrs/F021-001-structural-not-phrase-grep.md`.
- Standard ADR template — no freelancing the structure.

**Dispatch hooks will enforce TDD, invariants, required reading, and phase gate — do not circumvent them.**

Report back with: (a) `ls -la docs/adrs/F023-001-temp-id-format.md`; (b) `wc -l`; (c) confirmation all 5 standard ADR sections are present.
```

**~70 lines, ~600 tokens. Unique to this task.**

---

## Section D — `requires_reading` (escape valve)

Files the agent then Read (per the dispatch's required-reading list):

1. `.etc_sdlc/features/active/F023-distributed-id-allocation-discipline/spec.md` (~6,000 tokens)
2. `.etc_sdlc/features/active/F023-distributed-id-allocation-discipline/design.md` (~3,750 tokens)
3. `standards/architecture/adr-process.md` (~600 tokens)
4. `docs/adrs/F021-001-structural-not-phrase-grep.md` (~250 tokens — it's a short ADR by design)

**Total agent context after pulls:** ~3,500 tokens (dispatch) + ~10,600 tokens (required reading) = ~14,100 tokens of pre-work context.

About 30% less context than example 1's backend-developer dispatch — appropriate for a simpler task.

---

## Observations

1. **Smaller task → smaller per-dispatch prompt → smaller required-reading pull.** The orchestrator naturally scaled context downward for the simpler task. No template forced extra ceremony.

2. **The "Alternatives to discuss" section is the load-bearing per-dispatch content.** The system overlay has nothing about ADRs; the role manifest has the doc-writing voice but nothing about ADR-specific structure. The dispatch had to provide the rejection rationale list because no other layer could supply it.

3. **The `docs/adrs/F021-001-structural-not-phrase-grep.md` "closest stylistic cousin" reference was the second load-bearing item.** Naming an existing artifact as a stylistic exemplar gave the agent a concrete shape to mirror. Cheaper than describing the voice in prose.

4. **Cross-task awareness was minimal** (just "tasks 002-009 running in parallel") — appropriate because this task's file is genuinely independent of the others. Compare to example 1's longer cross-task note about feature_id.py being un-touched by parallel tasks.

5. **The redundant TDD-reminder line still appears** ("Dispatch hooks will enforce TDD, invariants, required reading, and phase gate — do not circumvent them.") even though this is a documentation task and TDD doesn't strictly apply. Same minor impurity as example 1; should be trimmed in future polish.
