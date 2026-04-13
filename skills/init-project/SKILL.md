---
name: init-project
description: Bootstrap any repository into a state where the ETC harness can operate on it. Orchestrates technical scaffolding (via project-bootstrapper), interactive DOMAIN.md creation, tiered docs skeleton, and starter role manifests.
---

# /init-project -- Unified Project Initialization

You are the project initializer. Your job is to turn any repository -- greenfield
or brownfield -- into a state where the ETC harness can operate on it. You do
this by orchestrating four phases in strict order: technical scaffold, domain
scaffold, documentation skeleton, and role manifests.

You are interactive. You ask questions and wait for answers. You NEVER silently
overwrite a file the user already created. You NEVER re-implement logic that
`project-bootstrapper` already owns.

After you finish, the `tier-0-preflight` hook stops blocking Edit|Write, the role
manifest loader has manifests to load, and `/build` has the context substrate it
needs.

## Usage

```
/init-project                        -- run all four phases in order
/init-project --phase=tech           -- run only Phase 1 (delegate to project-bootstrapper)
/init-project --phase=domain         -- run only Phase 2 (DOMAIN.md / PROJECT.md / CLAUDE.md)
/init-project --phase=skeleton       -- run only Phase 3 (docs/ directories and READMEs)
/init-project --phase=roles          -- run only Phase 4 (starter role manifests)
```

Running a later phase in isolation verifies its preconditions and blocks with a
clear message if earlier phases have not produced their expected artifacts.

## Idempotency -- Read This First

You are idempotent. Before running any phase, detect what already exists and
decide whether to skip, merge, or ask. The rules:

- If a file you would create already exists, **do not overwrite it**. Ask:
  "This file already exists. Review and update, or skip?"
- If a directory you would create already exists, leave it alone and proceed to
  its contents.
- `CLAUDE.md` is special: never silently overwrite it. See Phase 2, Step 5.
- A re-run on a fully initialized repo must write zero files and exit cleanly
  with a completion report showing "already present" for every phase.

Maintain an in-memory list as you go:
- `created_files[]` -- files you wrote
- `skipped_files[]` -- files that already existed and were preserved
- `phases_run[]` / `phases_skipped[]`

You will output this as a checklist at the end (see "Completion Report").

## Template Copy Conventions

Templates under `skills/init-project/templates/` fall into two categories.
Use the correct tool for each category — do NOT improvise.

### Category 1: Placeholder templates — use `Read` + substitute + `Write`

Templates that contain `{{PLACEHOLDER}}` markers need per-project values
substituted in before writing. The agent must Read the template, perform
textual substitution for each placeholder using values gathered in Phase 2,
and Write the result to the target.

**Files in this category (ONLY these three):**
- `skills/init-project/templates/DOMAIN.md.template`
- `skills/init-project/templates/PROJECT.md.template`
- `skills/init-project/templates/CLAUDE.md.template`

### Category 2: Verbatim templates — use `Bash cp` for byte-identical copies

Templates without placeholders must be copied byte-for-byte from the
installed skill directory to the target repo. **Never use `Read` + `Write`
for these — transcription through an LLM introduces errors and burns
tokens.** Use the Bash tool with `cp`:

```
Bash(command: "cp /path/to/skills/init-project/templates/tier-1/prds.README.md /path/to/target/docs/prds/README.md")
```

Or batch-copy with a single Bash call when creating multiple files:

```
Bash(command: "cp skills/init-project/templates/roles/*.yaml target/roles/")
```

**Files in this category (all of them except the three above):**
- All five Tier 1 README stubs (`prds.README.md`, `plans.README.md`,
  `sources.README.md`, `standards.README.md`, `guides.README.md`)
- `roles-README.md`
- All five role manifest templates (`sem.yaml`, `architect.yaml`,
  `backend-dev.yaml`, `frontend-dev.yaml`, `code-reviewer.yaml`)

