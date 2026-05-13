# F013 — install.sh CLI UX + --scope flag

**Status:** spec
**Author role:** Engineer (Jason / HCE)
**Date:** 2026-05-13

## Problem

`install.sh` today is interactive-only — it prompts for client choice and installs into `~/.claude/` or `~/.gemini/antigravity/`. Two issues:

1. **No per-project scope.** The single global install means etc's Stop hooks, agents, skills fire in EVERY Claude Code session on the operator's machine, including projects where etc is not wanted. Operators have reported this bleeding into unrelated work.
2. **Interactive-only.** Cannot be scripted, automated, or driven from CI. A customer reinstalling on every harness update has to sit at the prompt.

## Solution

Add CLI argument parsing to install.sh:

```
./install.sh                                  # interactive (current behavior preserved)
./install.sh --client claude                  # non-interactive client choice
./install.sh --scope global                   # install to ~/.claude/ (default)
./install.sh --scope project                  # install to ./.claude/ in CWD
./install.sh --client claude --scope project  # fully non-interactive
./install.sh --help                           # usage output
```

- `--client {claude,antigravity}` — skip the interactive client prompt
- `--scope {global,project}` — global = current behavior; project = ./.claude/ in CWD (Claude Code respects `.claude/` in the project for per-project settings overrides)
- `--help` — print usage and exit 0
- Unknown flags → print error + usage + exit 1

When both flags are given, install proceeds non-interactively. When neither is given, current interactive prompt runs (backward compatibility).

## Acceptance Criteria

- **AC-01:** `install.sh --help` exits 0 with a usage block listing all flags + defaults + examples.
- **AC-02:** `install.sh --client claude --scope global` installs non-interactively to `~/.claude/` (or `$CLAUDE_CONFIG_DIR` if set).
- **AC-03:** `install.sh --client claude --scope project` installs non-interactively to `./.claude/` in the current working directory.
- **AC-04:** `install.sh` with no flags falls back to current interactive behavior (client prompt). Backward compatible.
- **AC-05:** `install.sh --scope project` (no `--client`) prompts for client interactively but uses project scope.
- **AC-06:** `install.sh --client antigravity --scope project` resolves $TARGET_DIR to `./.gemini/antigravity/` in CWD.
- **AC-07:** Unknown flag (e.g., `--bogus`) → exit 1, error message + usage block to stderr.
- **AC-08:** Project-scope install creates `./.claude/` (or `./.gemini/antigravity/`) if absent.
- **AC-09:** Settings.json merge writes to `$TARGET_DIR/settings.json` regardless of scope (project install does NOT touch `~/.claude/settings.json`).
- **AC-10:** Summary block at end of install reports the effective $TARGET_DIR so operators see exactly where etc landed.
- **AC-11:** tests/test_install_sh_cli.py exercises --help (AC-01), unknown-flag (AC-07), and basic flag parsing happy paths.
- **AC-12:** README "Quick start" section is updated to document the new flags, with a short example for project-scope install.

## Out of Scope

- Replacing the install.sh implementation language (still bash).
- Marketing the project-scope install as the recommended path (it's an option, not a default).
- Backwards-incompat changes to global-scope install. Existing operators see no behavior change.
- Uninstaller / cleanup flag (`--uninstall`). Future work.
- License key / signed binary distribution. Deferred per `memory/project-plugin-packaging-strategy.md`.

## Technical Notes

- Flag parsing via a manual `while [[ $# -gt 0 ]]; case "$1" in ... esac; shift; done` loop. `getopts` doesn't support long-form flags portably; manual parsing is the etc convention (see how other CLI scripts in etc handle this).
- $TARGET_DIR resolution stays in one place (after flag parsing + interactive prompt fallback).
- When --scope project is used, the path rewrite step (install.sh:260+) DOES still run — it rewrites `~/.claude/` references to whatever $TARGET_DIR is, including project paths.
- Help output goes to stdout; error messages go to stderr.

## Dependencies

None beyond what install.sh already requires (bash 4+, jq, python3, optional rsync).
