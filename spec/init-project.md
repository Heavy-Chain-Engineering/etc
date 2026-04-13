# /init-project — Unified Project Initialization

**Status:** Design sketch
**Date:** 2026-04-13
**Owner:** ETC harness

## Purpose

`/init-project` is the **single entry point** for bootstrapping any repository the ETC harness will operate on. It produces, in sequence:

1. A technical scaffold (gitleaks, linting, testing, pre-commit hooks, CI)
2. A domain scaffold (`DOMAIN.md`, `PROJECT.md`, `CLAUDE.md`)
3. A documentation directory skeleton (Tier 1 always, Tier 2 on prompt)
4. A role manifest seed (`roles/` with starter templates)

After it runs, the `tier-0-preflight` hook stops blocking, the role manifest loader has something to load, and the first `/build` invocation has the context substrate it needs.

Before it runs, the harness is unusable. That is deliberate — projects that skip this step silently fabricate business assumptions, and "incapable of wrong" starts with "incapable of operating without grounding."

## Relationship to the existing technical scaffolder

The user already has a technical project scaffolder skill that installs gitleaks, linters, pre-commit hooks, CI skeletons, and other "best practices you always forget." **`/init-project` composes with it rather than replacing it.** Phase 1 delegates to the existing scaffolder (or runs it inline if not installed separately). Phase 2 and beyond are new work that only `/init-project` owns.

This composition follows the "single entry point" principle: users run one command, and the right things happen in the right order. No "which skill do I run first?" decision.

## Phases

### Phase 1 — Technical scaffold

**What it does** (delegated to existing scaffolder):
- `.gitleaks.toml` + pre-commit hook
- `.editorconfig`, `.gitignore` (language-aware)
- Linter + formatter config (ruff, prettier, etc.)
- Test runner config (pytest.ini, vitest.config, etc.)
- CI workflow skeleton (GitHub Actions / similar)
- pre-commit framework hooks
- Language-specific baseline (pyproject.toml, package.json, etc.)

**Idempotent:** if the scaffold already exists, phase 1 reports "already present" and moves on. Never overwrites.

**Gating:** phase 2 requires phase 1 to have completed successfully. If phase 1 fails, stop — do not scaffold domain on top of a broken technical baseline.

### Phase 2 — Domain scaffold

**What it does:** creates `DOMAIN.md`, `PROJECT.md`, `CLAUDE.md` at repo root, following the 6-step process from "The Most Important File in Your Repository is domain.md."

**Interactive flow** (the agent asks the user one question at a time, waits for the answer, then proceeds):

1. **"What is the name of the business this codebase serves?"**
   One-line answer. Used as the DOMAIN.md title.

2. **"What domain does this business operate in?"**
   Two-to-four sentences. Not a mission statement — a precise domain description. The agent pushes back on marketing fluff and asks for specificity.

3. **"What is the core problem this business solves?"**
   Including failure modes: what happens when it gets it wrong. This directly informs the risk posture section.

4. **"How does the business make money?"**
   Revenue model, retention drivers. Keeps architectural decisions aligned with commercial reality.

5. **"What does the business explicitly NOT do?"**
   Boundary-setting. Often more important than "what it does" because it prevents scope creep in agent decisions.

6. **"What are the 5–10 core conceptual entities?"**
   The product core. Nouns, not database tables. The agent generates a draft list from its understanding so far and asks the user to correct it.

7. **Agent proceeds without further questions:** researches the business if a website is provided (via WebFetch), drafts the DOMAIN.md in the blog article's 9-section format, and writes it to `/DOMAIN.md`.

8. **Review loop:** the agent presents the draft and asks "what's wrong, what's missing, what's too generic?" Iterates until the user says it's correct.

9. **PROJECT.md generation:** after DOMAIN.md is locked, the agent inspects the repo (reads README, package.json/pyproject.toml, top-level directories) and generates a first-draft `PROJECT.md` with:
   - What the codebase is
   - Current phase (asks user, defaults to "bootstrap")
   - Where resources live (points into `docs/` structure from phase 3)
   - Tech stack anchors (extracted from config files)
   - Read order for new agents

10. **CLAUDE.md generation:** short file with agent working rules and pointers into `DOMAIN.md` / `PROJECT.md`. Follows the existing ETC harness conventions for CLAUDE.md structure.

**Cost control:** phase 2 should take <30 minutes of interactive time for a project the user already understands, and <2 hours for a brownfield project that requires research. If the agent is spending more time than that, it's an indicator that the user doesn't yet have enough clarity to write DOMAIN.md — and that's valuable information, not a failure.

