# Subagent Dispatch — Prompt Construction Standard

<!-- forward-only: convention applies to dispatches authored from F024 onward -->

## Status: MANDATORY
## Applies to: any skill that dispatches subagents via the Agent tool (/build, /implement, /hotfix, /architect, /spec)

## Anchor

The orchestrator's job at dispatch time is to provide **the smallest sufficient context** for the subagent to do the right work the first time. Every line of the dispatch prompt must earn its place. Redundancy with the system overlay or the role manifest is waste: the subagent already has those.

The dispatch prompt is the **per-invocation delta** — what the subagent could not derive from its system overlay, its role manifest, or files it will Read on demand. Anything that fails this test belongs elsewhere (or nowhere).

## The Four Layers (no overlap)

The subagent receives four layers of context. The dispatch prompt is layer 3.

| Layer | Source | Carries | Lifetime |
|---|---|---|---|
| 1. System overlay | `hooks/inject-standards.sh` (SubagentStart) | Persistent discipline (TDD, diagnostic, sandbox, completion, code standards, git commit, research, user-flow, stub-marker) | Invariant across every dispatch |
| 2. Role manifest | `agents/<role>.md` body | Role identity, allowed tools, decision frameworks, antipatterns specific to the role | Invariant across every dispatch OF THAT ROLE |
| 3. Per-dispatch prompt | What the orchestrator writes per task | Feature intent, task intent, scope, ACs, cross-task hazards, expected report format | Unique per invocation |
| 4. `requires_reading` | Paths in the dispatch | Deep context the subagent fetches via Read on demand | Pulled, not pushed |

The dispatch prompt MUST NOT duplicate content from layers 1, 2, or 4.

## Required dispatch sections (in order)

