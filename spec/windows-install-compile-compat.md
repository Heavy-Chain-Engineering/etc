# PRD: Windows Install + Compile Compatibility Fix

## Summary

A Heavy Chain Engineering partner attempted to install `Heavy-Chain-Engineering/etc-internal` HEAD `3d958c6` on Windows under Git Bash on 2026-05-04 and hit two distinct bugs that block every Windows install of the harness. **Bug A:** `install.sh` line 147 (the settings.json merge step) embeds a Python heredoc that receives a path like `/c/Users/name/.claude/settings.json` (Git Bash's representation of a Windows path), and Windows-native `python3` can't open `/c/...`-style paths — it expects `C:\...` or `C:/...`. The heredoc fails; `install.sh` bails; steps 7-9 (sdlc tracker, templates, git hooks, scripts) skip silently. The partner manually finished the install. Phase 2 codebase research uncovered that **`install.sh` line 224 (the HOOK_EVENTS counter) has the same bug but masks it** — `2>/dev/null || echo "    (run python3 to see details)"` swallows the error and prints a fallback. Every Windows install has been silently degraded at line 224 too; partners just see the fallback instead of actual hook-event counts. **Bug B:** `compile-sdlc.py` runs Python in Windows-default cp1252 mode and chokes on UTF-8 characters in source files (em-dashes, smart quotes, arrows, box-drawing) that the harness uses throughout skill bodies, standards docs, agents, and hooks. The partner worked around it with `set PYTHONUTF8=1` but the harness should not require this.

This refactor ships the durable fix for both bugs in one PRD. **Bug A fix:** add a small bash helper `_to_native_path()` at the top of `install.sh` that detects Windows shell environments via `uname -s` matching `MINGW*|MSYS*|CYGWIN*` and runs the path through `cygpath -w` when matched, passing through unchanged otherwise. Apply the helper inline at both heredoc call sites (line 147 and line 224) so paths are translated before they reach Windows-native Python. No new shell-helper file under `scripts/` — the harness convention is Python helpers there, and centralizing inside `install.sh` keeps the cross-cutting concern co-located with its consumers. **Bug B fix:** add explicit `encoding="utf-8"` keyword arguments to all 9 text-mode file-open sites in `compile-sdlc.py` (mix of `open()`, `Path.read_text()`, `Path.write_text()`). Right durable fix, small surface, eliminates the env-var workaround entirely. Line 527's binary-mode `open(ruff_toml_path, "rb")` is correctly excluded.

This PRD also adds a new contract test file `tests/test_windows_compatibility.py` with grep-based assertions over the modified `install.sh` and `compile-sdlc.py` source — verifying the helper function exists, both heredocs invoke it, every text-mode file-open site has the encoding kwarg, and the prior bug-prone patterns (raw `/c/` paths in heredocs, encoding-less `open()` calls) no longer appear. Tests run on macOS/Linux without a Windows VM by asserting source-content patterns rather than runtime behavior; that matches F001/F002/F003's grep-based contract test posture and the harness's existing `tests/test_compiler.py` pattern. After F004 ships, every Windows partner gets a clean install on the next pull + compile + install cycle, and silent failures at the line-224 hook-event counter are eliminated.

## Scope

### In Scope
- Add a small bash helper function `_to_native_path()` at the top of `install.sh` that detects Windows shell environments via `uname -s` matching `MINGW*|MSYS*|CYGWIN*` and runs paths through `cygpath -w` when matched, passing through unchanged otherwise.
- Apply `_to_native_path()` to all path arguments passed into both python3 heredocs in `install.sh`:
  - Line 147 (`merge_settings` function — opens `$SETTINGS` and `$HOOKS_TEMPLATE`)
  - Line 224 (HOOK_EVENTS counter — opens `$HOOKS_TEMPLATE`)
- Add explicit `encoding="utf-8"` keyword arguments to all 9 text-mode file-open sites in `compile-sdlc.py` (lines 30, 180, 351, 367, 407, 467, 565, 668, 715).
- Create a new contract test file `tests/test_windows_compatibility.py` with the six grep-based assertions enumerated in BR-006.
- Compile pipeline integration: `python3 compile-sdlc.py spec/etc_sdlc.yaml` continues to complete without error after the encoding kwargs are added.
- No-Windows-VM test posture: tests assert source-content patterns rather than runtime behavior.

### Out of Scope
- A full Windows CI pipeline (separate concern; would require a Windows runner).
- Cygwin or MSYS2 native install support beyond Git Bash.
- WSL support (WSL is Linux from the harness's perspective; unaffected).
- Encoding fixes outside `compile-sdlc.py`.
- Path-translation issues elsewhere in the harness.
- Removal of the existing `command -v python3` guard at install.sh:164.
- Modifications to other Python scripts under `scripts/`.
- Modifications to other agents, skills, or standards docs.
- Backfill of existing user installs.
- A standalone `scripts/path-convert.sh` helper.
- `os.environ["PYTHONUTF8"] = "1"` shim at compile-sdlc.py top.

## Requirements

### BR-001: Windows Shell Detection Helper in install.sh
A new bash helper function MUST be defined at the top of `install.sh` (immediately after the existing `info`/`warn`/`error` log helpers, before the preflight check):

```bash
_to_native_path() {
    # Convert Git-Bash/MSYS2/Cygwin path to Windows-native path when
    # running under those shells; pass through unchanged on macOS/Linux.
    local path="$1"
    case "$(uname -s)" in
        MINGW*|MSYS*|CYGWIN*)
            cygpath -w "$path"
            ;;
        *)
            printf '%s' "$path"
            ;;
    esac
}
```

The function MUST:
- Detect Windows shells via `uname -s` matching `MINGW*`, `MSYS*`, or `CYGWIN*`.
- Run the input path through `cygpath -w` on Windows shells.
- Pass through unchanged on macOS/Linux/WSL.
- Take exactly one path argument; return the converted path on stdout.

### BR-002: Apply Helper at Both python3 Heredocs in install.sh
The path arguments passed into `install.sh`'s python3 heredocs MUST be wrapped with `_to_native_path()` BEFORE entering the heredoc:

- **Line 147 (`merge_settings` function):** the heredoc currently embeds `$SETTINGS` and `$HOOKS_TEMPLATE` directly inside the Python `open(...)` calls. Both MUST be replaced with shell-expanded versions of `$(_to_native_path "$SETTINGS")` and `$(_to_native_path "$HOOKS_TEMPLATE")`.
- **Line 224 (HOOK_EVENTS counter):** the heredoc embeds `$HOOKS_TEMPLATE` directly. MUST be replaced with `$(_to_native_path "$HOOKS_TEMPLATE")`.

### BR-003: Explicit UTF-8 Encoding at All compile-sdlc.py File-Open Sites
Every text-mode `open()`, `Path.read_text()`, and `Path.write_text()` invocation in `compile-sdlc.py` MUST include an explicit `encoding="utf-8"` keyword argument. The 9 text-mode sites (per Phase 2 research):

- Line 30: `with open(spec_path) as f:` → `with open(spec_path, encoding="utf-8") as f:`
- Line 180: `out_path.write_text(content)` → `out_path.write_text(content, encoding="utf-8")`
- Line 351: `(skill_dir / "SKILL.md").write_text(content)` → add `encoding="utf-8"`
- Line 367: `(skill_dir / "SKILL.md").write_text(content)` → add `encoding="utf-8"`
- Line 407: `with open(sdlc_dir / "dod-templates.json", "w") as f:` → add `encoding="utf-8"`
- Line 467: `text = inv_file.read_text()` → add `encoding="utf-8"`
- Line 565: `content = md_file.read_text()` → add `encoding="utf-8"`
- Line 668: `with open(dist_dir / "settings-hooks.json", "w") as f:` → add `encoding="utf-8"`
- Line 715: `inv_file.read_text()` → add `encoding="utf-8"`

### BR-004: Detection Mechanism Documented in install.sh
The `_to_native_path()` function MUST include an inline comment explaining the detection mechanism (the `MINGW*|MSYS*|CYGWIN*` pattern and what it matches).

### BR-005: Binary-Mode File Open at Line 527 Documented as Intentional Skip
The `open(ruff_toml_path, "rb")` at compile-sdlc.py line 527 is a binary-mode read, so `encoding="utf-8"` is not applicable. The PRD's contract test MUST account for this — counting only the 9 text-mode file-open sites.

### BR-006: Contract Test Coverage
A new test file `tests/test_windows_compatibility.py` MUST exist and pass, containing at minimum:

- `test_install_sh_defines_to_native_path_helper` — confirms `install.sh` contains the `_to_native_path()` function definition with the `MINGW*|MSYS*|CYGWIN*` case match and the `cygpath -w` call.
- `test_install_sh_heredoc_paths_use_helper` — greps `install.sh` for both python3 heredocs and asserts paths use the `_to_native_path` wrapping.
- `test_install_sh_no_unwrapped_paths_in_heredocs` — negative assertion: zero matches for unwrapped `open('$SETTINGS')` or `open('$HOOKS_TEMPLATE')` patterns inside python3 heredocs.
- `test_compile_sdlc_text_opens_have_utf8_encoding` — greps `compile-sdlc.py` for all text-mode file-open calls and asserts every one has `encoding="utf-8"`.
- `test_compile_sdlc_binary_open_is_intentional` — asserts the line-527 `open(ruff_toml_path, "rb")` binary-mode read remains unchanged.
- `test_compile_sdlc_no_encoding_less_text_opens` — negative assertion: zero text-mode `open()` calls without `encoding=` kwarg.

### BR-007: No-Windows-VM Test Posture
Contract tests MUST run on macOS/Linux/CI without requiring a Windows VM. Tests assert source-content patterns rather than runtime behavior. Tests MUST NOT invoke `cygpath`, MUST NOT call `uname` to verify the detection logic at runtime, and MUST NOT spawn subprocesses other than the standard `compile-sdlc.py` invocation in the autouse fixture.

### BR-008: Compile Pipeline Integration
`python3 compile-sdlc.py spec/etc_sdlc.yaml` MUST complete without error after the `encoding="utf-8"` additions. On non-Windows systems, the kwarg is a no-op.

### BR-009: Backward Compatibility with Existing Installs
The bash helper and encoding kwargs MUST NOT break existing installs on macOS/Linux. `_to_native_path()` returns the input unchanged on uname=Darwin/Linux. `encoding="utf-8"` is a no-op when the system's default encoding is UTF-8.

### BR-010: Forward-Only Behavior
The PRD does NOT modify legacy installs in place. Operators who manually worked around the bugs get the durable fix on their next pull + compile + install cycle. No migration script, no auto-cleanup of manual workarounds.

## Acceptance Criteria

1. `install.sh` contains a `_to_native_path()` bash function defined near the top of the file. The function body includes a `case "$(uname -s)"` block with `MINGW*|MSYS*|CYGWIN*` patterns and a `cygpath -w "$path"` invocation.
2. `install.sh` line 147's `merge_settings` heredoc opens both `$SETTINGS` and `$HOOKS_TEMPLATE` paths through `_to_native_path()`. The heredoc body contains `$(_to_native_path "$SETTINGS")` and `$(_to_native_path "$HOOKS_TEMPLATE")`.
3. `install.sh` line 224's HOOK_EVENTS counter heredoc opens `$HOOKS_TEMPLATE` through the helper. Heredoc body contains `$(_to_native_path "$HOOKS_TEMPLATE")`.
4. `install.sh` does NOT contain unwrapped `open('$SETTINGS')` or `open('$HOOKS_TEMPLATE')` patterns inside its python3 heredocs.
5. `compile-sdlc.py` contains exactly 9 text-mode file-open sites, each with `encoding="utf-8"`. Line 527's `open(ruff_toml_path, "rb")` is binary-mode and correctly omits the kwarg.
6. `compile-sdlc.py` does NOT contain any text-mode `open()` calls without `encoding=` keyword argument.
7. `tests/test_windows_compatibility.py` exists with the six tests from BR-006. `pytest tests/test_windows_compatibility.py -q` reports all 6 tests passing.
8. Contract tests use the same autouse session-scoped compile fixture pattern as F001/F002/F003 with the explicit `_ = _compile_sdlc` Pyright workaround.
9. `python3 compile-sdlc.py spec/etc_sdlc.yaml` completes without error. On macOS/Linux, the kwargs are no-ops; the compile output is byte-identical to pre-edit.
10. `dist/` artifacts remain byte-identical to source after the encoding kwarg additions (no behavioral change).
11. Contract tests run on macOS/Linux without invoking `cygpath`, `uname`, or any Windows-specific subprocess.
12. `install.sh` continues to operate correctly on macOS/Linux. `_to_native_path()` returns input unchanged on Darwin/Linux uname values.
13. `install.sh` continues to operate correctly under WSL (uname=Linux). The case statement does not match WSL's uname.
14. The PRD adds no validator, scanner, or skill step that retroactively scans existing installs. Forward-only per BR-010.
15. Existing tests in the repository continue to pass. `pytest tests/ -q` reports no new failures (regression baseline; should be 686 + 6 = 692 after F004).
16. No agents, skills, standards, or hooks are modified by F004. Only `install.sh`, `compile-sdlc.py`, and the new `tests/test_windows_compatibility.py` are touched.
17. `tests/test_compiler.py` and `tests/test_inject_standards.py` are NOT modified by this PRD. F004's tests live in their own file per GA-004.

## Edge Cases

1. **`cygpath` is not on PATH on a Windows machine.** Possible if Git Bash install is incomplete. Mitigation: `_to_native_path()` checks `command -v cygpath` and surfaces a clear error.
2. **`cygpath -w` produces backslashes in the output path.** Python's `open()` accepts both forward and back slashes on Windows. No additional escaping needed.
3. **Path contains spaces.** `$(_to_native_path "$SETTINGS")` form with double-quotes preserves spaces.
4. **User runs install.sh from PowerShell or cmd.exe directly.** install.sh is a bash script; PowerShell/cmd can't execute it. Out of scope: the partner's setup is Git Bash.
5. **`uname` is not available.** Vanishingly rare. The case statement falls through to `*)` and returns the path unchanged.
6. **Future commit adds a third python3 heredoc to install.sh.** GA-001's centralized helper is reusable; AC4's negative assertion catches new offenders that bypass the helper.
7. **Future commit adds a new file-open site to `compile-sdlc.py` without `encoding="utf-8"`.** AC6's negative assertion catches this.
8. **`compile-sdlc.py` line 527 is moved or removed.** The contract test should compute N at test-time (counting text-mode opens dynamically) rather than hardcoding line 527.
9. **`cygpath` returns a UNC path** (`\\wsl$\...`). Python's `open()` handles UNC paths on Windows.
10. **macOS user with locale set to non-UTF-8.** The encoding kwarg forces UTF-8 regardless of locale.
11. **`_to_native_path` shadowed by environment variable or alias.** Bash function definitions override prior definitions.
12. **install.sh run with `sh` (not `bash`).** The `case` syntax is POSIX-compliant; should work.
13. **Contract test grep finds a false positive in a comment.** Mitigation: preprocess by stripping `#` comments before grepping.
14. **PEP 686 future-proofing.** Python 3.15+ deprecates platform-default encoding. F004's kwargs become essential then.
15. **MSYS2 bundled Python that handles `/c/...` paths natively.** `cygpath -w` produces a Windows path; MSYS2 Python opens it correctly. No regression.
16. **F001/F002/F003 independence.** F004 doesn't touch the orphan-surface defense files.

## Technical Constraints

- **File touchpoints (small, surgical):** edits two existing files (`install.sh`, `compile-sdlc.py`), creates one new file (`tests/test_windows_compatibility.py`).
- **install.sh is bash.** `_to_native_path()` is a bash function defined inline.
- **compile-sdlc.py is Python 3.** `encoding="utf-8"` kwarg supported since Python 3.0.
- **No new shell helpers under scripts/.** Per GA-001, the helper lives inline in install.sh.
- **No new env-var dependencies.** PYTHONUTF8 is not set or required.
- **Compile pipeline:** unchanged behaviorally on non-Windows.
- **No Pattern A / Pattern B prompts added.** install.sh and compile-sdlc.py are non-interactive.
- **Backward compatibility preserved on macOS/Linux/WSL.**
- **Forward-only application.** No migration of manual workarounds.
- **Test precedent:** follows F001/F002/F003 grep-based contract test pattern.
- **No-Windows-VM test posture (BR-007).**
- **F001/F002/F003 independence.**
- **Missing infrastructure:** INVARIANTS.md and `.etc_sdlc/antipatterns.md` absent.
- **PEP 686 future-proofing:** Python 3.15+ will require explicit encoding.
- **The Sonnet/Opus-1M child-dispatch bug:** F004's /build pipeline will use `model: opus` override, same workaround as F002+F003.

## Security Considerations

This feature does not handle authentication, user input validation at system boundaries, data storage, file uploads, external APIs, or authorization. The security-relevant considerations:

- **`cygpath -w` operates on operator-supplied path values.** Paths are derived from `$HOME` and the install script's working directory. No user-typed runtime input. No injection vector.
- **The bash helper does NOT eval or execute path content.** `cygpath -w` is a pure path-translation utility.
- **No new Python `open()` calls with untrusted paths.** Only the encoding kwarg is added.
- **`encoding="utf-8"` is more strict than platform default.** Malicious non-UTF-8 files would FAIL the read with `UnicodeDecodeError`, surfacing the issue rather than allowing it. Security improvement.
- **The contract test is read-only.** Grep-style assertions over committed files; no network, no shell escapes, no writes outside pytest tmpdir.
- **`cygpath` invocation does not pass shell metacharacters unsanitized.** Standard double-quoted variable expansion.
- **No secret material.** No credentials, tokens, API keys.
- **Forward-only is security-adjacent.** Pre-F004 manual workarounds are not corrupted; re-running install.sh overwrites them with canonical state.
- **The detection mechanism is not bypassable by malicious uname.** uname output is set by the shell itself, not by user-mutable env vars.
- **No new external dependencies.** `cygpath` ships with all three Windows shell environments; `uname` is POSIX-mandatory.
- **install.sh continues to write outside the project tree (~/.claude/).** Existing behavior; F004 does not change it.

## Module Structure

Files to create or modify:

- **Modified:** `install.sh` — add `_to_native_path()` bash helper at top of file (after existing `info`/`warn`/`error` log helpers, before preflight check). Apply helper at both python3 heredoc call sites: line 147 (`merge_settings`) and line 224 (HOOK_EVENTS counter).
- **Modified:** `compile-sdlc.py` — add explicit `encoding="utf-8"` keyword argument to all 9 text-mode file-open sites (lines 30, 180, 351, 367, 407, 467, 565, 668, 715). Line 527's binary-mode `open(ruff_toml_path, "rb")` correctly excluded.
- **Created:** `tests/test_windows_compatibility.py` — six grep-based contract tests (BR-006). Same autouse session-scoped compile fixture as F001/F002/F003 with the explicit `_ = _compile_sdlc` Pyright workaround.
- **Created:** `.etc_sdlc/features/F004-windows-install-compile-compat/spec.md` — this PRD.
- **Created:** `.etc_sdlc/features/F004-windows-install-compile-compat/value-hypothesis.yaml` — outcome contract.
- **Created:** `.etc_sdlc/features/F004-windows-install-compile-compat/state.yaml` — Phase 2.75 classification (`research-assisted`) + author_role: SME/PM.
- **Created:** `.etc_sdlc/features/F004-windows-install-compile-compat/gray-areas.md` — 4 entries (3 research, 1 user).
- **Created:** `.etc_sdlc/features/F004-windows-install-compile-compat/research/` — at least `codebase.md` capturing the silent-line-224 finding.
- **Created (byte-identical copy):** `spec/windows-install-compile-compat.md` — for browsability.

Files explicitly NOT touched:

- `compile-sdlc.py` lines outside the 9 text-mode file-open sites — only kwargs added.
- `agents/spec-enforcer.md` — F002 territory.
- `skills/spec/SKILL.md`, `skills/build/SKILL.md`, `skills/decompose/SKILL.md`, all other skills.
- `standards/process/user-flow-completeness.md` (F001+F002+F003 doc).
- Other process standards.
- `hooks/inject-standards.sh` and other hooks.
- Other Python scripts under `scripts/`.
- Other shell scripts under `hooks/`.
- `tests/test_compiler.py` and `tests/test_inject_standards.py` (per GA-004).
- F001/F002/F003 contract test files.
- Legacy partner installs (forward-only per BR-010).
- `spec/etc_sdlc.yaml`.

## Research Notes

**Codebase findings (Phase 2):**

- **install.sh has TWO python3 heredocs**, not just one. Line 147 (`merge_settings`) is what the partner reported. Line 224 (HOOK_EVENTS counter) has the same bug but masks it via `2>/dev/null || echo "    (run python3 to see details)"`. Every Windows install has been silently degraded at line 224.
- compile-sdlc.py has 10 file-open sites total: 9 text-mode (need `encoding="utf-8"`) + 1 binary-mode at line 527 (correctly excluded).
- `scripts/` contains Python helpers only. Adding `scripts/path-convert.sh` would be inconsistent with the convention.
- `tests/test_compiler.py` exists as the closest-scope test file; per GA-004, F004's tests land in a new file matching the F001/F002/F003 pattern.
- INVARIANTS.md absent; `.etc_sdlc/antipatterns.md` absent.

**Best practices (light pass — proposal grounded in partner report + standard cross-platform patterns):**

- `cygpath -w` is the canonical Git-Bash/MSYS2/Cygwin → Windows-native path-translation tool.
- `uname -s` matching `MINGW*|MSYS*|CYGWIN*` is the de-facto detection pattern for Windows shell environments.
- Explicit `encoding="utf-8"` on Python file opens is PEP 686-aligned future-proofing (Python 3.15+ deprecates platform default).

**Antipatterns:** No `.etc_sdlc/antipatterns.md`. Nothing to incorporate.

**Process standards consulted:**
- `standards/process/interactive-user-input.md` — Pattern A/B; F004 adds no user-facing prompts.
- `standards/process/harness-feedback-loop.md` — defines the harness-feedback emission contract.

**F001/F002/F003 independence:** F004 is unrelated to the orphan-surface defense. The standards doc and the F001/F002/F003 contract test files are unchanged.
