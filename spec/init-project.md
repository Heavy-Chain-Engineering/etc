# PRD: /init-project — Unified Project Initialization

## Summary

`/init-project` is the single entry point for bootstrapping any repository into a state where the ETC harness can operate on it. It coordinates the existing `project-bootstrapper` agent (which owns technical scaffolding and `.meta/` tree generation) with four new phases that produce the Tier 0 domain artifacts (`DOMAIN.md`, `PROJECT.md`, `CLAUDE.md`), the tiered documentation skeleton, and starter role manifests.

After successful execution, the `tier-0-preflight` hook stops blocking Edit|Write operations, the role manifest loader has manifests to load, and the first `/build` invocation has the context substrate it needs. Before successful execution, the harness cannot operate against the project — that is deliberate, and is the "fail early and loud" principle applied at the project-bootstrap level.

This skill composes with, rather than replaces, the existing `project-bootstrapper`. Phase 1 delegates to it via the Task tool. Phases 2–4 own the domain/project/docs/roles layers that `project-bootstrapper` does not touch. The division is clean because `.meta/` tree is bottom-up code archaeology while `DOMAIN.md` / `PROJECT.md` are top-down domain framing — different artifacts serving different purposes, coexisting in the same repo.

## Scope

### In Scope

- New skill at `skills/init-project/SKILL.md` with the full interactive prompt and four-phase orchestration logic
- Template files for the three Tier 0 artifacts (`DOMAIN.md`, `PROJECT.md`, `CLAUDE.md`)
- Tier 1 directory README stubs (5 stubs: prds, plans, sources, standards, guides)
- `roles/README.md` stub explaining the role manifest pattern
- Starter role manifest templates for the 5 standard roles (sem, architect, backend-dev, frontend-dev, code-reviewer)
- Delegation to `project-bootstrapper` agent via Task tool in phase 1
- Interactive 6-step DOMAIN.md creation flow matching the blog article format
- Idempotent detection of completed phases (re-run safety)
- Integration with the existing `tier-0-preflight` hook's error messages
- Extension of `compile-sdlc.py` to copy entire skill directories (not just `SKILL.md`), so templates are deployed
- Update to `spec/init-project.md` (the design sketch) to reference this PRD as the authoritative spec

### Out of Scope

