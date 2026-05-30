# PRD: Codex-Native Harness Conversion

**Status:** spec
**Delivery target:** PR into the shared ETC repository
**Release bar:** reusable Codex distribution across repositories

## Problem

ETC is currently a Claude-oriented harness. Its source-of-truth model is
sound: `spec/etc_sdlc.yaml` defines the SDLC gates, agents, skills, phases,
standards, and installer artifacts, and `compile-sdlc.py` turns that source
into deployable output. The problem is that the current deployable target and
runtime assumptions are Claude-specific.

Codex can preserve most of ETC's discipline, but not by copying the Claude
implementation literally. Several Claude-era concepts do not have direct Codex
equivalents:

- prompt hooks
- agent hooks
- `TaskCreated` and `TaskCompleted` lifecycle hooks
- `ConfigChange` lifecycle hooks
- hard pass/fail checks that parse transcript internals
- hook payloads shaped around `.tool_input.file_path`
- install paths hardcoded to `~/.claude`

The goal is result parity, not implementation parity. Every Claude-era
discipline, guardrail, workflow, and safety outcome must either map to a
Codex-native mechanism or have an explicit workaround that delivers the same
end result.

## Solution

Add Codex as a first-class ETC compiler and installer target while preserving
`spec/etc_sdlc.yaml` as the only authoritative SDLC definition.

The Codex target will generate and install:

- Codex project/user instructions from ETC standards and lifecycle guidance.
- Codex-compatible skills under `.agents/skills`.
- Codex custom agents/subagents under `.codex/agents`.
- Codex hook config and hook scripts using supported Codex command-hook
  semantics.
- A small runtime compatibility layer for paths, install roots, normalized hook
  payloads, edited-file extraction, tool names, and task proof validation.
- Task-scoped JSON proof artifacts under `.etc_sdlc/tasks/<task-id>/`.
- `etc-runtime doctor` and `etc-runtime ci-check`.
- Optional CI templates and optional plugin packaging.

The installer is the authoritative complete install path. Plugin packaging is a
convenience distribution path for the Codex surfaces it can reliably carry.

## Codex Behavior Assumptions

The implementation must verify current OpenAI Codex docs before coding against
these assumptions. The planning baseline is:

- `AGENTS.md` is Codex's instruction-file convention and is discovered by
  walking from repository root toward the current working directory, with
  project and global scopes.
- Codex skills can live in repository-local `.agents/skills`, user-level
  `$HOME/.agents/skills`, and plugin-provided skill roots.
- Codex custom agents/subagents are TOML files under `.codex/agents` or
  `$HOME/.codex/agents`.
- Codex hooks support command handlers. Prompt and agent hook declarations may
  be parsed but must not be treated as active enforcement.
- Codex edit activity can arrive through `apply_patch`, so file extraction must
  parse patch payloads and not assume one `.tool_input.file_path`.
- Codex plugin packaging supports plugin manifests, skills, hooks, assets, and
  related plugin files, but this PRD must not assume custom-agent bundling is
  first-class unless the docs confirm it during implementation.

Reference docs to re-check during implementation:

- `https://developers.openai.com/codex/guides/agents-md`
- `https://developers.openai.com/codex/skills`
- `https://developers.openai.com/codex/subagents`
- `https://developers.openai.com/codex/hooks`
- `https://developers.openai.com/codex/plugins/build`

## Scope

### In Scope

- Add a Codex compiler target to `compile-sdlc.py`.
- Add `--client codex` to `install.sh`.
- Keep existing Claude compiler and installer behavior working unless a
  breaking change is explicitly approved in the PR.
- Generate Codex-native hook config from `spec/etc_sdlc.yaml`.
- Generate Codex-friendly skills from existing ETC skills.
- Generate Codex custom-agent TOML files from existing ETC agents.
- Add a runtime compatibility layer for Codex and shared script execution.
- Add task-scoped JSON artifact schemas for readiness, reading ledger, review,
  and completion proof.
