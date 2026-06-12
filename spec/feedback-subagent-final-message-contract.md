# Feedback Brief: Subagent Final-Message Contract

**Source:** 📬 Harness feedback block, 2026-06-11 (trigger: repeated-mistake).
Captured via /harness-feedback during the covr workspace-test acceptance run.
**Terminates in:** `standards/process/subagent-dispatch.md` (the gate this brief builds).

## Why

Agent-tool-dispatched subagents systematically complete their work, then stop on a
preamble line ("Now I'll grep…", "Let me run the suite.") instead of emitting their
final report/findings block. Field evidence (covr workspace-test, 2026-06-11): 14 of
~19 baseline-surveyor dispatches (final count) needed a SendMessage flush to produce their findings
YAML. Same-day etc build of F-2026-06-10: 6 of ~20 dispatches stalled identically
across five agent types (backend-developer, devops-engineer, code-reviewer,
security-reviewer, spec-enforcer). Each stall costs one conductor resume round-trip
plus a transcript re-read — ~17 wasted round-trips across two sessions.

The harness lacks any final-message contract: `standards/process/subagent-dispatch.md`
does not define one, no `agents/*.md` Response Format section carries one, and the
dispatch-prompt assembler's "Report back with…" prose is advisory. The decisive
contrast: every Workflow-tool dispatch with a structured-output JSON schema completed
cleanly (11/11 same session) — a forcing mechanism at the output boundary works;
prose report-back instructions stall ~30–40% of the time.

## Scope

1. **Standard:** add a "Final-Message Contract" section to
   `standards/process/subagent-dispatch.md` — the dispatched agent's FINAL message
   MUST be the report block itself, never a preamble; "if you catch yourself
   announcing a next step, perform the step instead of narrating it."
2. **Assembler:** `scripts/dispatch_prompt.py` appends the contract clause verbatim
   to every assembled prompt (a new fixed section, like the existing report-back
   footer it replaces/extends).
3. **Agent definitions:** every `agents/*.md` Response Format section gains the
   clause; a contract test greps all agent definitions for it (the
   `test_rule_vocabulary_purity`-style sweep pattern).
4. **Structured-output preference:** where the dispatch surface supports output
   schemas, skills SHOULD prefer them over prose report-backs; document the
   asymmetry evidence in the standard.
5. **Conductor recovery guidance:** one paragraph in the standard naming the
   SendMessage-flush recovery so conductors handle residual stalls uniformly
   (resume with "finish and deliver the report" rather than re-dispatching).

Out of scope: changing the Agent tool platform behavior itself; retrofitting
Workflow scripts (already clean).

## Value Hypothesis (stub — fill during /spec)

- who: etc conductors (build/init/review orchestration) in every project
- current_cost: ~30–40% of Agent-tool dispatches stall before final emission
  (17 observed round-trips across two sessions on 2026-06-11)
- predicted: stall rate on Agent-tool dispatches; decrease; threshold TBD at /spec
  (candidate: <5% over the next two feature builds); window_days TBD
- how_we_know: conductor counts resume-flush messages per build (verification.md
  deviation notes already record them)

## Cross-Reference

The canonical 📬 block is preserved in the session transcript of 2026-06-11
(session "etc") and summarized verbatim in the Why section above. Companion field
evidence lives in the covr workspace-test operator notes from the same date.

**Live validation (2026-06-12):** two extend-lane dispatches carrying the proposed
FINAL-MESSAGE CONTRACT clause completed 2-for-2 with zero stalls.