### Phase 3 — Documentation directory skeleton

**What it does:** creates the Tier 1 directory tree with README stubs that teach their own purpose.

**Tier 1 (always created):**
```
docs/
├── prds/
│   └── README.md          # "PRDs live here. Numbered PRD-NN-{context}.md."
├── plans/
│   └── README.md          # "Dated YYYY-MM-DD-slug.md. Plans are meta-work, not domain truth."
├── sources/
│   └── README.md          # "Ground truth. Cite, never invent. Research, feedback, reference docs."
├── standards/
│   └── README.md          # "Engineering conventions. Coding standards, testing standards, etc."
└── guides/
    └── README.md          # "Runbooks, deployment guides, operational how-tos."
roles/
└── README.md              # "Role manifests. Declarative context projections per agent role."
```

**Each README stub** is ~10 lines: one-line purpose, naming convention, one example filename, and a pointer to `DOMAIN.md` / `PROJECT.md` for orientation.

**Tier 2 (prompted, not default):**
After Tier 1, the agent asks: "Will this project have multiple bounded contexts, ADRs, or cross-cutting invariants?" If yes, creates:
```
docs/
├── adrs/
│   └── README.md          # "Numbered NNN-slug.md. Frontmatter declares affects_contexts."
├── contexts/
│   └── README.md          # "Per-bounded-context taxonomy and PRD grouping."
└── invariants/
    └── README.md          # "Thematic split. Frontmatter: affects_contexts, priority."
```

If no, Tier 2 dirs are skipped entirely — they can be added later when the project climbs into platform territory. **Never scaffold Tier 2 for a marketing site or a toy project.**

**Tier 3 (never scaffolded automatically):** regulated/high-stakes projects need explicit opt-in via `/init-project --tier=3`, which prompts additional questions about compliance, traceability, and source corpus management.

### Phase 4 — Role manifest seed

**What it does:** creates `roles/` with starter manifests for the standard roles the ETC harness uses.

**Created manifests (starter versions, ~60-line YAML each):**
- `roles/sem.yaml` — orchestrator role with broad default projection
- `roles/architect.yaml` — tier 2 consumer, sees ADRs and invariants
- `roles/backend-dev.yaml` — leaf dev with narrow projection + discovery
- `roles/frontend-dev.yaml` — leaf dev, frontend variant
- `roles/code-reviewer.yaml` — read-only role with cross-context visibility

Each starter manifest is annotated with `# EDIT ME` comments where project-specific decisions are needed (e.g., which bounded contexts exist, which ADRs apply). The user is expected to customize these before relying on them.

## Invocation modes

```bash
/init-project              # full flow: phase 1 → 2 → 3 → 4, interactive
/init-project --phase=domain        # skip phase 1 (tech scaffold already exists)
/init-project --phase=skeleton      # just create the Tier 1 dirs + READMEs
/init-project --tier=3              # climb to Tier 3 (regulated domain)
/init-project --non-interactive    # batch mode: read all answers from .etc_sdlc/init-answers.yaml
```

**The preflight hook knows about these modes.** When it blocks, it recommends `/init-project --phase=domain` if technical scaffolding is already detected (via presence of `.pre-commit-config.yaml` or similar).

## Preflight integration

The `tier-0-preflight` hook from step 4 blocks Edit|Write when `DOMAIN.md` / `PROJECT.md` are missing. `/init-project --phase=domain` is the only supported path to unblock it. The hook's error message points directly at this skill:

```
BLOCKED: Tier 0 domain context is missing from repo root.
Fix: run /init-project to scaffold the Tier 0 files.
     If the project already has a technical scaffold,
     run /init-project --phase=domain to generate DOMAIN.md
     and PROJECT.md only.
```

This is the **closed loop at the project-bootstrap level:** the hook detects the gap, names the fix, and the fix exists and is discoverable.

## Worked example — brownfield VenLink re-init

Suppose someone runs `/init-project` on VenLink today (after the reshape already happened).

1. **Phase 1 detects existing scaffold:** gitleaks, pre-commit, ruff, vitest all present. Reports "technical scaffold already complete, skipping."

2. **Phase 2 detects existing DOMAIN.md and PROJECT.md** at repo root. Asks: "DOMAIN.md already exists. Review and update, or skip?" User picks "review." Agent reads current DOMAIN.md, asks "has anything changed in the business in the last quarter?" — iterates if yes, skips if no.