- Replace unsupported Claude lifecycle behavior with deterministic artifacts,
  skill workflow requirements, subagent review artifacts, Stop hooks, and
  reusable CI checks.
- Add Codex-specific compiler, installer, hook, runtime, skill, agent, and
  fixture tests.
- Add `etc-runtime doctor`.
- Add `etc-runtime ci-check`.
- Ship first-class reusable CI scripts and optional CI workflow templates.
- Add optional Codex plugin packaging as a convenience path.
- Update operator documentation.
- Dogfood the release in two real repositories plus one synthetic fixture repo.

### Out of Scope

- Literal Claude implementation parity.
- Fake Codex lifecycle events that pretend to be Claude events.
- Running LLM judgment inside Codex command hooks.
- Making human escalation the default substitute for missing Claude behavior.
- Hand-maintaining parallel Codex artifacts outside the compiler.
- Rewriting ETC's SDLC philosophy, standards model, or source-of-truth model.
- Committing generated `dist/` output.
- Making plugin install the authoritative complete install path.
- Treating transcript parsing as a hard gate.

## Release Decisions

### OD1: CI Enforcement

ETC ships first-class reusable CI scripts. Workflow files are optional
templates.

Required behavior:

- `etc-runtime ci-check --client codex` is implemented, tested, and documented.
- GitHub Actions templates may be generated or copied as examples.
- `etc-runtime doctor` reports CI as one of:
  - `enabled`
  - `available-but-not-wired`
  - `unsupported`

### OD2: Artifact Schemas

Use task-scoped JSON artifacts under `.etc_sdlc/tasks/<task-id>/`.

Required artifact files:

- `readiness.json`
- `reading-ledger.json`
- `review.json`
- `completion.json`

Artifacts replace unsupported Claude prompt, agent, and task lifecycle hooks as
the durable machine-checkable proof surface.

### OD3: Packaging

Installer-first. Plugin as convenience.

Required behavior:

- `install.sh --client codex` is the authoritative complete install path.
- Plugin packaging is generated and supported for the Codex surfaces it can
  reliably carry.
- Installer owns project-local agents, runtime scripts, optional CI wiring,
  config placement, path resolution, and health checks.

### OD4: Transcript Usage

Transcript parsing is forbidden for hard pass/fail gates.

Allowed:

- diagnostic output
- debug hints
- optional remediation context

Forbidden:

- passing a hard gate because transcript text says something happened
- failing a hard gate solely because transcript parsing failed
- making transcript shape part of the stable ETC contract

### OD5: Dogfood Release Bar

Release requires:

- two real repository installs
- one synthetic fixture repository

Each dogfood target must record install evidence, doctor result, an edit
workflow, one blocked gate, one successful completion, and issues found/resolved
or explicitly accepted.

## Generated Artifact Policy

Current repo policy is that `dist/` is generated, gitignored, and not committed.
This PRD preserves that policy.

Required behavior:

- The PR commits source inputs, compiler logic, runtime scripts, schemas, tests,
  docs, templates, and fixtures.
- The PR does not commit generated `dist/` artifacts.
- CI compiles fresh from `spec/etc_sdlc.yaml`.
- CI validates generated Claude and Codex outputs from the fresh compile.
- Install/package artifacts may be produced from compiled output, but compiled
  output remains non-authoritative.

## Result-Parity Model

Unsupported Claude behavior must map to one of these Codex mechanisms:

| Claude-era behavior | Codex result-parity mechanism |
|---|---|
| Prompt hook | Required skill step writes machine-checkable artifact |
| Agent hook | Explicit Codex subagent writes reviewer/verifier artifact |
| `TaskCreated` / `TaskCompleted` | Repo-local ETC task state and task-scoped artifacts |
| `ConfigChange` | Edit/Bash guards plus `ci-check` diff validation |
| Transcript-backed hard gate | Deterministic artifact, hook payload, or git state |
| `.tool_input.file_path` | Normalized hook payload with `edited_files[]` |
| Pre-edit check that needs final tree | Split PreToolUse cheap guard from Post/Stop/CI validation |
| Hardcoded `~/.claude` path | Runtime path resolver |

