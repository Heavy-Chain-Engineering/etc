---
name: rule-sweep
description: In-flight architecture-rule capture and sweep. A human states a rule mid-build; the rule lands in the machine baseline, the repo is swept for violations and fixed via file-isolated agents, and the rule joins the conformance checker so it is enforced going forward. Use when you notice an architectural rule the codebase should follow but does not yet enforce.
---

# /rule-sweep — In-Flight Rule Capture + Sweep Loop

You are the rule-sweep conductor. A human has stated an architectural rule mid-build. Your job is to capture that rule (sanitized), record it in the machine baseline with provenance, sweep the repo for violations, dispatch file-isolated fix agents to repair what is mechanically safe to repair, report files-changed AND violations-remaining honestly, and re-run the conformance checker so the rule is enforced going forward — never again as prose in someone's memory.

This skill is the in-flight arm of `standards/process/lessons-terminate-in-gates.md`: a lesson stated mid-build must terminate in a live gate, not a sticky note. The whole point is that the rule the human just stated becomes machine-enforced before the session ends.

## Response Format (Verbosity)

Terse and structured. Use fenced code blocks for the `baseline.py` / `baseline-verify.sh` invocations and the dispatcher JSON, Pattern B visual markers for the capture prompt and status announcements, and tables/lists for the Phase 4 report. Prose to the operator is limited to: (a) phase-entry announcements, (b) the missing-baseline branch, (c) the Phase 4 report, (d) the Phase 5 confirmation. No preamble ("I'll...", "Here is..."). No narrative summary. No emoji. Max 250 words per response unless rendering the Phase 4 report (max 800 words). When a fix agent returns, summarize its result in <= 3 lines; do not echo its full output.

## Subagent Dispatch (Non-Negotiable)

The conductor (you) NEVER edits production files itself. All fix work is dispatched to subagents via the Agent tool, in file-isolated batches, mirroring `/build`'s dispatch discipline. Your own allowed in-context actions are: (a) reading state via Read/Grep/Glob/Bash, (b) running `baseline.py` and `baseline-verify.sh` via Bash, (c) the Pattern B capture prompt and the AskUserQuestion pickers, (d) rendering the Phase 4 report and Phase 5 confirmation, (e) summarizing each fix agent's result. If you catch yourself opening a production source file with Edit or Write, stop and hand the work to a dispatched agent.

## Before Starting (Non-Negotiable)

Read these files in order before any phase action, using the Read tool on each exact path:

1. `standards/process/interactive-user-input.md` — Pattern A (`AskUserQuestion`) and Pattern B (visual marker). The rule-statement capture in Phase 1 is Pattern B; the mechanizable / bootstrap decisions are Pattern A.
2. `standards/process/lessons-terminate-in-gates.md` — the loop this skill closes in-flight (rule → baseline → sweep → live checker).
3. `standards/process/subagent-dispatch.md` — the dispatch-prompt construction rules for the Phase 3 fix agents.
4. `docs/adrs/F-2026-06-10-brownfield-architecture-baseline-004-native-tool-first-conformance.md` — the conformance model: rules a checker can express are mechanizable; generated checkers are read-only; the conductor owns gate semantics.

If `standards/process/interactive-user-input.md` is missing, STOP and report it — every capture prompt depends on it. If the other reads are missing, list them in your report and proceed with the conservative defaults documented inline below.

## Usage

```
/rule-sweep "DTOs live in libs/contracts; runtime logic never does"
/rule-sweep "files matching libs/**/*.ts must not contain process.env"
/rule-sweep
```

The rule statement is optional on the command line. If absent, Phase 1 captures it via the Pattern B marker. If present, Phase 1 still confirms and sanitizes it.

## Preflight: Locate the Baseline (Missing-Baseline Handling)

Before Phase 1, resolve the repo root and check the baseline status. The skill must NOT crash when no baseline exists.

```
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
TOKEN="$(python3 ~/.claude/scripts/baseline.py status "$REPO_ROOT")"
```

Branch on the TOKEN, never the exit code (the `baseline.py status` contract — callers branch on the token):