1. **Feature intent** — one paragraph lifted from `spec.md`'s Summary section by the orchestrator. The user-visible WHY for the feature. Format: `**Feature intent (F<NNN>):** <problem class>. <what we're shipping>. <what changes for the system>.`

2. **Task intent** (optional) — one paragraph when the task's WHY differs from the feature WHY (standards docs, ADRs, integration tests, hand-off tasks). Omit when the task is an obvious sub-piece of the feature. Lifted from the task YAML's `intent:` field if present.

3. **Task identifier** — full path to the task YAML so the subagent can re-read it if needed.

4. **Required reading (in order)** — file paths with ≤8-word commentary each. Commentary names WHY the file is included (e.g., "F022 helper; mirror this pattern"), not WHAT the file contains (the subagent will Read).

5. **Files in scope** — paths the subagent may write/edit. One per line. No `(NEW)`/`(MODIFIED)` tags (the subagent will see the filesystem state).

6. **Acceptance criteria** — verbatim from the task YAML. Cross-reference BRs/ECs by ID prefix. Do NOT restate the AC in different words — that risks semantic drift between the YAML and the dispatch.

7. **Cross-task awareness** — what other agents are doing in this wave, file-set isolation guarantees, dependencies. This is the load-bearing per-dispatch content that NO other layer can carry.

8. **Report-back format** — bulleted list of facts to surface. Standardized across all dispatches:
   ```
   Report back with: (a) <pytest/verify output>; (b) <key artifact path or diff>;
   (c) <one architectural decision you made beyond the spec>; (d) <any gaps>.
   ```

## Forbidden in dispatch prompts

The dispatch prompt MUST NOT include:

- **TDD reminders** — already in system overlay's TDD section + role manifest's Development Cycle. Saying "write the failing test first" in the dispatch is pure redundancy.
- **"Dispatch hooks will enforce TDD, invariants, required reading, and phase gate — do not circumvent them"** — already in the system overlay (Process + TDD + Diagnostic sections).
- **Architectural constraints already documented in design.md** — the subagent has `design.md` in `requires_reading` and will pull it. Replace with one line: "See `design.md` §<Technical Constraints> for framework-version pins and security boundaries."
- **Tech stack reminders** — already in role manifest's Tech Stack section.
- **Pattern A/B usage rules** — system overlay's compressed User Interaction section already says "subagents escalate, don't invoke directly."
- **No-emoji / terse-voice reminders** — already in role manifest's Output Format section.
- **Generic "be careful" advice** — if it applies to every dispatch, it belongs in the system overlay or the role manifest.

## Anti-patterns (observed)

1. **Over-narration of required reading.** "scripts/active_to_shipped_mv.py — F022's helper pattern (use as architectural cousin for shutil.move semantics and three-branch failure shape)" should be "scripts/active_to_shipped_mv.py (F022 helper; mirror three-branch shape)."

2. **Inlining design.md content.** If the dispatch quotes design.md sections, the subagent ends up reading the same content twice (once in the dispatch, once when it Reads design.md). Cite the section path; do not inline.

3. **Restating ACs in narrative form** alongside the verbatim AC list. Pick one form (verbatim). Narrative drift causes the subagent to optimize for the narrative voice instead of the AC literal text.

4. **Including the "TDD discipline (red/green/refactor): 1. Write the failing test FIRST..." block.** Pure duplication. Drop entirely.

## Token budget

| Section | Target tokens |
|---|---|
| Feature intent | 50–100 |
| Task intent (when present) | 50–100 |
| Required reading list | ≤200 |
| Files in scope | ≤100 |
| Acceptance criteria | varies (the verbatim list) |
| Cross-task awareness | ≤150 |
| Report-back format | ≤80 |

**Total target: ≤1,000 tokens per dispatch prompt** for typical work. Larger only when the AC list itself is substantive.

Current measured baseline (pre-F024): ~1,400 tokens for substantial dispatches, ~600 tokens for simple dispatches. Post-F024 target: ~800 / ~400.

## Forward-only

This convention applies to dispatches authored from F024 onward. Earlier dispatches (F001–F023) are not retroactively re-authored. The orchestrator's dispatch shape evolves forward; legacy specs and tasks are not affected.

## Background

- F022 added the "intent gap" observation (per-dispatch carries WHAT but not WHY).
- The dispatch examples saved at `.etc_sdlc/incidents/2026-05-22-dispatch-examples/` informed this standard.
- This standard is the prose anchor; the actual prompt assembly is the orchestrator's job at /build Step 6a.
- Full dynamic prompt assembly is mechanized via `scripts/dispatch_prompt.py` (F-2026-05-23). See §Implementation below for the CLI invocation. The assembler embodies the eight required sections above; section ordering is embedded in code per ADR-Ftmp-19e49f7c-002 with this doc as the canonical rationale source.

## Implementation

The canonical implementation lives at `scripts/dispatch_prompt.py`. Invocation:

```bash
python3 ~/.claude/scripts/dispatch_prompt.py assemble \
    --feature-path <path> --task-id <id>
```

The CLI emits the assembled dispatch prompt on stdout. Token-budget
warnings (per §Token budget) emit to stderr without affecting stdout.
Two ADRs document load-bearing design decisions:

- `docs/adrs/Ftmp-19e49f7c-001-cite-design-md-not-inline.md` — design.md is referenced via `requires_reading`, never inlined.
- `docs/adrs/Ftmp-19e49f7c-002-embed-section-ordering-in-code.md` — section ordering is embedded in the script with this doc as the rationale source.

`skills/build/SKILL.md` Step 6a invokes the assembler. Forward-only:
applies to dispatches authored from the F-2026-05-23 release tag
onward. F001-F024 dispatches are not retroactively re-authored.

## Anti-pattern catalog

- **Belt-and-braces TDD reminders** — agents read the system overlay before reading the dispatch. Restating TDD in the dispatch is noise, not safety.
- **Cargo-cult "do not circumvent the hooks"** — the hooks circumvent themselves. Restating their authority in dispatch prose adds nothing.
- **Inline-everything dispatches** — if the dispatch needs 3000+ tokens, the orchestrator is treating the dispatch as a context dump. Cite paths; the agent has Read.