## Hook Adaptation Matrix

Every gate in `spec/etc_sdlc.yaml` must be classified. No uncategorized gate may
remain.

| Gate | Current event | Current type | Script/prompt/agent | Codex bucket | Intended result parity |
|---|---|---|---|---|---|
| `safety-guardrails` | `PreToolUse` `Bash` | command | `block-dangerous-commands.sh` | Direct Codex command hook | Block destructive shell commands before execution. Normalize command extraction, but keep this as a hard local hook. |
| `tier-0-preflight` | `PreToolUse` `Edit|Write` | command | `check-tier-0.sh` | Command hook with payload adapter | Block code edits when required Tier 0 project context is missing. Adapter must extract edited files from `apply_patch`. |
| `tdd-gate` | `PreToolUse` `Edit|Write` | command | `check-test-exists.sh` | Command hook with payload adapter plus Stop/CI backstop | Enforce write-test-first for production code. Pre hook may allow a patch that creates test and implementation together; Post/Stop/CI validates final tree. |
| `invariant-check` | `PreToolUse` `Edit|Write` | command | `check-invariants.sh` | Command hook with payload adapter | Validate project invariants for every changed file, including multi-file patches. |
| `code-quality-check` | `PreToolUse` `Edit|Write` | command | `check-code-quality.sh` | Command hook with payload adapter plus Stop/CI backstop | Preserve AST quality enforcement. If final-tree judgment is required, run against patched files after edit and in `ci-check`. |
| `enough-context` | `PreToolUse` `Edit|Write` | command | `check-required-reading.sh` | Skill workflow gate plus command validation | Replace transcript inference with `reading-ledger.json`. Edits are blocked when required reading for the active task is missing or stale. |
| `phase-gate` | `PreToolUse` `Edit|Write` | command | `check-phase-gate.sh` | Command hook with payload adapter | Block edits inappropriate for the current SDLC phase. Runtime resolves active phase from task/project state, not transcript. |
| `seam-evidence-check` | `Stop` | command | `check-seam-evidence.sh` | Stop/final verification gate | Validate integration seam evidence at completion time. Also runnable from `ci-check`. |
| `concept-check` | `PostToolUse` `Task` | command | `check-concepts.sh` | Stop/CI verification gate | No Codex `Task` lifecycle dependency. Run concept validation during completion/CI for the active task or changed bounded contexts. |
| `dirty-marker` | `PostToolUse` `Edit|Write` | command | `mark-dirty.sh` | Command hook with payload adapter | Mark production-source edits for later completion/CI discipline. Must support `apply_patch`, multi-file edits, creation, deletion, and rename-like patches. |
| `task-readiness` | `TaskCreated` | prompt | YAML prompt in `spec/etc_sdlc.yaml` | Skill workflow gate | Skill validates formal ETC tasks and writes `readiness.json`. Hook/CI validates presence, schema, freshness, and pass status. |
| `task-completion` | `TaskCompleted` | agent | YAML agent prompt in `spec/etc_sdlc.yaml` | Subagent workflow gate plus Stop verification | Codex verifier subagent writes `completion.json`. Stop/CI blocks incomplete, stale, or failing completion proof. |
| `standards-injection` | `SubagentStart` | command | `inject-standards.sh` | Direct Codex command hook if supported; otherwise skill/subagent prompt prelude | Preserve onboarding packet for subagents. Rewrite Claude-specific references and keep output concise enough for Codex context. |
| `adversarial-review` | `SubagentStop` | agent | YAML agent prompt in `spec/etc_sdlc.yaml` | Subagent workflow gate | Explicit reviewer subagent writes `review.json`. Completion cannot pass without a current passing review artifact. |
| `completion-discipline` | `Stop` | command | `check-completion-discipline.sh` | Stop/final verification gate | Block final completion when dirty marker, in-progress tasks, missing proofs, failed checks, or incomplete artifacts remain. Remove hardcoded Claude paths. |
| `change-control` | `ConfigChange` | command | `block-config-changes.sh` | Edit/Bash guard plus CI diff validation | Block unauthorized harness/config changes through `apply_patch`/Bash detection and CI changed-file policy. Do not rely on `ConfigChange`. |
| `compaction-recovery` | `SessionStart` `compact` | command | `reinject-context.sh` | Direct command hook if supported; otherwise AGENTS/skill recovery workflow | Restore active phase, task, constraints, and recent decisions from deterministic checkpoints. Rewrite Claude-specific wording. |