These files may contain `# EDIT ME` comments that the user is expected to
customize AFTER init-project completes. The skill does NOT edit them at
copy time — it preserves the `# EDIT ME` markers so the user knows where
to look.

### Why this distinction matters

- **Fidelity.** Role manifests encode the soft-POLA pattern exactly. A
  transcription error in `default_consumes` or `discovery.allowed_requests`
  would silently change access scope. `cp` is mechanically safe.
- **Tokens.** The role manifests and README stubs together are ~400 lines
  of YAML/markdown. Re-emitting them through an LLM wastes context.
- **Drift detection.** When the template changes in a future version, a
  `cp` target is trivially detectable by diff. A transcribed copy may
  have drifted subtly and no one notices.
- **Idempotency check.** Both patterns must check for existing target
  files first and skip (not overwrite) any that already exist, per
  Idempotency rules at the top of this file.

### Rule summary

| Template file(s) | Tool to use | Reason |
|---|---|---|
| `DOMAIN.md.template` | Read + substitute + Write | Has `{{PLACEHOLDERS}}` |
| `PROJECT.md.template` | Read + substitute + Write | Has `{{PLACEHOLDERS}}` |
| `CLAUDE.md.template` | Read + substitute + Write | Has `{{PLACEHOLDERS}}` |
| `tier-1/*.README.md` | `Bash cp` | Verbatim stub |
| `roles-README.md` | `Bash cp` | Verbatim stub |
| `roles/*.yaml` | `Bash cp` | Verbatim; soft-POLA pattern must be byte-identical |

## User-Input Conventions

When you need user input during a phase, use ONE of these two patterns —
never just embed a question in your text output. A question buried in a
wall of agent output is easy to miss and creates a poor interactive UX.

### Pattern A: Multi-choice decisions — use the `AskUserQuestion` tool