3. **Phase 3 detects existing Tier 1 and Tier 2 directories.** Reports "documentation skeleton already present; no changes."

4. **Phase 4 detects existing `roles/backend-dev.yaml`.** Asks: "One role manifest exists. Generate starter manifests for the other standard roles (sem, architect, frontend-dev, code-reviewer)?" User picks yes, the four new manifests are created with `# EDIT ME` markers.

**Outcome:** `/init-project` is fully idempotent against an already-initialized project. Running it again reveals what's missing and only creates the missing pieces. This is the property that makes it safe to run in CI or as part of a `/build` preflight — it can be invoked repeatedly without risk.

## Open questions

1. **Where does phase 1 delegation live?** Three options:
   - Invoke the existing technical scaffolder as a separate skill via a sub-skill call
   - Re-implement the technical scaffold inline in `/init-project`
   - Extract the technical scaffold into a library that both skills can call
   My preference: (a) delegate. It keeps the existing scaffolder as the source of truth and avoids divergence. Requires ETC to support skill-calls-skill.

2. **Research mode vs. teach-me mode for phase 2.** Two user archetypes:
   - User knows the business deeply: agent asks questions, user provides answers, DOMAIN.md takes 20 minutes.
   - User is inheriting a business: agent needs to do research (WebFetch the company site, analyze competitors) and teach the user as it writes.
   The flows differ significantly. Does `/init-project` detect the mode from the first answer, or does it prompt "teach me about this business, or am I teaching you?"

3. **Can phase 2 be deferred?** If a user wants the technical scaffold immediately but doesn't have time for the interactive DOMAIN.md flow, can they run phase 1 + phase 3 + phase 4 and come back for phase 2 later? Probably yes — but then the preflight hook will block their first edit, which is actually the correct behavior. They can't *use* the repo for code changes until phase 2 completes.

4. **Brownfield research source.** When a user runs this on an inherited codebase, the agent should probably grep the existing code for domain vocabulary and surface it as a starting point for the product core ("I see these nouns appearing in your models: Vendor, Requirement, Policy, Case. Are these the core entities?"). This shortens phase 2 significantly for brownfield projects.

5. **Integration with `closed-loop-ticket-pipeline.md`.** The pipeline spec assumes tickets can enter from multiple sources (Linear, direct conversation). `/init-project` creates the substrate those tickets get resolved against. The relationship between these two specs should be made explicit: tickets come in → check if DoR is met against DOMAIN.md/PROJECT.md → if not, either reject-to-source or run the discovery protocol.

## Required changes to ETC

To implement `/init-project`:

1. **New skill:** `skills/init-project/SKILL.md` with the full interactive prompt and phase orchestration logic.

2. **Template files for phase 2:** `skills/init-project/templates/`
   - `DOMAIN.md.template` — the 9-section scaffold from the blog
   - `PROJECT.md.template` — the orientation structure from VenLink
   - `CLAUDE.md.template` — the agent working rules baseline

3. **Role manifest starter templates:** `skills/init-project/roles/*.yaml.template` — one per standard role.

4. **Sub-skill invocation support:** the harness needs to support skill-calls-skill if phase 1 delegates to the existing technical scaffolder. Alternative: extract common scaffolding logic into a script under `hooks/scripts/`.

5. **Detection logic:** each phase must idempotently detect its own completion state so re-runs are safe.

## Status and next steps

This document is a **design sketch**. Before implementation:

- [ ] Validate phase ordering with the user (phase 1 → 2 → 3 → 4 the right sequence?)
- [ ] Confirm delegation vs. inline for phase 1
- [ ] Confirm the blog article's 6-step flow is what phase 2 should literally ask
- [ ] Decide: does `/init-project` exist as a standalone skill, or does it become the first command in the `/build` conductor?

After validation:
- Write `skills/init-project/SKILL.md` with full prompt
- Author the four template files
- Author the five role manifest starter templates
- End-to-end test: run `/init-project` on a fresh tmp directory, verify the preflight hook unblocks after completion

## What this replaces

- **Ad-hoc "set up the project" instructions scattered across onboarding docs.** Those become a single command invocation.
- **The user's existing technical scaffolder as a standalone entry point.** It still exists as the underlying scaffold, but `/init-project` is the advertised entry point.
- **Manual DOMAIN.md creation.** The interactive flow from the blog becomes executable.
- **Silent project-level fabrication.** Combined with the preflight hook, there is now no valid state where an agent can run code against a repository without Tier 0 context in place.
