# Codex Harness Operator Guide

How to compile, install, verify, upgrade, and remove the Codex-native ETC harness. This guide documents the current implementation state, not the full target PRD.

## Current Status

Codex support is project-local today. The installer writes generated Codex artifacts into the selected repository and does not modify user-global Codex or Claude configuration.

Implemented operator surfaces:

- `python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex`
- `./install.sh --client codex`
- `./install.sh --client codex --dry-run`
- `.codex/scripts/etc-runtime doctor --client codex`
- `.codex/scripts/etc-runtime ci-check --client codex`

Known gaps:

- User/global Codex install is not enabled by `install.sh`.
- `doctor --client codex` currently supports project scope only.
- Plugin packaging is not authoritative and is not part of the current install flow.

## Compile

From the ETC harness repository:

```bash
python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex
```

The Codex target writes generated output to `dist/codex/` by default:

- `AGENTS.md`
- `.codex/hooks.json`
- `.codex/hooks/`
- `.codex/agents/`
- `.codex/scripts/`
- `.codex/schemas/`
- `.codex/expected/`
- `.codex/standards/`
- `.agents/skills/`
- `gate-classification.json`

Use `--client all` when you need fresh Claude and Codex outputs in one compile:

```bash
python3 compile-sdlc.py spec/etc_sdlc.yaml --client all
```

## Install

Preview the project-local install plan:

```bash
./install.sh --client codex --dry-run
```

Install into the current project directory:

```bash
./install.sh --client codex
```

The explicit project-scope form is equivalent:

```bash
./install.sh --client codex --scope project
```

Install into a specific project directory:

```bash
ETC_PROJECT_DIR=/path/to/project ./install.sh --client codex
```

The installer copies the generated Codex artifacts into that project:

- `AGENTS.md`
- `.codex/hooks.json`
- `.codex/hooks/`
- `.codex/agents/`
- `.codex/scripts/`
- `.codex/schemas/`
- `.codex/expected/`
- `.codex/source/`
- `.codex/standards/`
- `.agents/skills/`
- `gate-classification.json`

If the project already has `AGENTS.md`, the installer preserves the existing
file and appends or refreshes an `ETC_CODEX` managed block. If the project
already has repo-local skills under `.agents/skills`, the installer adds or
updates ETC skills without deleting project-owned skills.

It also marks installed hook and runtime scripts executable. Re-running the install is the upgrade path for project-local artifacts.

## Install Modes

Project-local is the supported mode:

- Instructions: `<project>/AGENTS.md`
- Hooks, agents, runtime, schemas, and standards: `<project>/.codex/`
- Skills: `<project>/.agents/skills/`
- Gate classification: `<project>/gate-classification.json`

User/global is not enabled in the installer. The runtime has path-resolution support for user scope, but operators should not treat that as a supported install mode until `install.sh` and `doctor` expose it.

The safety reason is scope: a user/global Codex install can affect every repository the operator opens. ETC does not write that scope until config merge, trust review, and uninstall semantics are explicit and tested.

If you request user scope, the installer fails before writing:

```bash
./install.sh --client codex --scope user
```

Plugin packaging is a convenience path only. Do not use a plugin package as the authoritative complete install unless a future implementation explicitly documents full coverage for instructions, hooks, agents, skills, runtime scripts, schemas, and proof artifacts.

## Codex Docs Baseline

This implementation baseline was checked against the current OpenAI Codex docs on May 23, 2026:

- `https://developers.openai.com/codex/guides/agents-md`
- `https://developers.openai.com/codex/skills`
- `https://developers.openai.com/codex/subagents`
- `https://developers.openai.com/codex/hooks`
- `https://developers.openai.com/codex/plugins/build`

## Upgrade

Upgrade a project-local install by recompiling and reinstalling:

```bash
python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex
./install.sh --client codex
```

For a non-current project:

```bash
python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex
ETC_PROJECT_DIR=/path/to/project ./install.sh --client codex
```

Run `doctor` after every upgrade.

## Parent Sync