## Runtime Compatibility Layer

Add an ETC runtime entry point, installed with Codex artifacts and callable from
hooks, skills, and CI.

Candidate command shape:

```bash
etc-runtime hook-normalize --client codex
etc-runtime path hooks --client codex
etc-runtime path skills --client codex
etc-runtime path agents --client codex
etc-runtime task validate --task-id <id>
etc-runtime doctor --client codex
etc-runtime ci-check --client codex
```

Required capabilities:

- Detect install root without hardcoded `~/.claude`.
- Resolve project-local, user/global, and plugin install paths.
- Normalize hook stdin into a stable internal JSON shape.
- Extract `edited_files[]` from Codex `apply_patch` payloads.
- Extract shell commands from Bash hook payloads.
- Preserve `cwd`.
- Normalize tool names into stable categories:
  - `edit`
  - `shell`
  - `subagent`
  - `stop`
  - `session`
  - `unknown`
- Handle multi-file patch edits.
- Handle file create, delete, and modification patches.
- Produce clear failure messages for malformed payloads.
- Validate task artifacts by schema version and freshness.

Normalized hook payload minimum shape:

```json
{
  "schema_version": 1,
  "client": "codex",
  "event": "PreToolUse",
  "tool_name": "apply_patch",
  "tool_kind": "edit",
  "cwd": "/absolute/repo/path",
  "edited_files": ["src/example.ts", "src/example.test.ts"],
  "commands": [],
  "raw_payload_available": true
}
```

## Task Artifact Schemas

All artifacts live under:

```text
.etc_sdlc/tasks/<task-id>/
```

Shared required fields:

- `schema_version`
- `task_id`
- `client`
- `created_at`
- `updated_at`
- `source_commit`
- `changed_files`
- `status`
- `checks`
- `notes`

### `readiness.json`

Purpose: replaces the `TaskCreated` prompt hook.

Required concern-specific fields:

- `phase`
- `risk_tier`
- `files_in_scope`
- `acceptance_criteria`
- `required_reading`
- `test_strategy`
- `dependencies`
- `ready`

### `reading-ledger.json`

Purpose: replaces transcript-backed required-reading inference.

Required concern-specific fields:

- `required_reading`
- `read_entries`
- `coverage`
- `missing`
- `fresh`

Each read entry must include:

- `path`
- `reason`
- `recorded_at`
- one of `digest`, `mtime`, or another deterministic freshness marker

### `review.json`

Purpose: replaces the `SubagentStop` adversarial agent hook.

Required concern-specific fields:

- `reviewer`
- `review_type`
- `findings`
- `required_fixes`
- `verdict`
- `fresh_for_changed_files`

### `completion.json`

Purpose: replaces the `TaskCompleted` agent hook and supports Stop-time
completion discipline.

Required concern-specific fields:

- `test_evidence`
- `review_evidence`
- `acceptance_criteria_results`
- `unresolved_risks`
- `final_status`

## Compiler Requirements

### BR-001: Preserve YAML Source of Truth

`spec/etc_sdlc.yaml` remains the only authoritative source for gates, agents,
skills, phases, and standards.