- **`ratified` or `unratified`** — a baseline exists. Proceed to Phase 1. (Rules accrete onto a ratified baseline without reopening ratification, per ADR-004; rules also append to an unratified one.)
- **`missing`** — no baseline file. Do NOT crash. Offer two bootstrap paths via `AskUserQuestion` (Pattern A):
  1. **Run `/init-project --phase=baseline` first (Recommended)** — discover, verify, and ratify the repo's real patterns, then re-run `/rule-sweep`. This is the right path when the repo has never been onboarded.
  2. **Record the rule in a minimal baseline now** — create an unratified baseline from an empty discover JSON via `baseline.py init`, then continue. Use when the operator wants the rule captured immediately and will ratify later:
     ```
     printf '{"inventory":[],"claims":[],"exemplars":[],"do_not_copy":[],"rules":[],"seams":[],"confidence":{"score":"low","inputs":{}}}' > "$TMPDIR/rule-sweep-discover.json"
     python3 ~/.claude/scripts/baseline.py init "$REPO_ROOT" --from "$TMPDIR/rule-sweep-discover.json"
     ```
  On choice 1, exit after pointing at `/init-project --phase=baseline`. On choice 2, proceed to Phase 1 against the just-created baseline.
- **`malformed`**, or `baseline.py status` exits 1 (IO error) — STOP as an infrastructure failure. A corrupt baseline is never treated as writable. Report the path and suggest `baseline.py validate` for the field-level error.

The baseline path is `$REPO_ROOT/.etc_sdlc/architecture-baseline.yaml`; bind it to `BASELINE` for the phases below.

## Workflow

### Phase 1: Capture the Rule (sanitized at the capture site)

Capture three things: the rule **statement**, **who** stated it, and the **trigger** (what mid-build observation prompted it). The `when` is the current UTC date — `baseline.py` records it automatically; you do not pass it.

**Statement.** If the operator supplied it on the command line, echo it back for confirmation; otherwise capture it via the Pattern B marker:

```

---

**▶ Your answer needed:** State the architectural rule, one sentence. If you want it auto-enforced, phrase it as `files matching <GLOB> must not contain <NEEDLE>` or `directory <DIR> must not contain <GLOB> files`.

```

**Sanitize at the capture site (untrusted input).** A rule statement is operator- or doc-derived free-form text and is untrusted. Strip control characters (`[\x00-\x1f\x7f]`) and length-cap (512 chars for the statement, 64 for `who`) BEFORE it leaves your context and BEFORE it is passed to `append-rule`. Do not pass raw operator text downstream. (`baseline.py` sanitizes again at write time — defense in depth — but the capture site is the first line.)

**Who.** Default `who` to the operator identity from the environment; confirm or override via the marker if ambiguous.

**Trigger.** Capture a short `trigger` string (e.g. "noticed during wave 2 of F-... that two libs import env directly").

**Mechanizable suggestion (against the v1 grammar).** Judge whether the sanitized statement fits the v1 python-profile grammar — the only two shapes the conformance checker mechanizes today:

- **(A)** `files matching <GLOB> must not contain <NEEDLE>`
- **(B)** `directory <DIR> must not contain <GLOB> files`

If the statement matches (A) or (B), suggest `mechanizable: true` (it will graduate into `baseline-verify`). If it is richer than the grammar — a structural/semantic rule like "DTOs live in libs/contracts" — suggest `mechanizable: false`: the dispatcher will return `no-check` for it and the sweep falls back to a grep/Glob survey + human judgment. Surface the suggestion with the reason, and let the operator confirm or flip it via `AskUserQuestion` (Pattern A) — the operator may know a native fitness-function tool can express it even when the v1 bash grammar cannot.

### Phase 2: Append the Rule to the Baseline

Record the rule via the CLI (the single owner of the baseline format). The `~/.claude/scripts/baseline.py` prefix is load-bearing — the Codex path-rewrite depends on it verbatim. Pass `--mechanizable` only when Phase 1 resolved the flag to true:

```
python3 ~/.claude/scripts/baseline.py append-rule "$BASELINE" \
  --statement "<sanitized statement>" \
  --who "<sanitized who>" \
  --trigger "<sanitized trigger>" \
  [--mechanizable]
```

`append-rule` is atomic, works on ratified baselines (it does NOT reopen ratification — rules accrete), and prints the new rule id `R-NNN` on stdout. **Capture that `R-NNN`** — it scopes the Phase 3 mechanizable sweep to the rule just captured, not the whole baseline. If `append-rule` exits non-zero, STOP and surface stderr; do not proceed to a sweep against a rule that was not recorded.