This fork should keep Codex support rebased onto the current parent baseline
when parent updates are synced. Keep `install.sh` as the thin bootstrap and
place Codex install behavior in `etc_installer`; do not reintroduce a large
Codex-specific Bash installer branch.

Before opening or updating a Codex-support PR after a parent sync, run:

```bash
git fetch origin
git merge-base HEAD origin/main
git merge-tree "$(git merge-base HEAD origin/main)" origin/main HEAD
python3 compile-sdlc.py spec/etc_sdlc.yaml --client all
python3 -m pytest -q
git diff --check
```

The merge-base should match the current `origin/main` unless the PR description
explicitly names an accepted lag. The merge-tree output must not contain
unresolved conflict markers. Do not commit generated `dist/` output from the
compile step.

## Uninstall

There is no dedicated uninstall command yet. For a project-local install, remove only the generated ETC-owned surfaces after confirming the project does not maintain its own content at those paths:

```bash
rm -rf .codex .agents/skills gate-classification.json
```

Review `AGENTS.md` before deleting it. If the file contains an `ETC_CODEX`
managed block, remove only that block and keep the project-owned instructions.
If the project had no pre-existing Codex instructions, deleting the generated
file is safe after confirming it was installed by ETC.

## Hook Adaptation Model

The Codex target preserves result parity, not Claude implementation parity.

| Claude-era assumption | Codex replacement |
|---|---|
| Prompt hook | Skill workflow writes a task proof artifact. |
| Agent hook | Explicit Codex subagent writes a reviewer or verifier artifact. |
| `TaskCreated` / `TaskCompleted` | Repo-local task state and `.etc_sdlc/tasks/<task-id>/` artifacts. |
| `ConfigChange` | Edit/Bash guards plus `ci-check` changed-file validation. |
| Transcript-backed hard gate | Deterministic artifact, hook payload, git state, or CI validation. |
| `.tool_input.file_path` | Normalized payload with `edited_files[]`, including `apply_patch` parsing. |
| Pre-edit check needing final tree | Cheap command hook plus Stop/CI validation of the final tree. |
| Hardcoded `~/.claude` path | Runtime path resolver for Codex install roots. |

Active Codex command hooks are generated into `.codex/hooks.json`. Gates that cannot run as deterministic command hooks are classified in `gate-classification.json` and replaced by artifact, subagent, Stop, or CI validation.

Unsupported Claude lifecycle parity currently called out by `doctor`:

- Prompt hook lifecycle is represented by task proof artifacts.
- Agent hook lifecycle is represented by explicit subagent proof artifacts.
- `ConfigChange` lifecycle is represented by edit/Bash guards plus `ci-check`.

## Task Artifacts

Codex task proof lives under:

```text
.etc_sdlc/tasks/<task-id>/
```

Required files:

- `readiness.json`
- `reading-ledger.json`
- `review.json`
- `completion.json`

Generated schemas live under:

```text
.codex/schemas/
```

Each artifact must include shared fields:

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

Artifact-specific proof:

- `readiness.json`: phase, risk tier, files in scope, acceptance criteria, required reading, test strategy, dependencies, ready flag.
- `reading-ledger.json`: required reading, read entries, coverage, missing items, freshness.
- `review.json`: reviewer, review type, findings, required fixes, verdict, freshness for changed files.
- `completion.json`: test evidence, review evidence, acceptance-criteria results, unresolved risks, final status.

Validate one artifact:

```bash
.codex/scripts/etc-runtime task validate --task-id T-001 --artifact completion.json --changed-file src/example.py
```

## Doctor

Run from the installed project root:

```bash
.codex/scripts/etc-runtime doctor --client codex
```

`doctor` checks:

- instructions
- skills
- agents
- hooks
- runtime
- schemas
- expected output snapshot
- generated output drift
- gate classification
- task artifacts
- protected harness/config changes
- hardcoded `~/.claude` references in Codex outputs

`ci_state` reports one of:

- `enabled`: a `.github/workflows/*.yml` or `.yaml` workflow wires `etc-runtime ci-check --client codex`.
- `available-but-not-wired`: local `ci-check` is installed and runnable, but no known CI workflow calls it.
- `unsupported`: required runtime surfaces are missing.