### BR-002: Add Client-Aware Compilation

`compile-sdlc.py` must support Codex output without removing existing Claude
output.

Acceptable command shapes include:

```bash
python3 compile-sdlc.py spec/etc_sdlc.yaml
python3 compile-sdlc.py spec/etc_sdlc.yaml --client claude
python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex
python3 compile-sdlc.py spec/etc_sdlc.yaml --client all
```

The default must preserve current behavior unless intentionally changed and
documented.

### BR-003: Generate Codex Artifacts

The Codex target must generate artifacts needed by the installer, including:

- Codex hooks config.
- Codex hook scripts.
- Codex skills.
- Codex agents.
- Runtime scripts.
- Artifact schemas.
- Optional plugin bundle.
- Optional CI templates.

### BR-004: Classify Unsupported Gates

The compiler must either generate a Codex enforcement artifact or emit a
machine-readable unsupported-gate classification for every YAML gate. No gate
may silently disappear.

### BR-005: Copy Hook Helpers

Any helper scripts required by generated hooks must be present in the compiled
Codex output. Existing helper omissions must be fixed as part of this work.

### BR-006: Avoid Committed `dist/`

Generated output remains ignored. Tests compile fresh and validate generated
content from source.

## Installer Requirements

### BR-007: Add Codex Client Selection

`install.sh` must accept:

```bash
./install.sh --client codex
```

Interactive selection may remain, but non-interactive client selection is
required for CI, dogfood, and repeatable installs.

### BR-008: Support Idempotent Installs

Running the Codex install repeatedly must not duplicate hook entries, corrupt
existing config, or hand-edit generated artifacts.

### BR-009: Support Explicit Targeting

The installer must support explicit install targets or equivalent options for
the selected scope. Required scopes:

- project-local Codex install
- user/global Codex install, if supported by Codex docs

If a scope cannot be supported safely, the installer must fail clearly and docs
must explain why.

### BR-010: Installer Owns Complete Setup

The installer must install or wire:

- Codex instructions
- Codex skills
- Codex agents
- Codex hooks
- runtime scripts
- schemas
- optional CI templates
- optional plugin package
- doctor command

### BR-011: No Hardcoded Claude Install Root

No Codex-installed script may require `~/.claude`.

## Skills Conversion Requirements

### BR-012: Codex-Friendly Skill Output

Converted skills must be usable from Codex skill discovery and must avoid
Claude-only tool names or instructions unless abstracted through ETC runtime
or clearly marked as client-specific.

### BR-013: Preserve Workflow Intent

Skill conversion must preserve ETC workflow discipline:

- Socratic specification
- phase control
- task readiness
- required reading
- TDD
- verifier/reviewer handoff
- completion proof

### BR-014: Required Proof Writes

Codex skills that replace prompt hooks must write or update task-scoped proof
artifacts rather than relying on chat memory.

## Agent Conversion Requirements

### BR-015: Generate Codex Agent TOML

Claude-style agent markdown files must compile into Codex custom-agent TOML
where possible.

Required minimum fields:

- `name`
- `description`
- `developer_instructions`

### BR-016: Preserve Agent Intent

The generated Codex agents must preserve the role intent of the source agents,
especially verifier/reviewer agents used for result parity.

### BR-017: Explicit Unsupported Agent Features

Any Claude-only agent feature without Codex support must be documented in the
generated classification and operator docs.

## Hook Requirements

### BR-018: Command Hooks Only For Deterministic Logic

Codex command hooks may run deterministic checks only. They must not pretend to
run LLM prompt or agent judgment.

### BR-019: Payload Adapter Required

Every Codex hook script that inspects files, commands, cwd, or tool names must
consume the normalized runtime payload, not raw Claude-shaped JSON.

### BR-020: `apply_patch` Coverage

Codex edit-time gates must handle edits through `apply_patch`, including:

- one-file edits
- multi-file edits
- file creation
- file deletion
- patch payloads that include both tests and implementation