- Modifying the existing `project-bootstrapper` agent (it is delegated to as-is)
- Full discovery protocol runtime (separate spec: `spec/discovery-protocol.md`)
- The `/analyze-discovery-log` skill
- Tier 3 regulated-domain scaffolding (future enhancement, opt-in via `--tier=3`)
- Closed-loop ticket pipeline integration (separate spec: `spec/closed-loop-ticket-pipeline.md`)
- Runtime enforcement of role manifest projections (a separate runtime library, not built yet)
- Research mode implementation (WebFetch against a company website) — the interactive flow captures which mode the user wants, but actually performing the research is a follow-up enhancement
- Smoke/integration test scaffolding for the skill (a separate task during `/build`'s verify step)

## Requirements

### BR-001: Four-phase execution order

`/init-project` executes in phase order: Phase 1 (technical scaffold via project-bootstrapper) → Phase 2 (domain scaffold) → Phase 3 (docs skeleton) → Phase 4 (role manifests). Later phases do not run if earlier phases failed. Each phase checks its own preconditions before executing.

### BR-002: Phase 1 delegates to project-bootstrapper via Task tool

Phase 1 does not re-implement scaffolding logic. It invokes `project-bootstrapper` as a subagent using the Task tool with `subagent_type: "project-bootstrapper"`. The agent handles greenfield/brownfield mode detection, tooling installation, and `.meta/` tree generation. On completion, Phase 1 reads the `.meta/` tree to pass brownfield vocabulary into Phase 2.

### BR-003: Phase 2 follows the 9-section DOMAIN.md blog format

The interactive Phase 2 flow produces a `DOMAIN.md` conforming to the 9-section format from the user's "The Most Important File in Your Repository is domain.md" blog article: Domain, Core Problem, Revenue Model, What It Does, Operational & Regulatory Constraints, Product Core, What It Is Not, Risk Posture, Design Implications.

### BR-004: Idempotent execution

Re-running `/init-project` on a repository where some or all phases already completed detects the existing artifacts and skips their creation. No file is silently overwritten. If a Tier 0 file exists, the skill asks: "This file already exists. Review and update, or skip?"

### BR-005: Research mode vs teach-me mode selected upfront

At the start of Phase 2, the skill asks: "Do you understand this business deeply and can answer questions about it, or should I research and teach you?" User's answer determines the flow:
- **Deep understanding:** skill asks the 6 questions; user answers; skill drafts DOMAIN.md.
- **Teach-me mode:** (future enhancement) skill would use WebFetch against a company website and synthesize. For v1, teach-me mode is acknowledged but defers to the "deep understanding" flow with a note that research mode is a future enhancement.

### BR-006: Tiered documentation skeleton

Phase 3 always creates Tier 1 directories unconditionally: `docs/prds/`, `docs/plans/`, `docs/sources/`, `docs/standards/`, `docs/guides/`. Tier 2 is prompted ("Will this project have multiple bounded contexts, ADRs, or cross-cutting invariants?"). Tier 3 is only created when the skill is invoked with `--tier=3`.

### BR-007: Five standard role manifest starters

Phase 4 creates starter role manifests for exactly these 5 roles: `sem`, `architect`, `backend-dev`, `frontend-dev`, `code-reviewer`. Each manifest uses the soft-POLA pattern (`default_consumes` + `discovery.allowed_requests`, no `forbids`). Each manifest contains `# EDIT ME` comments at points requiring project-specific customization.

### BR-008: Per-phase invocation via flag

The skill supports `--phase=<name>` to run individual phases: `--phase=tech`, `--phase=domain`, `--phase=skeleton`, `--phase=roles`. Running a later phase verifies that earlier phases' outputs exist and blocks otherwise with a clear message.

### BR-009: README stubs are self-documenting

Each directory README stub created by Phase 3 is ≤15 lines and contains:
1. One-line purpose statement
2. Naming convention (e.g., "numbered `PRD-NN-{context}.md`")
3. One example filename
4. A pointer line back to `DOMAIN.md` / `PROJECT.md` for orientation

### BR-010: Completion report

Upon successful completion, the skill reports a checklist of what was created and what was skipped (already present). The report must include: which phases ran, which files were created, which files were preserved, and what the user should do next (typically: "run `/build`").

### BR-011: compile-sdlc.py copies full skill directories

`compile-sdlc.py`'s `compile_skills` function is extended to copy the entire contents of each `skills/<skill>/` directory into `dist/skills/<skill>/`, not just `SKILL.md`. This deploys template files alongside the skill definitions they are referenced from.

### BR-012: Preflight integration

The `tier-0-preflight` hook's error message names `/init-project` (and `/init-project --phase=domain`) as the fix when `DOMAIN.md` or `PROJECT.md` is missing. This message is currently in `hooks/check-tier-0.sh` and already names `/init-project`, so no change is needed — but BR-012 asserts this invariant so future hook edits do not drift.

### BR-013: No silent CLAUDE.md overwrite

If `CLAUDE.md` already exists in the target repo when Phase 2 runs, the skill MUST NOT silently overwrite it. The skill either merges (preferred) or asks the user which to keep. `CLAUDE.md` often contains user-specific rules the skill should not discard.

### BR-014: Starter manifests reference correct paths

Every starter role manifest produced by Phase 4 must reference files and glob patterns that will exist after `/init-project` completes: `DOMAIN.md`, `PROJECT.md`, `docs/prds/`, `docs/sources/`, etc. No manifest may reference a file that won't be created.

### BR-015: Brownfield vocabulary surfacing

When Phase 1 runs in brownfield mode and produces a `.meta/` tree, Phase 2 reads the tree to extract observed vocabulary (noun-like strings from Purpose and Key Components sections) and surfaces 5–10 candidates as suggested Product Core entities. User confirms or corrects. This resolves OQ4 from the design sketch.

## Acceptance Criteria

1. **Fresh greenfield run produces full artifact set.** Running `/init-project` on an empty repo initialized with `git init` produces:
   - Everything `project-bootstrapper` normally produces (tooling, `.meta/` tree, language-specific configs)
   - `/DOMAIN.md`, `/PROJECT.md`, `/CLAUDE.md` at repo root, all non-empty and following their respective templates
   - `docs/prds/README.md`, `docs/plans/README.md`, `docs/sources/README.md`, `docs/standards/README.md`, `docs/guides/README.md`, each ≤15 lines
   - `roles/README.md` plus 5 manifest files: `sem.yaml`, `architect.yaml`, `backend-dev.yaml`, `frontend-dev.yaml`, `code-reviewer.yaml`
   - All 5 role manifests parse as valid YAML
2. **Idempotent re-run produces no changes.** Running `/init-project` a second time on the output of AC#1 writes no files, reports "already present" for each phase, and exits 0.
3. **Preflight hook interaction.** After `/init-project` completes on a fresh repo, the `tier-0-preflight` hook no longer blocks Edit|Write operations on `src/` paths. Before `/init-project` runs, the hook blocks them.
4. **Partial Tier 0 recovery.** If only `DOMAIN.md` exists (not `PROJECT.md`), `/init-project --phase=domain` creates `PROJECT.md` without touching `DOMAIN.md`.
5. **Phase flag isolation.** `/init-project --phase=skeleton` creates only the Tier 1 README stubs and directories, does not invoke `project-bootstrapper`, does not touch Tier 0 files.
6. **Phase dependency enforcement.** `/init-project --phase=domain` executed on a repo with no `.meta/` tree (phase 1 has not run) still succeeds but produces a `DOMAIN.md` that notes "brownfield vocabulary unavailable" in place of suggested Product Core entities.
7. **Template deployment.** After `compile-sdlc.py` runs, `dist/skills/init-project/` contains `SKILL.md` AND a `templates/` subdirectory with all template files intact.
8. **CLAUDE.md preservation.** If `CLAUDE.md` already exists before Phase 2 runs, the pre-existing content is preserved. The skill either merges new rules in or asks the user which to keep — it never silently overwrites.
9. **Role manifest soft-POLA.** Every starter role manifest produced by Phase 4 contains a `default_consumes` block and a `discovery.allowed_requests` block, and contains no `forbids` block.
10. **Completion report.** On successful completion, the skill outputs a summary block showing which phases ran, which files were created, and a pointer to `/build` as the next step.
11. **README stubs are discoverable.** Each Tier 1 README stub points back to `DOMAIN.md` and `PROJECT.md` via relative markdown links that resolve correctly from the stub's location.
12. **project-bootstrapper invocation is visible.** Phase 1 invokes `project-bootstrapper` via the Task tool with `subagent_type: "project-bootstrapper"` — not via shell, not via skill-calls-skill, not via reimplementation.

## Edge Cases

1. **Repo is not git-initialized.** `project-bootstrapper` handles this in Phase 1 (initializes git or asks user). `/init-project` does not need to handle it directly.
2. **Empty `DOMAIN.md` already exists.** Phase 2 treats an empty file as "needs writing" and runs the interactive flow, but asks for confirmation before writing, in case the empty file was created intentionally by another tool.
3. **`PROJECT.md` exists and references a different project.** Phase 2 detects the mismatch by comparing the project name in the file to the current directory name, warns the user, and asks whether to keep, update, or replace.
4. **User interrupts Phase 2 mid-flow.** Partial drafts are saved to `spec/.drafts/init-project-domain.md` (matching `/spec`'s convention). Re-running `/init-project --phase=domain` resumes from the draft.
5. **`project-bootstrapper` fails in Phase 1.** `/init-project` stops, reports the error verbatim, and does not proceed to Phase 2. User must resolve the underlying scaffold issue and re-run.
6. **Language stack unclear for `project-bootstrapper`.** The agent asks the user directly (its own behavior). `/init-project` does not intervene.
7. **Tier 2 prompt answered "no", then later answered "yes".** Re-running `/init-project --phase=skeleton` and answering "yes" to the Tier 2 prompt creates the missing Tier 2 directories without affecting Tier 1.
8. **Partial role manifest set.** If `roles/backend-dev.yaml` already exists (e.g., from the VenLink experiment), Phase 4 skips that file and creates only the other 4 manifests.
9. **`compile-sdlc.py` has not been updated with BR-011.** `/init-project`'s templates are present in the source tree but missing from `dist/`. Running the skill from `dist/` (installed version) fails when it tries to read templates. The skill MUST detect this at runtime and error out with a message pointing to BR-011.
10. **Tier 0 partial creation during Phase 2 (e.g., session crashes after `DOMAIN.md` but before `PROJECT.md`).** Re-running `/init-project --phase=domain` detects the partial state and continues from `PROJECT.md` without re-asking Phase 2's initial questions.
11. **User runs `/init-project` in the ETC repo itself (self-hosting).** The skill should work — ETC already has `DOMAIN.md`-equivalent content scattered across `spec/` and `README.md`, but no `DOMAIN.md` at root. Running the skill against the ETC repo is a valid test case and should produce a `DOMAIN.md` that describes "the harness business" (agentic software engineering with discipline).
12. **Interactive prompts in a non-interactive context.** If the skill is invoked in a context without interactive input (e.g., CI), it fails fast with a message explaining Phase 2 requires interactive input or an answers file. A future enhancement can add `--answers-file=<path>` for non-interactive mode.

## Technical Constraints

- **Must use the Task tool** with `subagent_type: "project-bootstrapper"` to invoke Phase 1. No shell-based delegation, no skill-calls-skill, no inline reimplementation.
- **Must follow the `SKILL.md` format** used by other skills in `skills/`: YAML frontmatter with `name` and `description`, followed by markdown body. Reference: `skills/postmortem/SKILL.md`.
- **Must be idempotent.** Re-runs must detect existing files and skip them without error.
- **Must use the 9-section DOMAIN.md format literally** from the blog article — no creative reinterpretation of the sections.
- **Must conform to `compile-sdlc.py`'s skill emission path.** `skills/<name>/SKILL.md` → `dist/skills/<name>/SKILL.md`. Templates co-located under `skills/init-project/templates/` require BR-011 to be implemented.
- **Must reference but not depend on the discovery protocol runtime.** Starter role manifests include `discovery:` blocks in the yaml, but the runtime does not yet enforce them. This is OK — the manifest is declarative.
- **All starter role manifests MUST use the soft-POLA pattern** from `roles/backend-dev.yaml` in the VenLink experiment. No `forbids` keys. `default_consumes` + `discovery.allowed_requests` is the pattern.
- **compile-sdlc.py change (BR-011) MUST be backward-compatible.** Existing skills that have no `templates/` directory must still compile correctly — the change is additive.
- **Must not introduce new runtime dependencies.** The skill is a markdown prompt, not executable code. All dynamic behavior happens in the agent's interpretation of the prompt.
- **Model:** no explicit model pinning in the skill frontmatter. Default to whatever the harness is running. If the interactive phase benefits from a specific model, document it but don't hardcode it.

## Security Considerations

- **Interactive DOMAIN.md creation writes user-provided content directly into a file at repo root.** Content is not executed. Low risk, but the skill must not write content from untrusted sources (e.g., scraped web content) without user confirmation.
- **`CLAUDE.md` must never be silently overwritten.** CLAUDE.md contains agent working rules that users depend on; discarding them silently is an integrity violation. Asserted by BR-013.
- **Templates are static files bundled with the skill.** No template injection risk — templates are copied verbatim, not rendered as executable templates.
- **`project-bootstrapper` spawn is not a privilege escalation.** It is a trusted agent within the harness, invoked via the normal Task tool path.
- **No credentials, tokens, or secrets are written by any phase.** If Phase 1 (`project-bootstrapper`) configures gitleaks, that is part of its own scope and its own security posture.
- **`--tier=3` regulated-domain mode (out of scope for v1)** will require additional security considerations around source corpus handling, compliance evidence, and traceability. Deferred.
- **No filesystem access outside the current working directory.** The skill does not read or write anything above `cwd`.

## Module Structure

### New files (all paths relative to repo root)

```
skills/init-project/
├── SKILL.md                                    # main skill file with interactive prompt
└── templates/
    ├── DOMAIN.md.template                      # 9-section blog format with placeholders
    ├── PROJECT.md.template                     # codebase orientation template
    ├── CLAUDE.md.template                      # agent working rules template
    ├── tier-1/
    │   ├── prds.README.md                      # "PRDs live here. Numbered PRD-NN-{context}.md."
    │   ├── plans.README.md                     # "Dated YYYY-MM-DD-slug.md."
    │   ├── sources.README.md                   # "Ground truth. Cite, never invent."
    │   ├── standards.README.md                 # "Engineering conventions."
    │   └── guides.README.md                    # "Runbooks, deployment guides."
    ├── roles-README.md                         # "Role manifests. Declarative context projections."
    └── roles/
        ├── sem.yaml                            # orchestrator starter manifest
        ├── architect.yaml                      # tier-2 consumer starter
        ├── backend-dev.yaml                    # leaf dev starter (matches VenLink pattern)
        ├── frontend-dev.yaml                   # leaf dev, frontend variant
        └── code-reviewer.yaml                  # read-only role with cross-context visibility
```

**Total new files:** 1 skill + 14 templates = 15 files.

### Modified files

- `compile-sdlc.py` — extend `compile_skills` (currently line 183–203) to copy entire skill directory contents recursively, not just `SKILL.md`. Ensure backward compatibility for skills without `templates/`.
- `spec/init-project.md` — update to reference this PRD as the authoritative spec and to fold in the phase 1 delegation change. This is cleanup, not required for functionality.
- `spec/etc_sdlc.yaml` — optional: register `/init-project` as a declared skill in the DSL `skills:` section, so the spec can reference it from the SDLC flow. Out of scope unless the DSL requires it for compilation.

### Files explicitly not modified

- `agents/project-bootstrapper.md` — delegated to as-is, not modified
- `hooks/check-tier-0.sh` — already integrated, no change needed
- `roles/backend-dev.yaml` in `~/clients/venlink/src/venlink-platform/` — VenLink is a separate repo; not touched by this PRD

## Research Notes

### Canonical references

- **The "domain.md blog article"** (Heavy Chain Engineering, dated 2026-02-17, titled "The Most Important File in Your Repository is domain.md") is the authoritative source for the 9-section DOMAIN.md format and the 6-step creation process. The PortLedger example in the article is the model for what a finished `DOMAIN.md` looks like. Every template and the Phase 2 interactive flow must match it exactly — no creative variations.

- **The existing `project-bootstrapper` agent** (`agents/project-bootstrapper.md`) is battle-tested. Its Phase 4 "Tooling Gap Analysis" and Tooling Setup section cover gitleaks, linting, formatting, pre-commit, security scanning, CI/CD, and language-specific excellence for Python/TS/Rust/Go. `/init-project` delegates to it entirely in Phase 1.

- **The `tier-0-preflight` hook** (`hooks/check-tier-0.sh`, registered as a gate in `spec/etc_sdlc.yaml` commit `451a41c`) blocks Edit|Write when `DOMAIN.md` or `PROJECT.md` is missing. It allows editing the Tier 0 files themselves, so `/init-project` can bootstrap from nothing. The hook's error message already names `/init-project` as the fix — the skill's invocation syntax must stay consistent with that message.

- **The soft-POLA role manifest pattern** is documented in `spec/discovery-protocol.md` and exemplified by `roles/backend-dev.yaml` in the VenLink experiment (`~/clients/venlink/src/venlink-platform/`, commit `e5ffe49`). All starter manifests must follow this pattern: `default_consumes` + `discovery.allowed_requests`, no `forbids`.

- **The tiered domain layout pattern (Tier 0 / 1 / 2 / 3)** was validated on VenLink in session 2026-04-13. Reshape was mechanical (28 moves + 2 new files + 2 edits, no content rewrites). This is the evidence that `/init-project` generalizes beyond a single project.

### Implementation notes

- `compile-sdlc.py` currently only copies `SKILL.md` from each skill directory (line 203: `shutil.copy2(skill_path / "SKILL.md", dst / "SKILL.md")`). BR-011 requires extending this to copy the entire directory tree. The fix is a few lines: replace the single-file copy with `shutil.copytree`. Backward-compatible because existing skills simply have no additional files to copy.

- `.etc_sdlc/features/` and `.etc_sdlc/tasks/` already exist in the ETC repo. `/init-project` does NOT create its own feature directory during execution — that is `/spec` and `/build`'s job. The feature directory for THIS PRD lives at `.etc_sdlc/features/init-project/`.

- No `antipatterns.md` file exists in the ETC repo yet. The `/postmortem` skill would populate it as bugs escape. No antipatterns to incorporate at this time.

- `skills/build/SKILL.md` has its own DoR checklist at step 1 (VALIDATE). This PRD must pass that checklist before `/build` will proceed. Acceptance criteria and file paths above are explicit enough to satisfy it.

### Gray areas — resolved decisions

| ID | Topic | Decision | Rationale |
|---|---|---|---|
| GA-001 | Phase 1 delegation mechanism | Task tool spawn of `project-bootstrapper` agent | `project-bootstrapper` already exists and is battle-tested; reimplementation would duplicate work and risk divergence |
| GA-002 | Research vs teach-me mode detection | User selects upfront via a yes/no question at start of Phase 2 | Mode determination is a one-shot user decision; runtime detection is overcomplication |
| GA-003 | Can Phase 2 be deferred | Yes, via `--phase=<name>` flag | Supports CI scaffolding workflows where domain creation happens later interactively |
| GA-004 | Brownfield research source | Read `.meta/` tree produced by Phase 1 | `project-bootstrapper` already produces this; reusing it avoids redundant work |
| GA-005 | Closed-loop ticket pipeline integration | Out of scope for this PRD | Separate spec (`spec/closed-loop-ticket-pipeline.md`); would expand this PRD's scope beyond initial bootstrap |
