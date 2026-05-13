# etc — Engineering Team, Codified

**etc** is Heavy Chain Engineering's harness for AI-assisted software development. It encodes how a senior engineering team works — Socratic specification, test-driven development, recursive decomposition, defense in depth — as Claude Code skills, agents, and enforcement hooks. Install it once and the same disciplines govern work in any repository you point Claude Code at.

The name stands for **Engineering Team, Codified**. The team being codified is HCE. The harness is what we share with selected partners and customers when we extend our way of working into their codebase.

---

## Who this is for

etc is built for **mixed teams**. Different roles use the same harness without stepping on each other:

- **Product Managers** specify features through guided Socratic questioning rather than blank-page PRDs. `/spec` runs the conversation.
- **Subject Matter Experts** file domain requests that get pulled, scoped, and either built or returned with specific clarifying questions. `/pull-tickets` reads from Linear.
- **Designers** capture user flows, design tokens, and component specs. `/design` is the dedicated phase — it wraps [pbakaus/impeccable](https://github.com/pbakaus/impeccable) for Socratic design-context capture (PRODUCT.md + DESIGN.md) and a browser-extension iteration loop. Output feeds `/spec`.
- **Architects** turn specs into architecture and ADRs. `/architect` is the dedicated phase.
- **Engineers** decompose, dispatch, build, verify, and ship. `/build` runs the conductor pipeline.

You do not need to fill all of these roles. Most teams start with `/spec` and `/build` and pick up other skills as needs grow. The harness adapts to who is in the room.

---

## The lifecycle

```
strategy (business)
        ↓
    research
        ↓
  design  │  strategy     ← branch: user-facing surface OR internal/infra
        ↓                   (/design wraps pbakaus/impeccable)
      spec
        ↓
   architect
        ↓
     build
        ↓
    release
```

Four phases are fully built today: **design**, **spec**, **architect**, and **build**. `/design` wraps [pbakaus/impeccable](https://github.com/pbakaus/impeccable) (Apache 2.0) and runs on the design side of the mid-funnel `(design | strategy)` branch — replacing the previous `ux` / `ui` placeholders. The strategy branch (front-of-funnel and the non-user-facing mid-funnel) is a workflow for now, not a skill.

| Phase | What you get | Skill |
|---|---|---|
| **Discover** *(brownfield, optional)* | system-portrait, dependency-map, complexity assessment | `/discovery` |
| **Roadmap** *(strategic, optional)* | phased plan with entry/exit criteria | `/roadmap` |
| **Design** *(wraps pbakaus/impeccable)* | PRODUCT.md, DESIGN.md, design-tokens.json, component-specs.md | `/design` |
| **Spec** | spec.md — requirements, ACs, edge cases, value hypothesis | `/spec` |
| **Architect** | design.md — architecture, data model, APIs, ADRs | `/architect` |
| **Build** | working code, green tests, audit trail | `/build` |
| **Maintain** | hotfix incidents, prevention rules | `/hotfix`, `/postmortem` |

---

## Quick start

```bash
git clone <repo-url>
cd etc-system-engineering

# 1. Compile the SDLC specification into deployable artifacts.
python3 compile-sdlc.py spec/etc_sdlc.yaml

# 2. Install into Claude Code.
./install.sh    # Choose option 1 for Claude Code

# 3. Restart Claude Code. The harness is active.
```

Three steps. The compile is sub-second; the install merges hooks into your existing `~/.claude/settings.json` and copies skills, agents, and standards into place.

### Verify it works

```bash
uv sync          # Install test dependencies
uv run pytest    # 800+ contract tests, ~25 seconds
```

Then in Claude Code, try editing a `src/` file in a real project without writing a test first. The TDD hook will block the edit and tell you why. That is the harness working.

### Your first session

Open Claude Code in any project. Type:

```
/spec "Add user authentication"
```

You will see, in order:

1. Six Socratic questions (problem, users, success criteria, scope boundaries, constraints, your role) — one at a time, with full reasoning between answers.
2. Phase 2 research running in parallel: codebase grep for adjacent patterns, web search for documented patterns and OWASP-relevant considerations, antipatterns lookup.
3. Phase 2.75 classification verdict: well-specified, research-assisted, or rejected.
4. Gray-area resolution if needed (one decision at a time, multi-choice).
5. Section-by-section PRD drafting with per-section approval.
6. A Definition-of-Ready check.
7. Final artifacts written to `.etc_sdlc/features/F<NNN>-add-user-authentication/`, plus a git tag `etc/feature/F<NNN>/spec`.

That is a complete spec session. From there:

```bash
/architect .etc_sdlc/features/F<NNN>-add-user-authentication/
/build     .etc_sdlc/features/F<NNN>-add-user-authentication/spec.md
```

`/spec` auto-detects engineering implications and offers to chain `/architect` automatically. If you are a PM or SME working on intent only, you can stop after `/spec` and let an architect or engineer take it forward.

---

## What ships with it

| Layer | What | Where |
|---|---|---|
| **Skills** | 16 workflows (`/spec`, `/architect`, `/build`, `/discovery`, `/hotfix`, …) | `skills/<name>/SKILL.md` |
| **Agents** | 24 role specialists (sem, architect, backend-developer, security-reviewer, …) | `agents/<name>.md` |
| **Standards** | Engineering rules every role inherits | `standards/<category>/*.md` |
| **Hooks** | Mechanical enforcement on Claude Code lifecycle events | `hooks/*.sh` |

A skill calls an agent. An agent reads the standards. A hook blocks the agent if the standard is violated. The combination produces a senior engineering team's discipline in a codebase that does not yet have one — and gives our own engineers the same scaffold every time, on every project.

---

## Skills you will actually use

Skills are slash commands. Each lives at `skills/<name>/SKILL.md` — read those directly when you want the full contract. Highlights below.

### `/design`
The impeccable wrap. Runs on the design side of the `(design | strategy)` mid-funnel branch — before `/spec` — and is the first phase to allocate the feature directory. Phase 1 detects PRODUCT.md + DESIGN.md at repo root: if absent, dispatches `/impeccable teach` via the Skill tool (auth-context-preserving, never subprocess) for Socratic design-context capture; if present, surfaces a Pattern A entry picker (Accept / Refine PRODUCT / Refine DESIGN / Start over). Mirrors `/architect`'s 5-phase shape with `gray-areas-design.md` covering etc-specific concerns impeccable does not natively address (WCAG floor, motion-reduction, responsive breakpoints, user-flow state machines). A **file-watch contract** bridges impeccable's browser-extension iteration loop back to /design's state: the extension writes designer-decision deltas to `~/.impeccable/last-session.json` (or per-feature `<feature_path>/design-iteration.json`); `/design --sync` pulls them in. Conditional tier-0 promotion of PRODUCT.md + DESIGN.md fires only when the feature has a user-facing surface. Output: `design-tokens.json`, `component-specs.md`, `gray-areas-design.md`, `state.yaml.design_phase`, plus `etc/feature/F<NNN>/design/{start,done}` tags. Consumed by `/spec` Phase 2 research and `/build` Step 6 dispatch.

### `/spec`
Socratic specification loop. Six clarifying questions, parallel research (codebase + web + antipatterns), three-state classifier (proceed / research-assisted / reject), section-by-section drafting with per-section approval. Auto-detects engineering implications and offers to chain `/architect`. Output: `spec.md`, `value-hypothesis.yaml`, `gray-areas-spec.md`, `research/`, plus a git tag.

### `/architect`
Architecture design loop. Mirrors `/spec`'s shape — five phases, three-state classifier, gray-area resolution, per-section approval. Output: `design.md` (architecture overview, data model, API contracts, module structure, technical constraints, security considerations, trade-offs) + zero or more ADRs + `gray-areas-architect.md`. Run after `/spec`; consumed by `/build`.

### `/build`
The conductor. Eight steps from spec to verified working code. Validates the spec, decomposes recursively, plans waves with file-set isolation, dispatches one Agent tool call per leaf task per wave, runs full CI plus an adversarial spec-enforcer review, writes `verification.md` and `release-notes.md`, lays down a release tag. Resumable via `/build --resume` if a session dies mid-pipeline. **Multi-wave builds emit a stack of thin PR layers** (one squash-commit per wave, <500 LOC target per layer) via gh-stack — see F010 below. Single-wave builds ship as a conventional single PR.

### `/discovery`
Archaeological investigation of an existing system. Reads code, data, git history, and infra config; pretends the docs do not exist; tells you what the system *is*. Stateful and resumable — writes findings to disk continuously. Use when joining a brownfield codebase or when you suspect documentation has drifted from reality.

### `/roadmap`
Strategic planning that refuses fuzzy targets. Five-phase interrogation (Why / What / Boundaries / Constraints / Validation), then a phased roadmap with entry/exit criteria. Each roadmap phase becomes input to `/spec`. Pairs explicitly with `/discovery` for current-state input.

### `/hotfix`
Incident response lane. Use when production is on fire and the normal `/spec → /architect → /build` ceremony is too slow. Files an incident under `.etc_sdlc/incidents/`, dispatches a constrained `hotfix-responder` once. Bypasses some development gates (TDD, enough-context, phase-gate) at the manifest layer; `safety-guardrails`, `tier-0-preflight`, and `check-invariants` continue to fire. A postmortem-debt banner stays visible until you run `/postmortem`.

### `/postmortem`
Trace an escaped bug to root cause and append a prevention rule. Runs after every `/hotfix`; also runs standalone on any escaped bug. Produces an entry in `.etc_sdlc/antipatterns.md` keyed by class of bug, with the gate that should have caught it. Future `/spec` invocations on the same project read this file in Phase 2 and incorporate the prevention rule.

### `/pull-tickets`
Closed-loop ticket pipeline. Pulls Linear tickets via MCP, generates PRDs from ticket content plus codebase research, runs `/build`, creates PRs on success, or returns the ticket to the source with specific tactful clarifying questions on failure. Source-aware rejection routing — feedback reaches the SME in the tool they actually use. `--triage-only` analyses the board without building. `--concurrency N` processes up to N tickets in parallel.

### `/metrics`
Three-layer outcome report. Process layer reads git tags. Outcome layer reads `value-hypothesis.yaml` files. Cost layer reads `.etc_sdlc/telemetry.db`. Headline metric: **% hypothesis-validated**, broken down by author role (SME / Engineer / PM / Designer / Other). Anti-Goodhart by construction — the harness writes the source data automatically, so the numbers cannot be hand-curated.

### `/init-project`
Bootstrap any repo into a state where the harness can operate on it. Creates `DOMAIN.md`, `PROJECT.md`, `CLAUDE.md`, role manifests, and a tiered docs skeleton. Idempotent — re-runs on an initialized repo produce zero changes. The `tier-0-preflight` hook blocks all Edit and Write operations until this has run.

### `/harness-feedback`
Cross-project lesson capture. When a process failure observed in *any* project should change the harness itself — a research inversion, a wasted half-hour, a manual workaround, a framework surprise, a near-miss gate, a repeated mistake. Routes a structured feedback block directly to a `/spec` brief when invoked inside this repo.

### Plus
`/decompose`, `/implement`, `/tasks`, `/checkpoint`, `/retrospective`. See `skills/<name>/SKILL.md` for each.

---

## Theory: how we think about this

A handful of ideas hold the harness together. These are the principles you will keep meeting.

### Output IS state
Skills write findings, decisions, and progress to disk *continuously* rather than holding them in agent context. Sessions die, blockers pause work for hours, agents compact. A resume picks up exactly where it stopped because the artifacts ARE the state. Real client investigations span hours or days; access is fragmented; the agent that started the work is rarely the agent that finishes it. State on disk, not in context, is what makes the harness durable.

### The three-state PRD classifier
`/spec` does not blindly accept every input. After Phase 2 research, it classifies the input into one of three states:

- **Well-specified** — proceed straight to drafting.
- **Research-assisted** — codebase or web research filled the gaps with citations; the user reviews fills during section approval.
- **Rejected** — too many unfillable gaps; `rejected.md` is written with specific questions; `spec.md` is *not* written.

This saves agent-hours on under-specified inputs. A vague one-liner that would have produced a vague PRD now produces a rejection report with the questions the human needs to answer first. The same classifier runs again in `/architect`.

### Outcome metrics, not just outputs
Every `/spec`-produced feature carries a `value-hypothesis.yaml` predicting what success looks like — `who`, `current_cost`, `predicted` (metric / direction / threshold), and `how_we_know`. `/metrics` reads those hypotheses, the per-project telemetry DB, and the git lifecycle tags, and tells us whether the prediction held.

We build features that do not move the needle all the time. The harness makes that structurally visible. When a fractional CTO is billing by the hour, every feature that ships and does not matter is a problem you need to see.

### Defense in depth
When a class of bug escapes, the response is layered enforcement at multiple SDLC phases — never a single fix. F001 (spec-time), F002 (verify-time), and F003 (dispatch-time) are the canonical example: the same root cause (orphan user-facing surfaces) is now defended at acceptance-criterion authorship, adversarial review, AND task dispatch. F007 (verify-time stub grep) and F008 (plan-time implicit-dependency rejection) repeat the pattern for stub markers and missing dependencies. Three independent gates have to fail for any of these classes of bug to recur.

### Forward-only
New rules apply to new artifacts. Legacy specs are never silently rewritten. Legacy task files do not retroactively gain new fields. Turnaround engagements often involve large bodies of historical work that we cannot afford to invalidate, and HCE has been bitten by retrofit-everything migrations enough times to know better.

### Source of truth + compile model
Everything flows from `spec/etc_sdlc.yaml`. The compiled `dist/` tree is regenerated from that file by `compile-sdlc.py`; never edit `dist/` directly. Edits to skills, agents, standards, or hooks happen in their source files referenced from the YAML; one `python3 compile-sdlc.py spec/etc_sdlc.yaml && ./install.sh` cycle deploys the change.

---

## What has been shipping

Recent features, newest first. Each is a fully shipped PRD with tests, audit trail, and verification report.

| Feature | What changed |
|---|---|
| **F012** | Auto-checkpoint Stop hook. `hooks/auto-checkpoint.sh` blocks session-end (exit 2) when `context_window.used_percentage >= 85` AND `.etc_sdlc/checkpoint.md` is more than 30 min stale (or absent), forcing the model to run `/checkpoint` before stopping. Mechanizes what was a passive "suggest at 60%" rule. Threshold defaults are tuned for opus 1M-context windows; tunable via `CHECKPOINT_CTX_THRESHOLD` and `CHECKPOINT_STALE_MINUTES` env vars. Opt-in: install copies the script, operator pastes the JSON snippet into `~/.claude/settings.json` (denyWrite policy; install.sh emits the paste hint as INFO output). |
| **F011** | `/design` phase wraps impeccable. Adds Socratic design-context capture via `/impeccable teach`, conditional tier-0 promotion of PRODUCT.md + DESIGN.md, file-watch designer-iteration loop. Deprecates homeless `ux-designer` + `ui-designer` agents. |
| **F010** | `/build` emits stacked PRs — one squash-commit per wave on a layered branch chain via `gh-stack`. Soft warning at 500 LOC/layer. Single-wave builds skip stacking and ship as a single PR. Attacks the 4-hour-reconciliation pain at agentic-AI scale. |
| **F006** | `/spec` and `/architect` are now distinct phases. PMs can spec without writing architecture; architects can design without re-running intent capture. `/spec --include-architect` chains both. |
| **F009** | Two-state directory lifecycle — `features/active/` and `features/shipped/`, plus a separate `.etc_sdlc/rejections/` location. Forward-only; existing flat-path features remain in place. |
| **F008** | `/build` wave planner rejects implicit dependencies at plan time via file-set overlap detection. |
| **F007** | spec-enforcer greps deliverables for stub markers (`TODO`, `FIXME`, etc.) at verify time. |
| **F005** | `/build` writes per-phase completion reports with AC pass/fail, deferred items, and known gaps. |
| **F004** | Windows install + compile compatibility fixes. |
| **F003** | Orphan-surface dispatch-time wiring contract — third-layer defense in depth. |
| **F002** | spec-enforcer reachability evidence at verify time — second-layer defense. |
| **F001** | User-flow completeness at spec time — first-layer defense. |

---

## Repository structure

| Path | Contents |
|---|---|
| `agents/` | Agent definitions. One markdown file per role. `agents/design.md` is the unified design agent (introduced in F011); `agents/ux-designer.md` and `agents/ui-designer.md` are deprecated forward-only — files remain on disk so F001-F010 references resolve, but new specs reference `agents/design.md`. |
| `skills/` | Skill definitions. One subdirectory per skill, each with `SKILL.md`. |
| `standards/` | Engineering standards organised by tier: `process/`, `code/`, `testing/`, `architecture/`, `security/`, `quality/`, `git/`. |
| `hooks/` | Bash scripts that fire on Claude Code lifecycle events (PreToolUse, SubagentStart, Stop, etc.). |
| `spec/etc_sdlc.yaml` | The master harness configuration. Single source of truth. |
| `spec/.drafts/` | In-progress spec drafts, written by `/spec` between sections. Resumable. |
| `dist/` | Compiled output. Generated by `compile-sdlc.py`. **Do not hand-edit.** |
| `tests/` | Contract tests. ~800. Pytest, ~25 seconds. |
| `scripts/` | Python helpers (`feature_id.py`, `value_hypothesis.py`, `git_tags.py`, `tasks.py`). Called from skills via Bash. |
| `templates/` | Artifact templates: ADR, agent definition, task YAML, invariant entry. |
| `compile-sdlc.py` | The compiler. Reads YAML, writes `dist/`. |
| `install.sh` | The installer. Copies `dist/` into `~/.claude/`, merges settings hooks. |
| `.etc_sdlc/features/F<NNN>-<slug>/` | Per-feature work directories. **Gitignored everywhere, including this repo** — the durable git-tracked artifact is `spec/<slug>.md` (a byte-identical copy of the PRD) plus the `etc/feature/F<NNN>/*` git tags. Feature directories are persistent on the developer's machine and reconstructable from git tags + spec copies if needed. |

---

## What a feature directory looks like

```
.etc_sdlc/features/F006-spec-architect-split/
  spec.md                      ← the PRD (post-/spec)
  design.md                    ← the architecture (post-/architect, when present)
  value-hypothesis.yaml        ← outcome contract: who / current_cost / predicted / how_we_know
  state.yaml                   ← pipeline state — resumable; classification, author roles, step_completed
  gray-areas-spec.md           ← /spec design decisions captured with rationale + citations
  gray-areas-architect.md      ← /architect design decisions (when /architect ran)
  rejected.md                  ← only on rejected path; mutually exclusive with spec.md
  research/
    codebase.md                ← grep findings, adjacent patterns, INVARIANTS hits
    web.md                     ← OWASP, RFCs, library docs
    antipatterns.md            ← relevant entries from .etc_sdlc/antipatterns.md
    architect-codebase.md      ← /architect-specific research (when /architect ran)
  tasks/
    001-…yaml                  ← leaf tasks for the wave plan
    002-…yaml
  verification.md              ← final QA report (post-Step-7 of /build)
  release-notes.md             ← auto-generated rollup (post-release tag)
```

Plus git tags written by the harness:

| Tag | Written by | Marks |
|---|---|---|
| `etc/feature/F<NNN>/spec` | `/spec` Phase 5 | Spec finalized and DoR-passing |
| `etc/feature/F<NNN>/architect/start` | `/architect` Phase 1 | Architecture phase entered |
| `etc/feature/F<NNN>/architect/done` | `/architect` Phase 5 | Architecture finalized |
| `etc/feature/F<NNN>/build/phase-N/start` | `/build` per phase | Phase N entered |
| `etc/feature/F<NNN>/build/phase-N/done` | `/build` per phase | Phase N exited cleanly |
| `etc/feature/F<NNN>/release` | `/build` Step 8 (terminal) | Feature shipped |

These tags are how `/metrics` reconstructs the process layer of the weekly report. They are also load-bearing for partner handoffs: when we pass a project back to a client, the F<NNN> directory plus the tag history *is* the audit trail.

---

## Daily workflow examples

### Scenario A — A PM specs a feature

```
You:    /spec "Add SSO via Okta"

etc:    [Phase 1] Six questions, one at a time.
You:    Answer each. Last question: "What's your role?" → PM.
etc:    [Phase 2] Research dispatched in parallel; F<NNN>-add-sso-via-okta
        directory allocated.
etc:    [Phase 2.75] Classification: research-assisted (5 gaps; 4 filled by web,
        1 unfillable).
etc:    [Phase 2.5] Gray-area picker for the unfillable gap.
You:    Choose.
etc:    [Phase 3] Section-by-section PRD draft.
You:    Accept each section.
etc:    [Phase 4] DoR check passes.
etc:    [Phase 5] value-hypothesis.yaml + spec.md + gray-areas-spec.md written.
        Detected engineering implications. Offers to chain /architect.
You:    "Yes, but later — let an architect run /architect when ready."
etc:    spec_phase complete. Tag laid down. Hands off.
```

### Scenario B — An architect designs the implementation

```
You:    /architect .etc_sdlc/features/F<NNN>-add-sso-via-okta/

etc:    Reads spec.md. Phase 1 architecture intent capture (boundaries,
        integration patterns, security model).
You:    Answer.
etc:    Phase 2 research (codebase auth patterns, web for SSO best practices,
        ADR review).
etc:    Phase 2.75 classification, Phase 2.5 gray-area resolution.
etc:    [Phase 3] design.md drafted section by section: architecture overview,
        data model, API contracts, module structure, technical constraints,
        security considerations, trade-offs.
You:    Accept each section.
etc:    [Phase 5] design.md + gray-areas-architect.md written. ADRs proposed
        (two qualified — token storage, session policy). Hands off to /build.
```

### Scenario C — An engineer builds the feature

```
You:    /build .etc_sdlc/features/F<NNN>-add-sso-via-okta/spec.md

etc:    [Step 1] VALIDATE — sees state.yaml.classification = research-assisted,
        rubber-stamps DoR. Reads design.md if present.
etc:    [Step 2] SETUP.
etc:    [Step 3] DECOMPOSE.
etc:    [Step 4] SCORE/RECURSE — task scoring > 7 decomposed further.
etc:    [Step 5] PLAN WAVES — file-set isolation verified.
        Wave 0: 3 tasks (parallel-safe)
        Wave 1: 2 tasks
        Wave 2: 1 task
etc:    [Step 6] EXECUTE — per wave, dispatches one Agent tool call per task.
        backend-developer writes tests first (TDD hook enforces),
        then implementation. After each wave, watchdogs run:
        code-reviewer + verifier + security-reviewer.
etc:    [Step 7] VERIFY — full CI, spec-enforcer adversarial pass, architect
        review.
etc:    [Step 8] REPORT — verification.md, release-notes.md, release tag.
```

### Scenario D — Production is on fire

```
You:    /hotfix "POST /api/users returns 500 after 14:30 deploy"

etc:    Recursion guard, single-lock check, path-traversal guard.
etc:    Severity picker (S0 / S1 / S2) and rollback availability.
You:    S1, rollback available.
etc:    Writes incident.md with frontmatter (failure type, system, hypothesis),
        dispatches hotfix-responder once with the constrained brief.

hotfix-responder: Reads the failing endpoint, the recent diff, the integration
                  tests. Identifies a missing migration. Applies the fix.
                  safety-guardrails, tier-0-preflight, check-invariants all
                  fired and passed. tdd-gate, enough-context, phase-gate were
                  bypassed at the manifest layer (audited).

etc:    Phase 5 completion summary. Banner reminds you to run /postmortem
        before this incident is closed. The banner stays visible.

You:    /postmortem

etc:    Walks you through root cause, identifies which gate should have caught
        the bug, drafts an entry in .etc_sdlc/antipatterns.md. Future /spec
        invocations on this project will read this file and incorporate the
        prevention rule.
```

---

## Configuration and customization

### Editing the harness

Edit `spec/etc_sdlc.yaml` (or a file it references), then:

```bash
python3 compile-sdlc.py spec/etc_sdlc.yaml
./install.sh
# Restart Claude Code.
```

The compiler is fast. Make this muscle memory.

### Hooks are wired via `~/.claude/settings.json`

The installer merges the compiled `dist/settings-hooks.json` into your existing `settings.json`. The `hooks` section is replaced wholesale; the rest of your settings are preserved.

### Model overrides

Each gate, skill, or agent can specify its own model in the YAML. Defaults: sonnet for judgment-bearing gates, haiku for mechanical command hooks, opus for the strongest verification (final `/build` Step 7 review). **Never hardcode a specific model in a skill body or agent prompt** — model choice belongs in the YAML.

### Forward-only by design

New rules apply to new artifacts. Legacy specs are never silently rewritten. Adapt to this discipline; do not fight it.

---

## Troubleshooting

### Hooks affecting other projects
Today, `install.sh` installs globally to `~/.claude/`, so etc's hooks fire on Claude Code sessions in *every* project on your machine. A project-scoped install option (`--scope project`) is on the roadmap. For now, if you need a Claude Code session free of etc, you can move `~/.claude/settings.json` aside, restart Claude Code, and restore when you are done.

### Sandbox restrictions during install
If `./install.sh` fails with permission errors writing to `~/.claude/`, ensure your shell has access to that path. On macOS with strict sandbox settings, you may need to grant Terminal full-disk access or run from a different shell.

### Stale `dist/` after edits
Symptom: you edited something but the harness behaviour did not change. Cause: forgot to recompile and reinstall. Fix:

```bash
python3 compile-sdlc.py spec/etc_sdlc.yaml
./install.sh
# Restart Claude Code.
```

### `tier-0-preflight` blocking everything
You do not have `DOMAIN.md` and `PROJECT.md` at the project's repo root. Run `/init-project` to create them. Read-only exploration (Read, Grep, Glob, Bash) is unblocked so the agent can gather the context it needs to create the missing files.

### TDD hook blocking the first edit
If the TDD hook blocks an edit on a fresh module that has no test yet, write the test first. That is the rule. If the change has no testable surface (config, docs, infra), the hook recognises file-extension exemptions — see `hooks/check-test-exists.sh` for the list.

### `.etc_sdlc/features/` is gitignored in client repos
Per-feature work directories live under `.etc_sdlc/features/F<NNN>-<slug>/` and are gitignored in client repos by default. Each feature's working artifacts are durable on the developer's machine but should not be committed back to the client's tree unless you explicitly want them there. The release tag and (optionally) `release-notes.md` are what ships back, not the full feature directory. In *this* repo (etc-system-engineering), feature directories *are* committed because the harness's own work is the source of truth for its audit trail.

---

## Where to learn more

In rough order of value per minute spent:

| What to read | When |
|---|---|
| `standards/process/sdlc-phases.md` | First. The harness's playbook. |
| `standards/process/interactive-user-input.md` | Before writing or modifying any skill. Pattern A vs Pattern B is load-bearing. |
| `standards/process/research-discipline.md` | Before debugging any third-party framework. Calm, technical, opinionated. |
| `standards/process/incident-response.md` | Before running `/hotfix` for the first time. |
| `skills/spec/SKILL.md` | Socratic loop in full detail. |
| `skills/architect/SKILL.md` | Architecture phase in full detail. |
| `skills/build/SKILL.md` | Conductor in full detail. |
| `agents/sem.md` | The orchestrator's responsibility chart. |
| `compile-sdlc.py` | Heavily commented. Source → compile → install lifecycle. |
| `.etc_sdlc/features/F006-spec-architect-split/spec.md` | A real shipped PRD, written by `/spec`. The shape every spec converges to. |
| `.etc_sdlc/features/F003-orphan-surface-dispatch-gate/spec.md` | The defense-in-depth third layer, paired with F001 and F002. Read all three to see how the harness layers enforcement. |

The skills, agents, and standards are all plain markdown. They are meant to be read.

---

## A note to partners and customers

If you are reading this because Heavy Chain Engineering has invited you in: welcome. The harness is internal in the sense that we built it for ourselves, but it is not secret. It encodes how we work — disciplines learned the hard way over many turnaround engagements — and the parts that are mechanically enforceable are enforced. We share it with selected partners and customers because the same disciplines tend to be useful wherever software is being built under pressure.

If something in the harness contradicts how your team works, that is a real conversation to have. We are not trying to impose a process; we are trying to make a known-good process portable. The skills, agents, and standards are all editable. The compile-and-install loop is fast. Adapt where you need to. But adapt deliberately, and read the standards first — most of what looks arbitrary is load-bearing.

---

## Closing

The kind of engineering this codifies: tests-first because tests are the specification; specifications written under cross-examination because vague intent produces vague code; decompositions that go as deep as the problem requires because some problems are larger than one agent's context window; outcomes measured because shipping is not the same as moving the needle; and defense in depth because every shipped bug is a failure of multiple gates simultaneously, and the response is to add gates.

If something the harness does feels wrong, file `/harness-feedback`. The harness improves the same way the work does — by writing things down and acting on what we learn.