### BR-021: Final-State Backstops

Checks that cannot be safely judged before the patch lands must have Post/Stop
or CI validation.

### BR-022: Transcript Ban For Hard Gates

Hard gate scripts must not require transcript parsing to pass.

## CI Requirements

### BR-023: First-Class `ci-check`

`etc-runtime ci-check --client codex` must validate at minimum:

- generated artifact drift by compiling from source
- hook classification completeness
- task artifact schema validity
- stale proof artifacts
- unauthorized harness/config changes
- completion proof state
- no hardcoded `~/.claude` in Codex outputs

### BR-024: Optional CI Templates

ETC may ship GitHub Actions templates or other CI examples, but the reusable
enforcement logic must live in ETC-owned scripts.

## Doctor Requirements

### BR-025: Install Health Check

`etc-runtime doctor --client codex` must report:

- detected install root
- project/user/plugin mode
- Codex instruction files present
- skills present
- agents present
- hooks present
- runtime executable present
- schemas present
- CI state
- known unsupported gaps
- stale or missing generated output

Doctor failures must be specific enough for an operator to fix without reading
the compiler source.

## Documentation Requirements

### BR-026: Operator Docs

Docs must cover:

- Codex install
- upgrade
- uninstall
- project-local versus user/global install
- plugin convenience path
- hook adaptation model
- unsupported Claude lifecycle behaviors and result-parity replacements
- task artifact schemas
- `doctor`
- `ci-check`
- troubleshooting
- dogfood/release checklist

### BR-027: Migration Docs

Docs must explain how existing Claude assumptions map to Codex mechanisms:

- Claude hooks to Codex hooks/skills/subagents/CI
- Claude agents to Codex agents
- Claude skills to Codex skills
- `~/.claude` paths to runtime path resolution
- transcript assumptions to task artifacts

## PR Definition of Done

The PR is done when all of the following are true:

1. The implementation lands as a PR in the shared ETC repository.
2. Local `~/.codex` changes are not the deliverable.
3. `spec/etc_sdlc.yaml` remains the source of truth.
4. Existing Claude compiler/install behavior still works unless a breaking
   change is explicitly approved.
5. Existing Claude tests still pass.
6. Codex compiler output is generated from source, not hand-maintained.
7. `install.sh --client codex` exists and is idempotent.
8. Codex hook generation covers every YAML gate with an explicit classification.
9. No gate in `spec/etc_sdlc.yaml` is uncategorized.
10. Hard versus advisory behavior is declared for every Codex gate.
11. Codex hooks consume normalized payloads.
12. `apply_patch` edited-file extraction is tested.
13. No generated Codex script depends on hardcoded `~/.claude`.
14. Task-scoped JSON artifact schemas exist and are versioned.
15. Stale task artifacts fail validation.
16. Prompt hook intent is preserved through skills and proof artifacts.
17. Agent hook intent is preserved through Codex subagents and proof artifacts.
18. Stop-time completion discipline works in Codex.
19. `etc-runtime doctor --client codex` exists and is tested.
20. `etc-runtime ci-check --client codex` exists and is tested.
21. First-class reusable CI scripts ship; workflow files are optional templates.
22. Installer-first packaging works.
23. Plugin convenience packaging exists or is explicitly deferred with an
    accepted reason.
24. Operator docs are updated.
25. Generated `dist/` output is not committed.
26. CI/test workflow compiles fresh from `spec/etc_sdlc.yaml`.
27. Security/privacy review confirms no committed dogfood artifact includes
    transcripts, secrets, local-only absolute paths, or private repo content
    beyond approved evidence.

## Release Definition of Done

The release is done when all PR DoD items are true and:

1. The PR is merged or merge-ready.
2. Two real repositories have successful Codex installs.
3. One synthetic fixture repository covers regression cases.
4. Dogfood evidence includes install command, doctor result, edit workflow,
   blocked gate, successful completion, and resolved findings.