Failures include specific missing or drifted surfaces.

## CI Check

Run from the installed project root:

```bash
.codex/scripts/etc-runtime ci-check --client codex
```

`ci-check` returns success with:

```text
OK: codex ci-check passed
```

It fails when required surfaces are missing, generated Codex output has drifted, gate classification is invalid, proof artifacts are missing or stale, protected harness/config files changed without completion proof, or generated Codex output still references `~/.claude`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `dist/codex/... not found` during install | Codex artifacts were not compiled. | Run `python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex`. |
| `doctor` says project scope only | User/global doctor mode is not enabled. | Run from the installed project root without changing `--scope`. |
| `Codex user/global install is not enabled` | `install.sh --client codex --scope user` was requested. | Use `--scope project` or omit `--scope`. |
| `generated output drift` | Installed artifacts differ from a fresh compile. | Recompile and rerun `./install.sh --client codex`. |
| Missing task artifacts | `.etc_sdlc/tasks/<task-id>/` does not contain all required JSON proof files. | Complete the relevant skill/subagent workflow or write the missing proof artifact. |
| Stale artifact for changed file | A changed file is newer than the artifact `updated_at`. | Refresh the artifact after completing review or verification. |
| Unauthorized harness/config change | Protected files changed without passing completion proof. | Add valid completion proof or revert the unauthorized harness/config edit. |
| Hardcoded `~/.claude` in Codex output | A copied script or instruction still contains Claude-only paths. | Update the source artifact and recompile Codex output. |

## Dogfood Release Checklist

Record one entry for each dogfood target:

- Repository name or approved anonymized identifier.
- Install mode.
- Compile command.
- Install command.
- `doctor` result.
- `ci-check` result.
- One successful Codex skill workflow.
- One edit workflow using `apply_patch`.
- One blocked gate.
- One successful completion.
- Issues found.
- Issues resolved.
- Accepted known gaps, if any.

Release evidence must cover two real repositories and one synthetic fixture repository before the Codex conversion is treated as reusable.

## Dogfood Evidence

Release dogfood was run on May 23, 2026. The live repositories were not
modified; both real-repo checks used temporary local clones under
`/private/tmp`.

| Target | Source commit | Install | Blocked gate | Successful edit gate | Doctor | CI check |
|---|---:|---:|---:|---:|---:|---:|
| Synthetic fixture repo in `tests/test_codex_dogfood.py` | synthetic | pass | blocked missing `tests/**/test_no_test.py` | source+test patch passed | `ci_state: available-but-not-wired` | `OK: codex ci-check passed` |
| Private application repo temp clone under `/private/tmp` | `dd4df34` | pass | return code `2` | return code `0` | return code `0`, `ci_state: available-but-not-wired` | return code `0`, `OK: codex ci-check passed` |
| Private platform repo temp clone under `/private/tmp` | `80c9fed3e` | pass | return code `2` | return code `0` | return code `0`, `ci_state: available-but-not-wired` | return code `0`, `OK: codex ci-check passed` |

Issues found and resolved during dogfood:

- Existing project instructions and skills must be preserved. The first
  private platform temp install showed that replacing `AGENTS.md` and syncing
  `.agents/skills` with deletion would remove project-owned harness context.
  The installer now maintains an `ETC_CODEX` managed block in existing
  `AGENTS.md` files and merges ETC skills without deleting project-owned
  skills.
- Installed `doctor` must not require target-repo Python dependencies. The
  first real-repo pass failed when the target `python3` lacked PyYAML. Codex
  compile now emits `.codex/expected/`, and installed drift checks compare
  against that expected-output snapshot without recompiling source.

## Security and Privacy

Do not include transcripts, secrets, private absolute paths, or private repo content in dogfood evidence unless explicitly approved.

Hard gates must not pass or fail based on transcript parsing. Use deterministic proof instead: hook payloads, task artifacts, generated output, git state, or CI results.

Runtime and doctor output should avoid leaking sensitive local paths. Plugin convenience packages must not hide extra write targets or imply broader install coverage than the project-local installer provides.