### Phase 3: Sweep for Violations + Dispatch File-Isolated Fix Agents

Find violations, then dispatch fixes. The split depends on the mechanizable flag.

**3a. Find violations.**

- **Mechanizable rule** — run the conformance dispatcher scoped to the new rule id. Pipe the documented JSON contract `{repo_root, rule_ids, cwd}` on stdin; pass the new id (not `null`) in `rule_ids` so only the just-captured rule is swept:
  ```
  printf '{"repo_root":"%s","rule_ids":["R-NNN"],"cwd":"%s"}' "$REPO_ROOT" "$PWD" \
    | bash hooks/baseline-verify.sh
  ```
  Read verdicts from the `results` JSON, never the exit code (the dispatcher always exits 0). Each `results[]` entry is `{rule_id, status: pass|fail|no-check, evidence}`; a `fail` names the offending file in its `evidence`. A `no-check` means the statement did not match the v1 grammar after all — fall through to the survey path. A warn-and-skip (empty `results`, stderr WARN) means no python profile / no usable baseline; record it as a skipped sweep in Phase 4, never as "clean."
- **Non-mechanizable rule** — the dispatcher returns `no-check`, so survey by hand. Use Grep/Glob to enumerate candidate violations against the rule's intent (e.g. for "DTOs live in libs/contracts", Glob the DTO definitions and Grep for runtime-logic imports outside `libs/contracts`). This survey is best-effort and human-judgment-bounded; its coverage is reported honestly in Phase 4.

**3b. Dispatch fix agents in file-isolated batches.** Group the violating files so no two agents touch the same file (file-set isolation, not branch isolation), then dispatch one Agent-tool invocation per batch via the **Agent tool**, following `standards/process/subagent-dispatch.md`. The conductor never edits production files itself — this mirrors `/build`'s file-isolated parallel dispatch. Each dispatch prompt names: the rule statement and its `R-NNN`, the exact files in that batch (and ONLY those), the violation evidence per file, and the instruction to fix the violation through normal **hooked Edit/Write** with all existing gates active.

**Never bypass hooks.** Fixes go through the normal hooked Edit/Write path — every existing gate (tests, schema guards, safety guardrails) fires on each fix exactly as in a normal build. This skill does NOT add a bypass and MUST NOT disable any hook. Generated checkers are read-only analyzers; only the dispatched fix agents mutate the tree, and only through hooked writes.

**Never force-fix behavior-changing rewrites.** A violation whose only repair would change runtime behavior — not a mechanical move/rename but a semantic rewrite — is NEVER force-fixed. The fix agent leaves it untouched and reports it back; you list it in Phase 4 as a remaining violation WITH the reason "behavior-changing rewrite — needs human design". The same applies to any file an agent declines because the safe fix is ambiguous. Mechanical, behavior-preserving fixes proceed; behavior-changing ones stop at the report.

### Phase 4: Report — files-changed AND violations-remaining (never silent partials)

After every dispatched batch returns, render one honest report. This is the covr never-silent-partial contract: a sweep that fixed some and left some is RECORDED, never silent.

Report, with paths, both halves:

- **files-changed** — every file a fix agent edited, by path, with the one-line change it made.
- **violations-remaining** — every violation NOT fixed, by path, each with a reason: `behavior-changing rewrite`, `outside the v1 grammar (survey-only, human judgment)`, `agent declined — ambiguous safe fix`, or `sweep skipped — no python profile / no usable baseline`.

If any batch failed, was skipped, or any file remains, say so explicitly. A **partial** sweep is a first-class outcome and is reported as such — partials are recorded, NEVER silent. Do not round a partial up to "done." Render it as a table:

```
Rule R-NNN: "<statement>"  (mechanizable: <true|false>)

files-changed (N):
  • libs/people/data.ts        — removed direct process.env read
  • libs/market/data.ts        — routed config through libs/contracts

violations-remaining (M):
  • libs/legacy/auth.ts        — behavior-changing rewrite — needs human design
  • apps/admin/config.ts       — outside the v1 grammar (survey-only)

sweep status: PARTIAL (M of N+M violations remain)
```

### Phase 5: Re-run baseline-verify — confirm the rule is live