5. No hard gate depends on transcript parsing.
6. Every unsupported Claude lifecycle behavior has a result-parity replacement
   or an explicit accepted known gap.
7. A non-implementer can run the documented release checklist.

## Acceptance Criteria

1. `python3 compile-sdlc.py spec/etc_sdlc.yaml` preserves current Claude output
   behavior.
2. `python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex` emits the Codex
   artifact set.
3. `python3 compile-sdlc.py spec/etc_sdlc.yaml --client all` emits both Claude
   and Codex artifacts, if implemented as the chosen multi-target command.
4. `./install.sh --client codex --dry-run` reports the intended install plan
   without writing outside the selected target.
5. `./install.sh --client codex` installs Codex artifacts into a clean target.
6. Re-running `./install.sh --client codex` is idempotent.
7. `etc-runtime doctor --client codex` passes in a freshly installed fixture
   repo.
8. `etc-runtime ci-check --client codex` passes in a valid fixture repo.
9. `etc-runtime ci-check --client codex` fails when generated Codex output
   drifts from `spec/etc_sdlc.yaml`.
10. `etc-runtime ci-check --client codex` fails when required proof artifacts
    are missing.
11. `etc-runtime ci-check --client codex` fails when proof artifacts are stale
    for the current changed files.
12. Hook payload normalization extracts edited files from a single-file
    `apply_patch`.
13. Hook payload normalization extracts edited files from a multi-file
    `apply_patch`.
14. Hook payload normalization detects file creation and deletion.
15. `safety-guardrails` blocks dangerous Bash commands in Codex.
16. `tdd-gate` blocks production-code completion without test proof.
17. `enough-context` blocks edits when `reading-ledger.json` is missing or
    stale.
18. `task-readiness` result parity writes and validates `readiness.json`.
19. `task-completion` result parity writes and validates `completion.json`.
20. `adversarial-review` result parity writes and validates `review.json`.
21. `completion-discipline` blocks final completion when required proof is
    missing, failing, or stale.
22. `change-control` result parity blocks unauthorized harness/config edits
    through edit/Bash guards or `ci-check`.
23. Codex skills are discoverable in the selected install mode.
24. Codex custom agents are discoverable in the selected install mode.
25. Generated Codex files contain no hardcoded `~/.claude`.
26. Generated Codex hard gates do not parse transcript content to decide pass or
    fail.
27. Existing Claude tests continue to pass.
28. New Codex tests pass.
29. `dist/` remains ignored and untracked.

## Test Plan

Add or update tests in these areas:

- `tests/test_codex_compiler.py`
  - Codex artifact tree exists after compile.
  - Every YAML gate has a Codex classification.
  - Prompt/agent hooks are not emitted as active Codex command hooks.
  - Direct and adapter hooks are emitted correctly.

- `tests/test_codex_hook_payloads.py`
  - Normalizes Bash payloads.
  - Normalizes `apply_patch` payloads.
  - Extracts multi-file edits.
  - Handles create/delete patches.
  - Handles malformed payloads with clear errors.

- `tests/test_runtime_compat.py`
  - Resolves install roots.
  - Resolves project/user/plugin paths.
  - Rejects hardcoded Claude paths in Codex mode.
  - Validates task artifacts.
  - Detects stale artifacts.

- `tests/test_codex_installer.py`
  - Non-interactive `--client codex`.
  - Dry-run mode.
  - Idempotent install.
  - Existing config preservation.
  - Clear failure for unsupported install scopes.

- `tests/test_codex_agents.py`
  - Generated TOML is parseable.
  - Required fields exist.
  - Verifier/reviewer agents preserve source intent.

- `tests/test_codex_skills.py`
  - Skills are copied/generated into Codex-compatible layout.
  - Claude-only tool references are removed, abstracted, or marked
    client-specific.
  - Required proof-writing steps are documented.