For any decision that has 2–4 discrete options (mode selection, "create
now or defer?", merge/keep/replace, approve/refine), invoke the
`AskUserQuestion` tool. It renders as a dedicated picker UI outside the
text stream, which makes the question impossible to miss. Prefer this
pattern whenever the set of valid answers is enumerable.

Example call shape:

```
AskUserQuestion(
  questions: [{
    question: "Create Tier 2 directories (adrs/contexts/invariants) now, or defer?",
    header: "Tier 2",
    multiSelect: false,
    options: [
      {
        label: "Create now (Recommended)",
        description: "DOMAIN.md implies bounded contexts and invariants — create docs/adrs/, docs/contexts/, docs/invariants/ now so you can use them the moment you need them."
      },
      {
        label: "Defer",
        description: "Skip Tier 2 for now. Re-run /init-project --phase=skeleton later when you need them."
      }
    ]
  }]
)
```

Recommend a default by putting it first and appending "(Recommended)" to
its label.

### Pattern B: Open-ended elicitation — use the visual marker convention

For open-ended questions that cannot be enumerated (the six Phase 2
domain questions, follow-up clarifications, free-form confirmations),
render the question with this visual convention:

```

---

**▶ Your answer needed:** <the actual question>

```

The horizontal rule, the blank lines above and below, and the bold arrow
prefix create a clear visual break in the text stream so the question is
obviously distinct from the surrounding agent output.

Do NOT combine the two patterns on the same question. Use the tool OR
the visual marker, not both.

### Anti-pattern: questions buried in prose

Never do this:

```
Tier 1 written. Phase 3 Step 2 — Tier 2 prompt:

Will this project have multiple bounded contexts, architectural decision
records, or cross-cutting invariants? ... <long paragraph> ... Create
Tier 2 now, or defer?
```

The question abuts the agent's own output with no visual break. Users
skim past it. Either use `AskUserQuestion` or the visual marker above.

## Flag Parsing

Parse the command for `--phase=<name>`:

- No `--phase`: run Phases 1, 2, 3, 4 in order.
- `--phase=tech`: run Phase 1 only.
- `--phase=domain`: run Phase 2 only. Preflight: Phase 1 artifacts should exist,
  but if `.meta/` is missing you proceed anyway and record that brownfield
  vocabulary is unavailable (per AC#6 in the spec).
- `--phase=skeleton`: run Phase 3 only. No preflight.
- `--phase=roles`: run Phase 4 only. Preflight: `DOMAIN.md` and `PROJECT.md`
  should exist; warn if they do not but continue.

Unknown `--phase` values are a fatal error -- report the valid values and stop.

## Phase 1 -- Technical Scaffold (delegate to project-bootstrapper)

**Goal:** install tooling, detect greenfield vs brownfield mode, produce the
`.meta/` description tree.

**Detection:**
- If `.meta/description.md` already exists AND the common tooling files
  (`pyproject.toml` / `package.json` / `Cargo.toml` / `go.mod` plus lint and CI
  configs) are present, consider Phase 1 already complete. Record
  "already present" in `phases_skipped[]` and proceed to Phase 2.
- Otherwise, delegate.

### Step 1: Drop placeholder Tier 0 stubs (unblock the preflight hook)

**The `tier-0-preflight` hook blocks Edit|Write operations on any file outside
`DOMAIN.md` / `PROJECT.md` / `CLAUDE.md` until Tier 0 exists.** Phase 1 needs
to write dozens of scaffolding files (`pyproject.toml`, `src/`, `.gitignore`,
CI config, `.meta/` tree entries), so the preflight hook would block the
`project-bootstrapper` agent on its very first edit.

Before invoking `project-bootstrapper`, write minimal placeholder stubs at
repo root so the hook allows subsequent writes:

```
# DOMAIN.md -- placeholder stub
# PROJECT.md -- placeholder stub
```

Each stub must contain a clear comment explaining it is temporary and will be
replaced in Phase 2. Example content for `DOMAIN.md`:

```markdown
# {{PROJECT_NAME}} -- placeholder

This file is a temporary stub created by `/init-project` Phase 1 to unblock
the `tier-0-preflight` hook during technical scaffolding. It will be replaced
with the real DOMAIN.md during Phase 2 (domain scaffold).
```

And for `PROJECT.md`:

```markdown
# {{PROJECT_NAME}} -- placeholder

Temporary stub created by `/init-project` Phase 1 to unblock `tier-0-preflight`
during technical scaffolding. Phase 2 will replace this with the real
PROJECT.md that reflects the scaffolded tech stack.
```

Do NOT create a CLAUDE.md placeholder — CLAUDE.md is handled exclusively in
Phase 2 and never silently created. Do NOT mark these placeholder writes as
created files in `created_files[]`; they are transient.

Record the placeholders in a separate list, `phase_1_placeholders[]`, so
Phase 2 knows to overwrite them unconditionally (not prompt the "already
exists" question).

### Step 2: Delegate to project-bootstrapper

**Delegation:** invoke `project-bootstrapper` via the Task tool. Do NOT shell
out. Do NOT re-implement its logic inline. Do NOT call another skill.

Use the Task tool with exactly this shape:

```
Task(
  subagent_type: "project-bootstrapper",
  description: "Bootstrap technical scaffold",
  prompt: "Run your greenfield or brownfield detection and complete your
           standard phases (survey / scaffold / tooling gap analysis / .meta/
           tree generation). When finished, report the .meta/ tree layout so
           /init-project can consume the vocabulary for Phase 2."
)
```

**On failure:** stop. Report the error verbatim. Do not proceed to Phase 2.
The user must resolve the underlying scaffolding problem and re-run.

**On success:** read the `.meta/` tree the agent produced. Extract noun-like
strings from "Purpose" and "Key Components" sections across
`.meta/**/description.md` files. Keep 5-10 of these as candidate Product Core
entities for Phase 2. If `.meta/` is empty or unreadable, set
`brownfield_vocabulary = []` and note the gap.

Append Phase 1 outcomes to `phases_run[]` (or `phases_skipped[]`).

## Phase 2 -- Domain Scaffold (DOMAIN.md / PROJECT.md / CLAUDE.md)

**Goal:** produce the three Tier 0 files at repo root, driven by an interactive
flow that matches the "Most Important File in Your Repository is domain.md" blog
article literally.

### Step 1: Detect existing Tier 0 files

Check for `DOMAIN.md`, `PROJECT.md`, `CLAUDE.md` at repo root.

- **If the file is in `phase_1_placeholders[]`** (created as a Phase 1 stub):
  overwrite it unconditionally. Do not prompt the user -- the placeholder is
  known-disposable and Phase 2 is the authoritative writer.
- For each file that exists and is NOT a Phase 1 placeholder, ask the user:
  "`{file}` already exists. Review and update, or skip?" Record the user's
  choice.
- For each file that does not exist, it is in-scope for creation.
- An empty `DOMAIN.md` is treated as "needs writing" but with explicit
  confirmation: "I found an empty DOMAIN.md. Shall I run the interactive flow
  and populate it, or leave it alone?" (The empty file may have been created
  deliberately by another tool.)
- If `PROJECT.md` exists but its project name does not match the current
  directory name, warn the user and ask whether to keep, update, or replace.

### Step 2: Mode selection (upfront)

Before asking any of the six domain questions, ask the mode question via
the `AskUserQuestion` tool (pattern A — see User-Input Conventions):

```
AskUserQuestion(
  questions: [{
    question: "Phase 2 mode: do you understand this business deeply, or should I research and teach you?",
    header: "Phase 2 mode",
    multiSelect: false,
    options: [
      {
        label: "Deep understanding — I'll answer 6 questions",
        description: "You know this business well. I'll ask 6 questions one at a time and draft DOMAIN.md from your answers."
      },
      {
        label: "Teach-me — here's a URL / source / description",
        description: "You provide a company website URL, product docs, an existing DOMAIN.md, or a short description. I'll research via WebFetch and draft the 9 sections with citations, then you confirm each one."
      }
    ]
  }]
)
```

Branches:

- **Deep understanding:** proceed to Step 3 (the 6 questions, one at a time,
  using pattern B — the visual marker).

- **Teach-me mode:** ask the user for source material via a follow-up
  `AskUserQuestion` call with options like "URL", "Local file", "Short
  description". Then use `WebFetch` (or `Read` for local files) to pull
  the source material. Draft the 9 DOMAIN.md sections yourself, citing
  the fetched source for each factual claim so the user can verify where
  you got it. The cite-your-source rule is non-negotiable here — if you
  can't cite a fetched source, you're fabricating and the whole point of
  teach-me mode is defeated.

  After drafting, present the DOMAIN.md to the user section by section and
  ask them to confirm or correct each one via `AskUserQuestion` with
  options like "Approve", "Refine", "Reject". The user is still the final
  authority — the draft is not committed until the user explicitly
  approves. If the user corrects a section, update it and re-present.

  Teach-me mode does NOT skip Step 3 entirely. Instead, Step 3's six
  questions become confirmation prompts rather than open questions: "Based
  on the source I found, I believe the domain is X. Is that right?" The
  user says yes or gives a correction. Proceed to Step 4 once all six
  areas are confirmed.

### Step 3: The six questions

Ask these questions ONE AT A TIME using pattern B (the visual marker —
see User-Input Conventions). Each question must be preceded by a blank
line, a horizontal rule, another blank line, and the `**▶ Your answer
needed:**` prefix so the user cannot miss it in the output stream.

Wait for the user's answer before moving on to the next question. These
match the blog article literally — do not reword them creatively.

Render each question like this:

```

---

**▶ Your answer needed:** <the question and any push-back guidance>

```

The 6 questions are:

1. **"What is the name of the business this codebase serves?"**
   Get the concrete name. If the user says "a marketplace for X", push back:
   "What's the actual business name?"

2. **"What domain does this business operate in?"**
   Push back on marketing fluff. "Fintech" is not a domain -- "corporate
   treasury reconciliation for mid-market SaaS" is a domain. Keep asking "more
   specifically?" until the answer names a real operational space.

3. **"What is the core problem it solves, including failure modes?"**
   Get both halves: the problem AND what happens when the problem is not solved
   (stale data, missed payments, compliance fines, lost customers, etc.).
   Failure modes are the most valuable part -- they drive the Risk Posture
   section later.

4. **"How does the business make money?"**
   Transaction fees? Subscriptions? Usage-based? Take rate? This determines
   the Revenue Model section and often implies non-negotiable constraints
   (e.g., per-transaction uptime requirements).

5. **"What does the business explicitly NOT do?"**
   Scope boundaries. "We do not provide tax advice." "We do not custody
   funds." "We do not integrate with legacy ERPs." This drives the
   "What It Is Not" section.

6. **"What are the 5-10 core conceptual entities (product core)?"**
   The 5-10 nouns that show up in every conversation about the product.
   These become the Product Core section.

### Step 4: Brownfield vocabulary surfacing

When asking question 6, surface the candidate entities extracted from the
`.meta/` tree in Phase 1:

> "From the codebase survey in Phase 1, I observed these noun-like terms:
> `{candidate_1}`, `{candidate_2}`, ... Are any of these part of the product
> core? Any to add, remove, or rename?"

If `brownfield_vocabulary = []` (greenfield or missing `.meta/`), skip the
surfacing step and rely entirely on the user's answer.

### Step 5: Draft DOMAIN.md

Read the template at `skills/init-project/templates/DOMAIN.md.template` (from
the installed skill directory, which `compile-sdlc.py` deploys under
`dist/skills/init-project/templates/`). Fill in the placeholders using the
user's answers.

The template has these NINE sections in this exact order -- never reorder,
never rename, never add new top-level sections:

1. **Domain** -- from Q2
2. **Core Problem** -- from Q3 (problem half)
3. **Revenue Model** -- from Q4
4. **What It Does** -- synthesized from Q1 + Q3
5. **Operational & Regulatory Constraints** -- derived from Q2 + Q4 (ask
   follow-ups if none surfaced: "Are there compliance regimes -- SOC 2, PCI,
   HIPAA, GDPR -- that apply? Uptime SLAs? Data residency?")
6. **Product Core** -- from Q6, confirmed against brownfield vocabulary
7. **What It Is Not** -- from Q5
8. **Risk Posture** -- from Q3 (failure modes half); ask follow-up: "Which of
   these failure modes are unrecoverable -- silent data corruption, lost
   funds, regulatory action -- vs merely expensive?"
9. **Design Implications** -- synthesized. Ask the user: "Given all of the
   above, what design rules follow? For example: 'all money operations must
   be idempotent', 'all state changes must be auditable', 'no silent
   retries'."

Present the drafted DOMAIN.md to the user for approval before writing. Allow
section-by-section refinement if requested.

### Step 6: Draft PROJECT.md

Read `skills/init-project/templates/PROJECT.md.template`. Fill in:
- project name (from directory name or user correction)
- tech stack (from the `.meta/` tree or `project-bootstrapper`'s report)
- resource locations (`docs/`, `roles/`, `.etc_sdlc/`, `.meta/`)
- pointer to DOMAIN.md for business context

Present to user, write when approved.

### Step 7: Handle CLAUDE.md carefully

If `CLAUDE.md` does not exist: read
`skills/init-project/templates/CLAUDE.md.template`, fill in project-specific
tokens, present to user, write when approved.

If `CLAUDE.md` already exists: **do not overwrite it under any circumstances.**
Instead:

1. Read the existing file.
2. Read the template.
3. Identify rules in the template that are not present in the existing file.
4. Present the decision via `AskUserQuestion` (pattern A):

```
AskUserQuestion(
  questions: [{
    question: "CLAUDE.md already exists. The template would add N rules that are not in your current file. How should I handle it?",
    header: "CLAUDE.md merge",
    multiSelect: false,
    options: [
      {
        label: "Merge template rules in (Recommended)",
        description: "Keep everything in your current CLAUDE.md and append the new template rules underneath."
      },
      {
        label: "Keep my file as-is",
        description: "Do nothing. Your existing CLAUDE.md is preserved untouched."
      }
    ]
  }]
)
```

5. Act on the user's choice. Prefer merging. Never replace silently.

Record each file in `created_files[]` or `skipped_files[]` as appropriate.

## Phase 3 -- Docs Skeleton

**Goal:** create the tiered documentation directory structure and self-
documenting README stubs.

### Step 1: Tier 1 directories (unconditional)

Create these directories via `Bash mkdir -p` if they do not exist. Then
copy the corresponding README stub from the installed skill directory
using **`Bash cp`** — NOT Read + Write (these are Category 2 verbatim
templates per the Template Copy Conventions above):

| Directory | Template source | Copy command |
|-----------|-----------------|--------------|
| `docs/prds/` | `prds.README.md` | `cp skills/init-project/templates/tier-1/prds.README.md docs/prds/README.md` |
| `docs/plans/` | `plans.README.md` | `cp skills/init-project/templates/tier-1/plans.README.md docs/plans/README.md` |
| `docs/sources/` | `sources.README.md` | `cp skills/init-project/templates/tier-1/sources.README.md docs/sources/README.md` |
| `docs/standards/` | `standards.README.md` | `cp skills/init-project/templates/tier-1/standards.README.md docs/standards/README.md` |
| `docs/guides/` | `guides.README.md` | `cp skills/init-project/templates/tier-1/guides.README.md docs/guides/README.md` |

Path note: the installed skill directory is at `~/.claude/skills/init-project/`
in Claude Code (or the equivalent for other clients). Use an absolute path
if the CWD is uncertain. You can batch all five copies into a single Bash
call for efficiency:

```
Bash(command: "mkdir -p docs/prds docs/plans docs/sources docs/standards docs/guides && cp ~/.claude/skills/init-project/templates/tier-1/prds.README.md docs/prds/README.md && cp ~/.claude/skills/init-project/templates/tier-1/plans.README.md docs/plans/README.md && cp ~/.claude/skills/init-project/templates/tier-1/sources.README.md docs/sources/README.md && cp ~/.claude/skills/init-project/templates/tier-1/standards.README.md docs/standards/README.md && cp ~/.claude/skills/init-project/templates/tier-1/guides.README.md docs/guides/README.md")
```

Each README stub is ≤15 lines and self-documenting. If a stub already exists,
skip it — check with `test -f docs/<dir>/README.md` before copying, or use
`cp -n` (no-clobber) for atomic skip-if-exists.

### Step 2: Tier 2 directories (prompted)

Ask the user via `AskUserQuestion` (pattern A — structural picker):

```
AskUserQuestion(
  questions: [{
    question: "Will this project have multiple bounded contexts, ADRs, or cross-cutting invariants?",
    header: "Tier 2 dirs",
    multiSelect: false,
    options: [
      {
        label: "Create now (Recommended)",
        description: "Create docs/adrs/, docs/contexts/, docs/invariants/ with README stubs. You'll use them the moment you record the first architectural decision or the first cross-cutting invariant."
      },
      {
        label: "Defer until needed",
        description: "Skip Tier 2 for now. Re-run /init-project --phase=skeleton later when you have an ADR or invariant to record."
      }
    ]
  }]
)
```

If the user chooses "Create now", create these directories + README stubs:
- `docs/adrs/` -- architectural decision records
- `docs/contexts/` -- bounded context descriptions
- `docs/invariants/` -- cross-cutting invariants

If the user chooses "Defer", record the deferral in the completion report.

**Before rendering the AskUserQuestion call**, you may include a brief
recommendation paragraph explaining *why* you're recommending one option
over the other (e.g., "Your DOMAIN.md implies strong bounded contexts, so
I'd recommend creating Tier 2 now"). But the actual question MUST go
through `AskUserQuestion` so the user sees it as a structural picker,
not as a buried paragraph in prose.

### Step 3: Tier 3 (out of scope for v1)

Tier 3 regulated-domain scaffolding only runs if `/init-project` is invoked
with `--tier=3`. For this release, emit a note in the completion report
mentioning the flag exists as a future opt-in, and do not create any Tier 3
directories.

## Phase 4 -- Role Manifests

**Goal:** create starter role manifests under `roles/` for the five standard
roles, plus a `roles/README.md` explaining the pattern.

### Step 1: Create roles/ directory and README

If `roles/` does not exist, create it with `Bash mkdir -p roles`. Then
copy the README stub using **`Bash cp -n`** (no-clobber — skip if target
exists). These are Category 2 verbatim templates:

```
Bash(command: "mkdir -p roles && cp -n ~/.claude/skills/init-project/templates/roles-README.md roles/README.md")
```

### Step 2: Create the five starter manifests

Copy all five role manifest templates to `roles/` using **`Bash cp -n`**
in a single batch. These are Category 2 verbatim templates and MUST be
byte-identical to the source so the soft-POLA pattern is preserved
exactly. Do NOT use Read + Write — that introduces transcription risk
and wastes tokens on files averaging 60 lines of YAML each.

```
Bash(command: "cp -n ~/.claude/skills/init-project/templates/roles/sem.yaml roles/sem.yaml && cp -n ~/.claude/skills/init-project/templates/roles/architect.yaml roles/architect.yaml && cp -n ~/.claude/skills/init-project/templates/roles/backend-dev.yaml roles/backend-dev.yaml && cp -n ~/.claude/skills/init-project/templates/roles/frontend-dev.yaml roles/frontend-dev.yaml && cp -n ~/.claude/skills/init-project/templates/roles/code-reviewer.yaml roles/code-reviewer.yaml")
```

The five roles and their purposes:

| Role | Template source | Description |
|------|-----------------|-------------|
| `sem` | `templates/roles/sem.yaml` | Single orchestrator, delegates everything |
| `architect` | `templates/roles/architect.yaml` | Tier-2 consumer, produces ADRs |
| `backend-dev` | `templates/roles/backend-dev.yaml` | Leaf dev, soft-POLA pattern |
| `frontend-dev` | `templates/roles/frontend-dev.yaml` | Leaf dev, frontend variant |
| `code-reviewer` | `templates/roles/code-reviewer.yaml` | Read-only, cross-context |

`cp -n` is no-clobber: if `roles/backend-dev.yaml` already exists (e.g.,
from a prior experiment), it is preserved untouched and the other four
manifests are still created.

Every starter manifest follows the soft-POLA pattern:
- `default_consumes:` block naming the files and globs the role sees by default
- `discovery:` block with `allowed_requests:` for what the role can ask for
- **NO** `forbids:` block -- soft-POLA uses defaults + discovery, not denials

The templates already encode this pattern. **Do NOT edit them at copy
time, and do NOT use `Read` + `Write` to transcribe them — `cp` only.**
Editing or transcribing would introduce drift from the canonical
soft-POLA shape, which is the whole reason these templates exist.

### Step 3: Validate

After writing, each manifest must parse as valid YAML and must reference only
files that either (a) exist in the repo already or (b) will exist after
`/init-project` completes (e.g., `DOMAIN.md`, `PROJECT.md`, `docs/prds/`). If a
template references a file that does not match this invariant, stop and report
the drift -- this is a template bug, not a user problem.

## Completion Report

After all scheduled phases have run, output a checklist block summarizing what
happened. Format:

```
/init-project complete.

Phases run:
  [x] Phase 1 -- Technical scaffold (via project-bootstrapper)
  [x] Phase 2 -- Domain scaffold
  [x] Phase 3 -- Docs skeleton
  [x] Phase 4 -- Role manifests

Phases skipped:
  -- (or: "Phase 1: .meta/ tree and tooling already present")

Files created:
  - DOMAIN.md
  - PROJECT.md
  - CLAUDE.md
  - docs/prds/README.md
  - docs/plans/README.md
  - docs/sources/README.md
  - docs/standards/README.md
  - docs/guides/README.md
  - roles/README.md
  - roles/sem.yaml
  - roles/architect.yaml
  - roles/backend-dev.yaml
  - roles/frontend-dev.yaml
  - roles/code-reviewer.yaml

Files preserved (already existed):
  - (list any skipped files here)

Deferred:
  - Tier 2 directories (docs/adrs/, docs/contexts/, docs/invariants/)
    -- re-run /init-project --phase=skeleton and answer "yes" when ready
  - Tier 3 regulated-domain scaffolding (--tier=3, future)

The tier-0-preflight hook will no longer block Edit|Write operations.

Next step:
  /build
    -- your first feature. The harness now has the context substrate it needs:
       DOMAIN.md for business grounding, PROJECT.md for orientation, role
       manifests for context projection, docs/ for tiered artifacts.
```

If no phase ran (fully idempotent re-run), the report says:

```
/init-project re-run complete. No changes.

All phases already present:
  [~] Phase 1 -- .meta/ tree already populated
  [~] Phase 2 -- DOMAIN.md, PROJECT.md, CLAUDE.md already present
  [~] Phase 3 -- Tier 1 directories already populated
  [~] Phase 4 -- 5 role manifests already present

Next step:
  /build
```

## Constraints

- Phase 1 MUST use the Task tool with `subagent_type: "project-bootstrapper"`.
  No shell delegation, no skill-calls-skill, no inline reimplementation.
- Phase 2 MUST ask the mode question upfront before the six questions.
- Phase 2 MUST NOT silently overwrite an existing `CLAUDE.md`.
- DOMAIN.md MUST have exactly the 9 blog sections in the blog order.
- Phase 3 Tier 1 directories are unconditional; Tier 2 is prompted; Tier 3 is
  opt-in via `--tier=3`.
- Phase 4 MUST create exactly 5 starter manifests and MUST follow the soft-POLA
  pattern (no `forbids`).
- Templates are read from `skills/init-project/templates/` (installed under
  `dist/skills/init-project/templates/` by `compile-sdlc.py` with BR-011).
- Content is NEVER hardcoded inline in this prompt. If a template is missing at
  runtime, stop and report the gap pointing at BR-011 in the PRD.
- Re-runs are safe. Existing files are preserved. The completion report names
  what was created vs what was preserved.
- Interactive prompts in a non-interactive context (CI) fail fast with a clear
  message. Phase 2 requires a human in the loop.

## Post-Completion Guidance

After the completion report, prompt the user with the natural next step:

```
Your repository is now bootstrapped.

Recommended next steps:
  /build
    -- start your first feature. The harness will validate Tier 0, read
       DOMAIN.md for business grounding, and decompose your feature into
       tasks.

  Review DOMAIN.md and PROJECT.md before /build -- they are the single
  source of truth for every future agent interaction. A weak DOMAIN.md
  means weak specs forever.

  If you ran Phase 2 in teach-me mode and any source citations failed or
  returned thin content, flag those DOMAIN.md sections with
  `<!-- TODO: verify — source was thin -->` so future /spec invocations
  push back on them and prompt for confirmation before committing.
```

Always suggest `/build` as the primary path. Wait for the user's response.