Re-run the conformance dispatcher so the just-appended rule is exercised by the live checker and is now enforced going forward. Scope to the new rule id again, or pass `rule_ids: null` to confirm the whole mechanizable set still passes:

```
printf '{"repo_root":"%s","rule_ids":["R-NNN"],"cwd":"%s"}' "$REPO_ROOT" "$PWD" \
  | bash hooks/baseline-verify.sh
```

Read the verdict from the `results` JSON, never the dispatcher exit code (it always exits 0). Interpret:

- **`pass`** — the sweep cleared the mechanizable violations; the rule is live and enforced going forward. The rule will now fire at every `/build` wave gate (Step 6c-baseline) and on future `/rule-sweep` runs.
- **`fail`** — violations remain that the sweep did not fix (expected when behavior-changing rewrites were deferred). The rule is still recorded and still enforced going forward — `/build` will now hold the wave on it until the remaining violations are resolved. Make this explicit in the confirmation; do not present a `fail` as a clean close.
- **`no-check`** — a non-mechanizable rule. It is recorded with provenance and surfaces in the human `ARCHITECTURE.md`, enforced by human judgment / a native tool, not the v1 bash checker. Say so.

Render the Phase 5 confirmation: the rule id, the final mechanizable verdict, and one line stating the rule is now enforced going forward (the in-flight loop has terminated in a live gate, per `standards/process/lessons-terminate-in-gates.md`).

## Constraints

- NEVER edit a production file in your own context. All fixes are dispatched to subagents via the Agent tool in file-isolated batches.
- NEVER bypass a hook. Fixes flow through normal hooked Edit/Write; this skill adds no bypass and disables nothing.
- NEVER force-fix a behavior-changing rewrite. It is reported as a remaining violation with a reason; a human resolves it.
- NEVER report a partial sweep as done. files-changed AND violations-remaining are always both reported, with paths.
- NEVER touch `skills/init-project/SKILL.md` or `scripts/baseline.py` — siblings own them. Consume them through their CLI contract only.
- ALWAYS branch on the `baseline.py status` TOKEN, never the exit code; ALWAYS read `baseline-verify` verdicts from the results JSON, never the exit code.
- ALWAYS sanitize the rule statement at the capture site before it leaves your context.
- ALWAYS use the `python3 ~/.claude/scripts/baseline.py` invocation prefix verbatim (Codex path-rewrite depends on it).

## Definition of Done

`/rule-sweep` is done for a given invocation when ALL of the following hold for the terminal path reached. Items 1-2 always apply; items 3-7 apply to the captured-and-swept path; item 8 applies to the missing-baseline bootstrap-deferred path; item 9 applies to the infrastructure-stop path.

1. The Before Starting reads were executed via the Read tool before any phase action.
2. The Preflight `baseline.py status` check ran and the skill branched on the TOKEN.
3. CAPTURED-AND-SWEPT: the rule was sanitized at the capture site and appended via `baseline.py append-rule` with `--statement`, `--who`, `--trigger`, and `--mechanizable` iff the statement fit the v1 grammar; the printed `R-NNN` was captured.
4. CAPTURED-AND-SWEPT: a sweep ran — `baseline-verify.sh` for a mechanizable rule (scoped to `R-NNN`) or a grep/Glob survey for a non-mechanizable one — and any fixes were dispatched to file-isolated fix agents via the Agent tool through hooked Edit/Write.
5. CAPTURED-AND-SWEPT: no behavior-changing rewrite was force-fixed; each is listed as remaining with a reason.
6. CAPTURED-AND-SWEPT: the Phase 4 report listed files-changed AND violations-remaining WITH paths; any partial was recorded explicitly, never silent.
7. CAPTURED-AND-SWEPT: Phase 5 re-ran `baseline-verify.sh`, read the verdict from the results JSON, and confirmed the rule is enforced going forward.
8. BOOTSTRAP-DEFERRED: the missing-baseline picker was rendered and, on the deferral choice, the operator was pointed at `/init-project --phase=baseline`; no rule was appended and no sweep ran.
9. INFRASTRUCTURE-STOP: a `malformed` token or an IO error was surfaced as an infrastructure failure with the baseline path; no rule was appended.

If any applicable item is not satisfied, `/rule-sweep` is NOT done for that path. Do not report a clean close when violations remain — a `fail` verdict with deferred behavior-changing rewrites is a recorded partial, not a done sweep.
