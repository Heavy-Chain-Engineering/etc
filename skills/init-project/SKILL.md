---
name: init-project
description: Bootstrap any repository into a state where the ETC harness can operate on it. Orchestrates technical scaffolding (via project-bootstrapper), interactive DOMAIN.md creation, tiered docs skeleton, and starter role manifests.
---

# /init-project -- Unified Project Initialization

You are the project initializer. Your job is to turn any repository -- greenfield
or brownfield -- into a state where the ETC harness can operate on it. You do
this by orchestrating phases in strict order: technical scaffold (Phase 1),
architecture baseline (Phase 1.5 -- discover and verify the existing
architecture), domain scaffold (Phase 2), documentation skeleton (Phase 3),
and role manifests (Phase 4). Phase 1.5 slots between the technical and domain
scaffolds: it surveys what the codebase actually IS before you write the
business-context docs that describe what it should be.

You are interactive. You ask questions and wait for answers. You NEVER silently
overwrite a file the user already created. You NEVER re-implement logic that
`project-bootstrapper` already owns.

After you finish, the `tier-0-preflight` hook stops blocking Edit|Write, the role
manifest loader has manifests to load, and `/build` has the context substrate it
needs.

## Response Format (Verbosity)

Terse and structured. Prose is limited to:
(a) phase-entry announcements, (b) interactive question render blocks,
(c) the Completion Report, (d) the Post-Completion Guidance block.
Use fenced code blocks for machine-readable artifacts (template diffs,
YAML, `AskUserQuestion` call shapes). Use tables for enumerations of
files, directories, or template sources. No preamble ("I'll...", "Here
is..."). No narrative summary. No emoji. Max 300 words per phase-entry
response unless producing the Completion Report (max 600 words) or the
Post-Completion Guidance block (max 400 words). When `project-bootstrapper`
returns in Phase 1, summarize its result in <= 10 lines; do not echo the
full subagent output.

## Subagent Dispatch (Non-Negotiable)

Phase 1 dispatches the `project-bootstrapper` subagent. The rules below
are absolute:

1. **You MUST invoke the Agent tool exactly once with
   `subagent_type: "project-bootstrapper"`.** This is the only way
   Phase 1 executes the technical scaffold.
2. **You MUST NOT perform technical scaffold work in your own context.**
   You MUST NOT install tooling, write `pyproject.toml` / `package.json` /
   `Cargo.toml` / `go.mod`, scaffold `src/` layout, generate CI config,
   or write any `.meta/description.md` files. That work belongs to
   `project-bootstrapper`.
3. **You MUST NOT shell out to replicate `project-bootstrapper`'s
   behavior.** No `cookiecutter`, no `create-next-app`, no copy of a
   template monorepo. Dispatch the agent; it owns the logic.
4. **You MUST NOT call another skill to do Phase 1.** No skill-calls-
   skill chaining. Dispatch the agent directly.
5. **You proceed to Phase 2 only after the dispatched agent returns
   a result.** Read the returned `.meta/` tree layout before extracting
   the brownfield vocabulary for Phase 2.
6. **Your allowed in-context actions for Phase 1 are limited to:**
   (a) detecting whether Phase 1 is already complete (existing
   `.meta/description.md` plus tooling files), (b) writing the two
   Tier 0 placeholder stubs (`DOMAIN.md`, `PROJECT.md`) so the
   `tier-0-preflight` hook allows the dispatched agent's writes,
   (c) issuing the one Agent-tool invocation, (d) reading and
   summarizing the agent's returned result, (e) extracting
   candidate entity nouns from `.meta/**/description.md` for Phase 2.

Phase 1.5 (architecture baseline) dispatches the `baseline-surveyor`
subagent in parallel batches — see that phase's own Subagent Dispatch
rules. The merge and the `baseline.py init` call run in your context; the
discovery and verification work does NOT.

Phases 2, 3, and 4 run in your own context. They are interactive (Phase 2)
or template-copy (Phases 3, 4) — no subagent dispatch. Do not dispatch
subagents for those phases.

## Before Starting (Non-Negotiable)

Read these files in order before any phase action, using the Read tool
on each exact path:

1. `standards/process/interactive-user-input.md` — the
   `AskUserQuestion` Pattern A and visual-marker Pattern B referenced
   throughout Phase 2 and Phase 3. If this file does not exist, STOP
   and report the missing file to the user — interactive phases
   cannot proceed without it.
2. `skills/init-project/templates/DOMAIN.md.template` — the Phase 2
   DOMAIN.md template with `{{PLACEHOLDERS}}`. If missing, STOP and
   report the gap pointing at BR-011 in the PRD.
3. `skills/init-project/templates/PROJECT.md.template` — the Phase 2
   PROJECT.md template. If missing, STOP and report.
4. `skills/init-project/templates/CLAUDE.md.template` — the Phase 2
   CLAUDE.md template. If missing, STOP and report.

The five Tier 1 README stubs under `skills/init-project/templates/tier-1/`
and the six role-related templates under `skills/init-project/templates/roles/`
and `skills/init-project/templates/roles-README.md` are copied verbatim
via `Bash cp`; do NOT Read them in your context at dispatch. Reading
them pre-emptively burns tokens and risks transcription drift. Verify
their existence only at the moment of copy (Phases 3 and 4) — if `cp`
fails because a template is missing, STOP and report the gap.

## Usage

```
/init-project                        -- run all phases in order
/init-project --phase=tech           -- run only Phase 1 (delegate to project-bootstrapper)
/init-project --phase=baseline       -- run only Phase 1.5 (architecture baseline: discover/verify)
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

- No `--phase`: run Phases 1, 1.5, 2, 3, 4 in order.
- `--phase=tech`: run Phase 1 only.
- `--phase=baseline`: run Phase 1.5 only (the architecture-baseline backfill
  path). Preflight: the Phase 1 `.meta/` tree must exist. If it is absent,
  emit the precondition block (see Phase 1.5) and STOP — a discovery pass over
  an un-surveyed repo would burn the parallel fan-out on a tree the
  scaffolder never described.
- `--phase=domain`: run Phase 2 only. Preflight: Phase 1 artifacts should exist,
  but if `.meta/` is missing you proceed anyway and record that brownfield
  vocabulary is unavailable (per AC#6 in the spec).
- `--phase=skeleton`: run Phase 3 only. No preflight.
- `--phase=roles`: run Phase 4 only. Preflight: `DOMAIN.md` and `PROJECT.md`
  should exist; warn if they do not but continue.

Unknown `--phase` values are a fatal error -- report the valid values and stop.

## Workspace Mode -- multi-repo initialization

Some teams clone several repos side by side under one parent directory — a
two-repo product whose frontend and backend ship from different repos, a
platform plus its SDKs, a constellation of services. The cross-repo contracts
(who owns which URL routes, where the session is injected, whose schema the
shared database follows, which repo loads whose embed bundle) live in *nobody's*
single-repo context. That blindness is a verified client failure: a two-repo
system "worked locally, broke in dev" precisely because routing/session/schema
contracts lived in no one repo's baseline. Workspace mode fixes it: each repo
gets a full, complete-standalone init+baseline, AND the workspace gets ONE
canonical cross-repo seam map.

### Detection at skill entry (BEFORE Phase 1)

Before running any phase, inspect the **shape of the invocation directory**.
This detection runs at entry so a directory-of-repos is routed to workspace mode
rather than being mistaken for a single (non-)repo by Phase 1. Enumerate the
invocation directory's **immediate children only** and branch on this trichotomy
(four arms):

| Invocation directory shape | Route |
|---|---|
| The invocation dir **is itself a git repo** (a `.git` at its root) | **Normal single-repo flow** — Phases 1, 1.5, 2-4 as documented below. A multi-package single repo (a **monorepo**: many packages, one `.git`) is **NOT a workspace** — it has one git-repo boundary, so it runs the normal single-repo flow. The discriminator is git-repo-boundary count, never package count. |
| A **non-repo directory containing ≥2 immediate-child git repos** | **Offer workspace mode** via Pattern A (`AskUserQuestion`). On accept, run the Workspace Run loop below. On decline, fall back to treating the directory as a single (greenfield) target. |
| A **non-repo directory containing exactly 1 child git repo** | **Degrade to single-repo flow** inside that one child, and emit a **note** that workspace mode was not entered (one repo is not a workspace; the seam map needs at least two repos to map a seam between). Never silently. |
| A **non-repo directory containing 0 child git repos** | **Normal greenfield handling** — there is nothing to fan out over; run the single-repo flow at the invocation directory. |

The offer (≥2 child repos) uses Pattern A so workspace mode is never
auto-entered — the operator decides whether to fan out across the whole
directory:

```
AskUserQuestion(
  questions: [{
    question: "This directory contains <N> git repos and is not itself a repo. Initialize all <N> as a workspace (per-repo baseline + one cross-repo seam map)?",
    header: "Workspace mode",
    multiSelect: false,
    options: [
      {
        label: "Workspace mode (Recommended)",
        description: "Init + architecture-baseline each repo, then build ONE <workspace>/.etc_workspace/seam-map.yaml mapping the cross-repo contracts (URL routing, session/auth, shared schema, embed loaders). Solo-cloned repos keep full context."
      },
      {
        label: "Single repo only",
        description: "Treat this directory as one greenfield target and run the normal flow here. No cross-repo seam map."
      }
    ]
  }]
)
```

### Safety rails (verbatim — never relax)

Workspace enumeration is deliberately shallow and escape-proof
(ADR-005 security note; the `.hook-markers` symlink-defense precedent):

- **Never crawl upward.** Only the operator-named invocation directory is the
  workspace root. Do not walk to its parent looking for more repos.
- **Never follow symlinks out of the workspace.** A child entry that is a
  symlink pointing outside the workspace root is skipped, not resolved and
  initialized.
- **Immediate children only.** Enumerate the direct children of the invocation
  directory and check each for a `.git`. Do not descend recursively into nested
  directories hunting for `.git` boundaries — a repo nested two levels down is
  not a workspace member.

### Workspace Run -- per-repo loop, then one canonical seam map

When workspace mode is accepted, do this:

**1. Per-repo init+baseline loop (SEQUENTIAL).** For each immediate-child git
repo, in turn, run the **full single-repo flow** — Phase 1 (technical scaffold),
Phase 1.5 (architecture baseline: DISCOVER → VERIFY → RATIFY → ENFORCE), and
Phases 2-4 — exactly as documented below, with that repo as the repo root.
Repos are processed **sequentially**, one at a time — **one ratification session
at a time**, because **human attention** (the Phase 1.5 RATIFY matrix walk) is
the bottleneck; parallel ratification walks would thrash the operator. After a
repo finishes, its own `.etc_sdlc/architecture-baseline.yaml` is **complete
standalone**: a teammate who later clones *just that repo* gets its full baseline
with a read-only seam **mirror** — no workspace dependency, no solo-clone
blindness. The DISCOVER step's `seams` surveyor (per repo) produces that repo's
seam findings; keep each repo's seam findings in context for the merge below.

**2. Merge the per-repo seam findings into ONE canonical seam map.** After every
repo's single-repo flow has completed, **reconcile** the per-repo seam findings
into the single canonical artifact at:

```
<workspace>/.etc_workspace/seam-map.yaml
```

This is the one canonical cross-repo seam map for the whole workspace (the
single editable source; per-repo `seams:` blocks are regenerated mirrors of it).
Reconciliation is human-mediated via the interactive patterns (Pattern A for the
enumerable owner/consumer assignment, Pattern B for free-form contract/evidence
notes): for each detected seam, assign the **owner** repo (who defines the
contract) and the **consumer** repo(s) (who depend on it), and compute the
workspace-level **confidence** score. A seam with no resolvable owner caps
workspace confidence at LOW (ADR-005). The seam map records, per the ADR-005
schema:

```yaml
schema_version: 1
repos:
  - {name: <repo>, path: <abs-or-workspace-relative path>}
seams:
  - id: WS-001
    kind: url-routing        # closed enum: url-routing | auth-session | data-schema | embed-loader
    owner_repo: <repo that defines the contract>
    consumer_repos: [<repos that depend on it>]
    contract: "<the cross-repo contract, in one line>"
    evidence: "<file-level evidence; env-var NAMES only, never values>"
confidence: low              # workspace-level: low | medium | high
```

The four seam **kinds** are the closed enum `url-routing | auth-session |
data-schema | embed-loader` — exactly the covr contracts (stub-per-route URL
ownership, window-global session injection, shared-DB schema, embed-bundle
loader).

**3. Write the seam map, then regenerate the mirrors.**

> **Single-writer-rule boundary (state this explicitly).** `baseline.py` is the
> single writer of the per-repo baseline format (`architecture-baseline.yaml`),
> and it exposes **no seam-map writer subcommand** — wave 2 added `sync-seams`,
> which **READS** `.etc_workspace/seam-map.yaml` and regenerates the per-repo
> mirrors from it, but there is no `init-seam-map` / `write-seam-map` command. So
> the skill **writes the seam-map YAML via the Write tool**. This is allowed
> because the seam map lives **OUTSIDE** any repo's `.etc_sdlc` (it is under
> `<workspace>/.etc_workspace/`): the single-writer rule covers each repo's
> `architecture-baseline.yaml`, NOT the workspace seam file. Write the canonical
> seam map first, THEN run `sync-seams` — `sync-seams` reads the map to build the
> mirrors, so a sync before the write would mirror a stale or absent map.

After writing the canonical seam map, regenerate every repo's read-only mirror:

```
python3 ~/.claude/scripts/baseline.py sync-seams <workspace_root>
```

`sync-seams` validates the seam map (exit 1 on a malformed map or an
out-of-enum `kind` — a bad map never silently mirrors) and rewrites each repo's
baseline `seams:` block as a read-only **mirror** filtered to the seams touching
that repo, with a hand-edits-will-be-overwritten header. A non-zero exit is an
infrastructure failure — STOP and report it; do not hand-edit the mirrors.

After the loop and the sync, the workspace has: N complete-standalone per-repo
baselines, ONE canonical seam map, and N regenerated read-only mirrors.

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

**Delegation:** invoke `project-bootstrapper` via the Agent tool. The
Subagent Dispatch (Non-Negotiable) section above applies absolutely —
one Agent invocation, no in-context scaffold work, no shell replication,
no skill-calls-skill.

Use the Agent tool with exactly this shape:

```
Agent(
  subagent_type: "project-bootstrapper",
  description: "Bootstrap technical scaffold",
  prompt: "Run your greenfield-or-brownfield detection and complete every
           phase defined in your agent definition: survey, scaffold,
           tooling gap analysis, and .meta/ tree generation. When finished,
           return: (1) the absolute path of every file created or modified,
           (2) the full .meta/ directory tree layout with one line per
           description.md written, (3) the detected mode (greenfield vs
           brownfield), (4) any tooling gaps you could not fill and the
           reason. Do not include narrative prose — return the artifact
           list and the tree only."
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

## Phase 1.5 -- Architecture Baseline (discover + verify the existing architecture)

**Goal:** survey what the codebase actually IS — its normative artifacts, the
claims those artifacts make, its competing patterns, and its cross-repo seams —
verify every load-bearing claim against the tree, write an *unratified*
machine baseline at `.etc_sdlc/architecture-baseline.yaml`, then walk the human
through ratification and turn the ratified rules into machine-checked
conformance. This phase never honors a doc on faith: a discovered convention doc
is a *claim to be checked*, not a fact to be trusted (ADR-003). The four
sub-steps run in order — **DISCOVER** and **VERIFY** (the parallel surveyor
fan-out, authored in the prior wave), then **RATIFY** (the human matrix walk)
and **ENFORCE** (checker generation), both authored in the next wave after that
fan-out shipped. DISCOVER/VERIFY produce the unratified baseline; RATIFY blesses
it and renders the human twin; ENFORCE makes the rules self-checking.

**Why this slots between Phase 1 and Phase 2:** Phase 1 produces the `.meta/`
tree (what files exist); Phase 2 writes the business-context docs (what the
system is *for*). The baseline sits between them so the domain docs are written
with an evidence-based picture of the real architecture in hand, not an
aspirational one.

**Mode at entry.** Read the mode `project-bootstrapper` reported in Phase 1
(greenfield vs brownfield):

- **Greenfield** (the scaffolder just created the structure; there is no
  pre-existing architecture to discover): skip the DISCOVER/VERIFY fan-out
  entirely. The scaffold IS the architecture, so there is nothing to verify.
  Seed a trivial **ratified** baseline directly from the scaffold layout with
  **no verification pass** — call
  `python3 ~/.claude/scripts/baseline.py init <repo_root> --from <merged-json>`
  with a minimal merged-json (empty `inventory`, empty `claims`, the scaffold's
  top-level package dirs as the only exemplar candidates), then record it as
  ratified per the scaffold. Append Phase 1.5 to `phases_run[]` and proceed to
  Phase 2. Do NOT dispatch surveyors in greenfield mode.
- **Brownfield** (an existing tree the scaffolder surveyed): run DISCOVER and
  VERIFY below.

### Preconditions (standalone `--phase=baseline`)

When invoked standalone, this phase depends on Phase 1's output. Before any
dispatch, check the precondition:

- The Phase 1 `.meta/` tree must exist (`.meta/description.md` at repo root).
  It is the surveyed file map the fan-out reasons over and the source of the
  candidate vocabulary.

If the `.meta/` tree is absent, do NOT proceed. Emit this precondition block
and STOP:

```

---

**Precondition not met — Phase 1 artifacts absent.**

Phase 1.5 (architecture baseline) needs the Phase 1 `.meta/` description tree,
but `.meta/description.md` was not found at the repo root. Run technical
scaffolding first:

  /init-project --phase=tech

then re-run `/init-project --phase=baseline`.

```

(When the full pipeline runs end-to-end, Phase 1 has just produced `.meta/`, so
this precondition is already satisfied and the block never fires.)

### DISCOVER -- enumerate candidate normative artifacts (parallel fan-out)

DISCOVER answers "what artifacts could carry normative intent, and what
competing patterns and seams exist?" It dispatches read-only `baseline-surveyor`
agents and merges their structured findings. See **Subagent Dispatch (Phase 1.5)**
below for the absolute dispatch rules.

The DISCOVER assignments are:

- one `inventory` assignment — globs the tree for convention docs, ADRs, lint
  configs, generators, reference implementations, and agent-docs (secrets
  excluded), returning a typed inventory with last-modified dates;
- one `patterns:<concern>` assignment per competing-pattern concern worth
  measuring (e.g. `patterns:dto-placement`, `patterns:state-management`) —
  enumerate the distinct implementations and their instance counts;
- one `seams` assignment — detects cross-repo boundary signals (url-routing,
  auth-session, data-schema, embed-loader), recording env-var NAMES only.

**Empty inventory is valid.** If the `inventory` surveyor returns
`findings: []` (a no-docs repo — no convention docs, no ADRs, no lint config),
that is a legitimate result, not a failure. Proceed to VERIFY with zero claim
sources and let `baseline.py init` write a valid baseline with an empty
inventory and empty claim ledger. Do not synthesize claims to fill the void.

### VERIFY -- check every load-bearing claim against the tree (parallel fan-out)

VERIFY answers "is each claim these artifacts make actually TRUE of the tree?"
For every artifact the `inventory` step surfaced that carries load-bearing
claims (convention docs, ADRs, agent-docs), dispatch one
`claims:<artifact>` surveyor. Each extracts the load-bearing claims from its
ONE artifact, greps the tree for confirming evidence and counterexamples, and
classifies each claim into the closed enum `VERIFIED | STALE | ASPIRATIONAL |
CONTRADICTED` with file-level evidence. Only `VERIFIED` claims will later enter
agent context silently; every other classification is surfaced to the human at
ratification. The surveyor classifies; it never honors a doc on faith (ADR-003).

**Self-check — etc's own prior tier-0 artifacts are verified, not retained
(re-init).** On a re-init of a repo that etc has bootstrapped before, existing
`DOMAIN.md`, `PROJECT.md`, and `.meta/` description files are NOT trusted just
because etc generated them. Their load-bearing claims (system boundaries, the
"What It Is Not" scope statements, Product Core entities, the `.meta/` purpose
lines) enter the claim ledger through the **same verification pass** as any
third-party doc: dispatch `claims:DOMAIN.md`, `claims:PROJECT.md`, and (for the
root and any subsystem) `claims:.meta/description.md` surveyors alongside the
third-party artifacts. A claim etc wrote a year ago can be just as STALE as a
vendor's README — and etc's own generated DOMAIN.md has shipped a factually
wrong system-boundary claim before (ADR-003). Existing tier-0 claims are
**never silently retained**; they are re-verified every re-init.

### Merge and write the unratified baseline

After every dispatched surveyor in every batch has returned:

1. Merge all `findings` blocks in your context (the conductor role): combine the
   inventory entries, concatenate the per-artifact claim ledgers (renumber `id`s
   to a single `CL-NNN` sequence), collect the pattern concerns and exemplar
   candidates, and collect the seams. Preserve every `bounds_applied:` note a
   surveyor reported — a sampled survey must stay disclosed through the merge.
2. Write the merged result to a temporary JSON file (the engine-output shape the
   CLI expects: top-level `inventory`, `claims`, `exemplars`, `do_not_copy`,
   `seams`, `confidence`).
3. Call the CLI — it is the ONLY writer of the baseline format; do NOT write or
   parse the YAML yourself:

```
python3 ~/.claude/scripts/baseline.py init <repo_root> --from <merged-json>
```

   It assembles, sanitizes free-form claim text, validates the schema, and
   atomically writes `.etc_sdlc/architecture-baseline.yaml` with `status:
   unratified`. It prints the written path on stdout. A non-zero exit is an
   infrastructure failure — STOP and report it; do not hand-edit the YAML.

Append Phase 1.5 to `phases_run[]`. Record the baseline path and the
classification tallies (verified / stale / aspirational / contradicted counts)
for the completion report.

### Subagent Dispatch (Phase 1.5) -- Non-Negotiable

The same absolute dispatch discipline as Phase 1, applied to the surveyor
fan-out:

1. **You MUST dispatch discovery and verification via the Agent tool with
   `subagent_type: "baseline-surveyor"`.** One Agent invocation per assignment
   (one `inventory`, one `seams`, one `patterns:<concern>` per concern, one
   `claims:<artifact>` per claim-bearing artifact). You MUST NOT survey or
   verify in your own context — that work belongs to the read-only surveyor.
2. **Dispatch in parallel batches of at most 5 (≤5 per batch).** This mirrors
   the project-bootstrapper precedent (parallelism ceiling). Issue up to five
   Agent invocations, wait for that batch to return, then dispatch the next
   batch. Do not exceed five concurrent surveyors.
3. **You MUST NOT call another skill to do the fan-out.** No skill-calls-skill;
   dispatch the agent directly.
4. **The surveyors are read-only.** They never write, never mutate the tree,
   never read secrets. You are the conductor: you merge their structured
   findings and you alone call `baseline.py init`.
5. **Merge only after every dispatched surveyor in every batch returns.** A
   partial merge would write a baseline missing whole artifacts' claims.

Each Agent invocation has this shape:

```
Agent(
  subagent_type: "baseline-surveyor",
  description: "Baseline survey: <assignment>",
  prompt: "[conductor] assignment=<inventory|claims:<artifact>|patterns:<concern>|seams> repo_root=<abs repo root> bounds=<optional>. Return exactly the findings YAML block for this assignment per your definition — no prose. If you cannot complete it, return findings: [] with a single survey_error: line."
)
```

### RATIFY -- the human matrix walk (the engine never fabricates)

RATIFY is sequential and human. It is an **interactive matrix walk** — the same
per-cell forcing function as the layered-review precedent
(`standards/architecture/layer-rubrics.yaml`): you walk every cell that the
unratified baseline could not settle by evidence and force an explicit human
decision on each. **The engine never fabricates a decision.** A non-VERIFIED
claim is not silently adopted; a competing pattern is not auto-blessed; a seam
is not assumed resolved. Every such cell is surfaced to the operator and the
human's answer is what gets recorded.

**Mode at entry.** In greenfield mode the trivial baseline was already seeded
`ratified` (no claims to walk) — skip RATIFY entirely. In brownfield mode,
proceed.

**Re-init: enter review mode first.** Before walking any cell, read the status
token:

```
TOKEN=$(python3 ~/.claude/scripts/baseline.py status <repo_root>)
```

- `ratified` — this repo already has a blessed baseline. Run the DISCOVER/VERIFY
  fan-out in **review mode**: re-survey and compare the fresh findings against
  the ratified baseline. **Zero drift → zero writes:** make NO `baseline.py`
  calls, write nothing, and emit an "already present" line in the completion
  report (the idempotency rule at the top of this skill applies — a re-run on an
  unchanged ratified baseline is a no-op). **Drift detected** (a claim that was
  VERIFIED now CONTRADICTED, a new competing pattern, a vanished exemplar) →
  **surface the drift for amendment; never auto-mutate the ratified baseline.**
  Present the drift list and ask the operator (Pattern A) whether to open an
  amendment walk over just the drifted cells. The ratified baseline is never
  silently rewritten — drift is shown, the human decides.
- `unratified` — a prior ratification was started and aborted. **Resume from the
  recorded decisions:** the partial decisions already live in the baseline's
  `claims[].resolution` / `exemplars` / `do_not_copy` / `seams` fields (written
  by the prior session through `baseline.py`). Walk only the cells that are still
  undecided; do not re-ask a cell whose decision is already recorded.
- `missing` — no baseline; RATIFY has nothing to bless (DISCOVER/VERIFY must run
  first). This should not happen in-pipeline.

**The matrix walk.** Walk these cell classes, one decision per cell. Use
**Pattern A (`AskUserQuestion`)** for the enumerable verdict and **Pattern B**
(the `▶ Your answer needed` visual marker) when free-form rationale is needed:

| Cell class | What the human decides | Recorded into |
|---|---|---|
| **non-VERIFIED claim** (STALE / ASPIRATIONAL / CONTRADICTED) | `adopt` \| `supersede` \| `record-decision` + a one-line rationale | the claim's `resolution` field |
| **competing-patterns concern** | which implementation is canonical (the exemplar) and which is `do-not-copy` | `exemplars` + `do_not_copy` |
| **exemplar blessing** | confirm the candidate is golden, name `applies_to`, name `blessed_by` | `exemplars` |
| **do-not-copy marker** | confirm the superseded path and capture the reason | `do_not_copy` |
| **seam resolution** | `sibling-path` (name the sibling repo) **or** `boundary-unknown` | `seams[].resolution` |

Render the enumerable verdict with `AskUserQuestion`, for example a
non-VERIFIED claim:

```
AskUserQuestion(
  questions: [{
    question: "Claim CL-007 ('DTOs live in libs/contracts') is CONTRADICTED — 3 counterexamples in libs/people. How do you want to resolve it?",
    header: "CL-007",
    multiSelect: false,
    options: [
      { label: "Adopt", description: "The claim is the rule; the counterexamples are violations to fix later." },
      { label: "Supersede", description: "The codebase reality wins; record a new rule that matches the tree." },
      { label: "Record decision", description: "Neither — capture a one-line decision (e.g. 'in migration; both allowed until Q3')." }
    ]
  }]
)
```

When a decision needs free-form rationale (the `record-decision` branch, the
`applies_to` of an exemplar, a sibling-repo path), capture it with Pattern B:

```

---

**▶ Your answer needed:** One line — why record this decision instead of adopting or superseding CL-007?

```

**Persisting decisions (single-writer rule — the skill NEVER edits the YAML).**
`baseline.py` is the only writer of the baseline format and exposes **no
per-claim resolution subcommand**. So you record decisions by re-running `init`
with an updated merged JSON: keep the in-context merged-findings JSON from the
DISCOVER/VERIFY merge, write each recorded decision into the matching
`claims[].resolution` / `exemplars` / `do_not_copy` / `seams[].resolution`
field of that JSON, and re-run:

```
python3 ~/.claude/scripts/baseline.py init <repo_root> --from <updated-merged-json>
```

This rewrites the baseline (status stays `unratified`) with the decisions
recorded — **never hand-edit the YAML**. Re-running `init` is the honest
persistence path: it is idempotent and atomic, and a mid-walk **abort** simply
leaves the last `init` result on disk with `status: unratified`, so a re-run
resumes from exactly the recorded decisions (see review mode above). Flush the
JSON through `init` after each decision (or batch a few and flush) so an abort
never loses a recorded decision.

**Ratify.** Once every non-VERIFIED claim carries a `resolution` and every
concern/seam is decided, perform the one-way transition. `baseline.py ratify`
is the single call that both flips `unratified -> ratified` **and renders
`ARCHITECTURE.md`** (the human twin) — do NOT separately call `render-doc`:

```
python3 ~/.claude/scripts/baseline.py ratify <baseline_path> --by "<operator name>"
```

If any non-VERIFIED claim still lacks a resolution, `ratify` **exits 2** and
lists the blockers one per line as `CL-NNN: <reason>`. That is not an
infrastructure failure — it means the matrix walk missed a cell. Re-enter the
walk for each listed `CL-NNN`, record the missing resolution through `init`
(above), and re-run `ratify`. On exit 0 the baseline is `ratified`,
`ratified_by` / `ratified_at` are stamped, and `ARCHITECTURE.md` is at the repo
root. Record the ratification (and the ratified-by name) for the completion
report.

### ENFORCE -- ratified rules become machine-checked conformance (native-tool-first)

ENFORCE turns each ratified rule into an automated conformance check. The
posture is **native-tool-first** (ADR-004): rules survive after etc leaves, so
prefer configuring the project's own **fitness-function tool** over shipping etc
code. Route each rule, then report the routing — never silently wire it into the
host's CI.

**Per-rule routing.** For each ratified rule, pick exactly one route and record
its `enforced_by`:

1. **Native fitness-function tool covers the rule class → `enforced_by: native`.**
   If the project already runs a tool whose rule class covers this rule
   (illustrative, not a hardcoded list: a module-boundary linter, a
   dependency-graph checker, an import-restriction lint rule, an
   architecture-test harness), generate the rule into that tool's own config.
   The config is written through the normal hooked Edit/Write path (all existing
   gates active) and shown in the report. The rule's `enforced_by` is `native`.

2. **Mechanizable but no native tool fits → `enforced_by: generated`.** If the
   rule fits the v1 mechanizable grammar — *"files matching GLOB must not contain
   NEEDLE"* or *"directory DIR must not contain GLOB files"* (the python profile
   grammar) — but no native tool covers it, record it as a generated-checker rule
   for the per-profile `baseline-verify.sh`. `baseline.py` is the single writer;
   record the rule (and flip its graduation flag) via `append-rule
   --mechanizable`:

   ```
   python3 ~/.claude/scripts/baseline.py append-rule <baseline_path> \
     --statement "<the rule>" --who "<operator name>" \
     --trigger "ratification session" --mechanizable
   ```

   The rule lands with `enforced_by: generated`; the profile `baseline-verify.sh`
   (python reference first; other profiles warn-and-skip) checks it at `/build`
   wave gates via the `baseline-verify.sh` conductor.

3. **Not mechanizable → `enforced_by: human-judgment`.** A rule that no native
   tool expresses and that the v1 grammar cannot mechanize (a judgment-bearing
   rule like "side effects must be isolated") is recorded as `human-judgment`:
   captured in the baseline and surfaced at review, never falsely automated.
   Record it via `append-rule` **without** `--mechanizable`.

**The completion report names per-rule routing and recommends — never performs —
host-CI wiring.** For ENFORCE, the report MUST list each rule with its route
(`R-NNN → native: <tool>` / `R-NNN → generated: profile baseline-verify` /
`R-NNN → human-judgment`). etc writes the native-tool config and records the
generated/human rules, but it **never performs** the host-CI wiring that would
run these checks in the project's pipeline — it **recommends** the wiring (e.g.
"add `baseline-verify` to your CI's pre-merge gate; the generated lint config is
at `<path>` — wire it into your existing lint step") and leaves the change to the
operator. Silently mutating a team's CI pipeline is out of scope; the operator
decides.

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
   (illustrative; not exhaustive: per-transaction uptime requirements,
   settlement-window latency, reconciliation cadence).

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
over the other (illustrative phrasing: "Your DOMAIN.md implies strong
bounded contexts, so I'd recommend creating Tier 2 now"). But the
actual question MUST go
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

`cp -n` is no-clobber: if `roles/backend-dev.yaml` already exists (for
any reason — prior experiment, manual edit, earlier partial run), it
is preserved untouched and the other four manifests are still created.

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
`/init-project` completes (the complete set of category-b post-init files:
`DOMAIN.md`, `PROJECT.md`, `CLAUDE.md`, `docs/prds/`, `docs/plans/`,
`docs/sources/`, `docs/standards/`, `docs/guides/`, and — if the user
opted in at Phase 3 Step 2 — `docs/adrs/`, `docs/contexts/`,
`docs/invariants/`). If a template references a file that does not match
this invariant, stop and report the drift -- this is a template bug, not
a user problem.

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

## Definition of Done

`/init-project` is done for a given invocation when ALL of the following
observable artifacts exist and pass:

1. `DOMAIN.md` exists at repo root, is non-empty, and contains every one
   of the nine required sections in the specified order: Domain, Core
   Problem, Revenue Model, What It Does, Operational & Regulatory
   Constraints, Product Core, What It Is Not, Risk Posture, Design
   Implications.
2. `PROJECT.md` exists at repo root, is non-empty, and is not flagged
   as a Phase 1 placeholder stub (the "placeholder" comment from
   Phase 1 Step 1 has been replaced).
3. `CLAUDE.md` exists at repo root. If it existed before the run, it
   was preserved or merged per the user's `AskUserQuestion` answer in
   Phase 2 Step 7 — never silently overwritten.
4. The five Tier 1 directories exist with README stubs:
   `docs/prds/README.md`, `docs/plans/README.md`,
   `docs/sources/README.md`, `docs/standards/README.md`,
   `docs/guides/README.md`. Each stub is byte-identical to its
   template source under `skills/init-project/templates/tier-1/`
   (verify with `diff`).
5. `roles/README.md` exists and is byte-identical to
   `skills/init-project/templates/roles-README.md`.
6. All five role manifests exist under `roles/`: `sem.yaml`,
   `architect.yaml`, `backend-dev.yaml`, `frontend-dev.yaml`,
   `code-reviewer.yaml`. Each manifest is byte-identical to its
   template source under `skills/init-project/templates/roles/`
   (unless the file pre-existed and was preserved by `cp -n`).
7. Every role manifest parses as valid YAML and contains a
   `default_consumes` block and a `discovery` block with an
   `allowed_requests` field. No manifest contains a `forbids` block —
   the soft-POLA pattern uses defaults + discovery, not denials.
8. If Phase 1 ran, `.meta/description.md` exists at repo root and was
   written by the dispatched `project-bootstrapper` agent (not by
   `/init-project` in its own context).
9. If Phase 1 ran, the two Phase 1 placeholder stubs for `DOMAIN.md`
   and `PROJECT.md` have been overwritten by Phase 2 (their
   "placeholder" comment text no longer appears in either file).
10. The Completion Report has been rendered with every phase marked
    run, skipped, or deferred — one line per phase — and with the
    `created_files[]` and `skipped_files[]` lists fully enumerated.
11. The Post-Completion Guidance block has been rendered.

If any of the eleven items is not satisfied, `/init-project` is NOT
done, regardless of how many phases reported success individually. Do
not render the Completion Report as "complete" unless every item holds.

## Constraints

- Phase 1 MUST use the Agent tool with `subagent_type: "project-bootstrapper"`.
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