- `tests/test_codex_ci_check.py`
  - Valid repo passes.
  - Missing proof artifact fails.
  - Stale proof artifact fails.
  - Unauthorized config change fails.
  - Generated-output drift fails.

- Existing tests
  - Existing compiler and installer tests remain green.
  - Tests that currently depend on `dist/` either compile fresh or use temp
    output consistently.

## Implementation Sequence

### Phase 1: Runtime and Schemas

- Add runtime entry point.
- Add payload normalizer.
- Add path resolver.
- Add task artifact schemas and validators.
- Add tests for runtime and schemas.

### Phase 2: Compiler Target

- Add client-aware compilation.
- Generate Codex hook classification.
- Generate Codex hook config and scripts.
- Generate Codex skills layout.
- Generate Codex agent TOML.
- Copy hook helpers.
- Add compiler tests.

### Phase 3: Hook Adaptation

- Port direct command hooks.
- Adapt file-based hooks through normalized payloads.
- Split pre-edit versus final-tree checks where needed.
- Add Stop/CI backstops.
- Remove transcript dependence from hard gates.

### Phase 4: Installer and Packaging

- Add `install.sh --client codex`.
- Add dry-run.
- Add idempotent config handling.
- Add doctor.
- Add ci-check.
- Add optional CI templates.
- Add plugin convenience package if supported by current Codex docs.

### Phase 5: Skills, Agents, Docs, Dogfood

- Convert skills for Codex.
- Convert agents for Codex.
- Update operator docs.
- Build synthetic fixture repo.
- Dogfood in two real repos.
- Resolve or explicitly accept dogfood findings.

## Dogfood Evidence Format

Each dogfood run must record:

- repository name or approved anonymized identifier
- install command
- install mode
- compile command
- `doctor` result
- `ci-check` result
- one successful Codex skill workflow
- one edit workflow using `apply_patch`
- one blocked gate
- one successful completion
- issues found
- issues resolved
- accepted known gaps, if any

Evidence must not include:

- transcripts
- secrets
- private absolute paths unless approved
- private repo content beyond approved summary/evidence

## Security and Privacy

- Hard gates must not depend on transcript parsing.
- Dogfood artifacts must not commit transcripts or secrets.
- Runtime must not echo secrets from hook payloads.
- Installer must preserve existing user config outside the owned ETC section.
- Config-change guard must prevent agents from weakening their own governance.
- Plugin packaging must not hide additional write targets.
- Doctor output must avoid leaking sensitive local paths unless explicitly run in
  verbose mode.

## Risks

1. **Codex hook semantics may change.** Mitigation: re-check official docs at
   implementation start and pin behavior in tests.
2. **Plugin packaging may not support every required artifact.** Mitigation:
   installer remains authoritative; plugin is convenience.
3. **Artifact workflow may feel heavy.** Mitigation: skills write artifacts as
   part of normal workflow, and hooks validate rather than asking users to fill
   files manually.
4. **`apply_patch` parsing may miss edge cases.** Mitigation: fixture tests for
   create, delete, rename-like changes, and multi-file patches.
5. **CI integration may vary by repo.** Mitigation: ship reusable `ci-check`
   logic and optional templates, not provider-only enforcement.
6. **Claude behavior may regress.** Mitigation: keep Claude tests and default
   compile/install behavior green.
7. **Generated-output tests may be brittle.** Mitigation: validate semantic
   structure and selected exact contracts, not every byte of generated output.

## Non-Blocking Implementation Questions

These questions should not reopen the release bar, but implementation must
answer them explicitly in the PR:

1. What exact output tree should Codex compilation use under generated `dist/`?
2. Should runtime be implemented as Python, shell plus Python helpers, or a
   small package-style module?
3. Which project-local Codex config files should installer modify versus
   generate for operator review?
4. Which CI provider template ships first?
5. Whether current Codex plugin docs support bundling custom agents; if not,
   installer handles agents and docs call out the plugin limitation.
