# PRD: Python Installer Rewrite

## Summary

Replace the 526-line `install.sh` bash script with a thin (~30-line) bash
bootstrap that hands off to a Python module under `etc_installer/`. The
bootstrap exists solely to resolve the Python-toolchain chicken-and-egg:
detect `uv`, auto-install it via the official Astral curl bootstrap if
missing, then invoke `uv run --from . -m etc_installer <args>`. From there
the installer is Python — typer for argv, rich for terminal UX, no
shell-embedded Python heredocs, no jq, no PATH-probing without fallback.

The motivation is the existing installer's poor UX ("looks like shit") and
a growing feature backlog that bash absorbs poorly: an ANSI-truecolor
banner (`assets/etsy-logo.ascii`, jp2a output), a status-line installer
with overwrite-warning prompt, sandbox-config defaults, plus the existing
four third-party tool preflights (gh-stack, impeccable, Mergiraf,
@google/design.md). Each feature in bash adds another 50-100 lines of
fragile shell; the same features in Python compose cleanly.

The deliverable is an installer that is robust, testable, and just works
on a fresh machine. CLI surface (`--client`, `--scope`, `--help`) and the
four F010/F011/F016/F018 INFO_LINE strings are preserved byte-for-byte to
honor the pinned test contracts. Basic Windows support via Git Bash is
retained; full cross-platform parity (native PowerShell, Linux distro
coverage beyond bash) is explicit out-of-scope for this iteration.

## Scope

### In Scope

- Bash bootstrap (`install.sh`) reduced to ~30 lines: parse argv, detect
  `uv`, auto-install `uv` via `curl -LsSf https://astral.sh/uv/install.sh
  | sh` (Unix) or PowerShell variant (Windows under Git Bash, when
  reachable), hand off to `uv run --from . -m etc_installer "$@"`.
- Python installer module at `etc_installer/` (inline in repo, not
  published to PyPI for v1) using `typer` for the CLI and `rich` for
  terminal UX.
- Banner rendering of `assets/etsy-logo.ascii` (jp2a ANSI truecolor) at
  the top of `install`, gated by `sys.stdout.isatty()`. Banner content
  is written as raw bytes so rich does not re-interpret the embedded
  ANSI escapes.
- Preserve verbatim: `--client {claude|antigravity}`,
  `--scope {global|project}`, `--help`. Preserve verbatim the four
  `F010_INFO_LINE`, `F011_INFO_LINE`, `F016_INFO_LINE`,
  `F018_INFO_LINE` strings.
- Reproduce every install step the current script does: directory
  structure, agents, skills, standards (recursive), profiles (F020),
  hooks (`chmod +x`), settings.json merge (replace hooks section), SDLC
  tracker templates, templates, git hooks + scripts, `~/.claude/` path
  rewrite, F020 profile detection + lock write, summary.
- **Status-line installer**: interactive prompt
  "Install the etc default status line? This will overwrite your
  existing status line if you have one. [y/N]". On yes, install. Skip
  on no.
- **Sandbox-config defaults**: interactive prompt
  "Install the etc default sandbox config? This enables auto-mode
  without --dangerously-skip-permissions. [y/N]". On yes, write to the
  operator's settings.json. Skip on no.
- Windows Git Bash compatibility maintained: `cygpath` for
  `_to_native_path()` equivalents in Python (`pathlib.PureWindowsPath`
  + `subprocess.run(['cygpath', '-w', path])` fallback), no
  shell-quoted Python heredocs.
- Tests split: `tests/test_install_sh_cli.py` keeps testing bootstrap
  argv-parsing + uv-detection + hand-off; new
  `tests/test_etc_installer.py` covers the Python module via
  `typer.testing.CliRunner`. F010/F011/F016/F018 INFO_LINE pin
  assertions continue to live where they are.

### Out of Scope

- Full cross-platform parity (native PowerShell `install.ps1`, Linux
  distro coverage beyond bash, BSD, native macOS .pkg).
- Publishing `etc_installer` to PyPI.
- Self-update / version-pin mechanism.
- Post-install diagnostics or doctor command.
- TUI wizard with multi-step screens.
- Package-manager submissions (Homebrew formula, apt repo, MSI
  installer).
- Operator opt-out env vars or config files for the banner. (TTY-gating
  is sufficient; persistent off-switch is a follow-up.)
- License-key gating (deferred per project-plugin-packaging-strategy
  memory).

## Requirements

### BR-001: Bootstrap minimalism
`install.sh` is reduced to a ~30-line bash bootstrap whose entire job
is: parse argv (pass through to Python), detect `uv` on PATH,
auto-install `uv` if missing, then `exec uv run --from "$SCRIPT_DIR" -m
etc_installer "$@"`. The bootstrap MUST NOT contain shell-embedded
Python heredocs, jq dependencies, or hardcoded paths beyond
`$SCRIPT_DIR`. The line-count target is enforced by a lint test
(BR-009).

### BR-002: uv auto-install (no prompt)
When `uv` is not on PATH, the bootstrap installs it via the official
Astral installer (`curl -LsSf https://astral.sh/uv/install.sh | sh` on
Unix; the PowerShell equivalent invoked through Git Bash on Windows).
The install runs without prompting the operator. If the install fails
(network error, curl missing), the bootstrap exits non-zero with a
single-line error pointing at the Astral docs.

### BR-003: Python module location and invocation
The Python installer lives at `etc_installer/` in the repo root, with
at minimum `__init__.py`, `__main__.py`, and a `cli.py` exposing a
`typer.Typer()` app. The bootstrap invokes it via `uv run --from
"$SCRIPT_DIR" -m etc_installer "$@"`. `pyproject.toml` declares
`etc_installer` as a package with `typer`, `rich` as runtime
dependencies (alongside the existing `pyyaml`).

### BR-004: CLI argv compatibility
The Python module preserves the existing argv surface byte-for-byte:
`--client {claude|antigravity}`, `--scope {global|project}`, `--help`,
plus the no-args interactive mode. Unknown flags exit non-zero with the
same usage text shape as today. The existing `tests/test_install_sh_cli.py`
assertions continue to pass against `install.sh ...` invocations
(which now route through the bootstrap → Python).

### BR-005: INFO_LINE preservation
The four verbatim strings — `F010_INFO_LINE`, `F011_INFO_LINE`,
`F016_INFO_LINE`, `F018_INFO_LINE` — defined in `install.sh:196-199`
are reproduced byte-for-byte in `etc_installer/preflights.py` (or
equivalent). The existing pin assertions in `tests/test_design_skill.py`
and `tests/test_build_stacked_prs.py` continue to pass.

### BR-006: Banner display
`etc_installer/banner.py` reads `assets/etsy-logo.ascii` and writes
its raw bytes to `sys.stdout` BEFORE any rich-managed output, gated by
`sys.stdout.isatty()`. Non-TTY invocations (CI, piped, redirected)
skip the banner. Rich's Console is initialized with
`highlight=False, markup=False` for the banner write path so the
pre-rendered ANSI escapes are not re-interpreted.

### BR-007: Status-line installer prompt
During interactive install (no `--client` flag), after client
selection, the installer prompts: `Install the etc default status
line? This will overwrite your existing status line if you have one.
[y/N]`. On `y` / `yes`, the installer writes a status-line snippet to
`$TARGET_DIR/settings.json` (`statusLine` key) and copies any required
`statusline.sh` to `$TARGET_DIR/scripts/`. On `n` (default) or empty
input, the step is skipped. Non-interactive runs (`--client` flag set)
skip the prompt entirely and do NOT install the status line.

### BR-008: Sandbox-config defaults prompt
During interactive install, after the status-line prompt, the
installer prompts: `Install the etc default sandbox config? This
enables auto-mode without --dangerously-skip-permissions. [y/N]`. On
`y` / `yes`, the installer merges the sandbox defaults into
`$TARGET_DIR/settings.json` (`permissions.defaultMode`,
`permissions.allow`, `permissions.ask`, `permissions.deny` keys). On
`n` (default), the step is skipped. Non-interactive runs skip the
prompt.

### BR-009: Test split
`tests/test_install_sh_cli.py` is refactored to test ONLY the
bootstrap layer: argv pass-through, uv detection, exit codes from
missing uv when install fails. Deeper install behavior moves to a new
`tests/test_etc_installer.py` testing the Python module via
`typer.testing.CliRunner`. A new bootstrap-line-count test fails if
`install.sh` exceeds 50 LOC (BR-001 ceiling with headroom).

### BR-010: Windows Git Bash compatibility
The Python module handles POSIX→Windows path conversion via
`pathlib.PureWindowsPath` and a `cygpath` shell-out helper (analogous
to `_to_native_path()`). The bootstrap detects MINGW/MSYS/CYGWIN via
`uname -s` and uses platform-appropriate uv install invocation. No
shell-embedded Python heredocs anywhere in the bootstrap.
`tests/test_windows_compatibility.py` continues to pass.

### BR-011: Install-step parity
The Python installer reproduces every install step the current bash
script performs: directory structure, agents (md files), skills (full
directory trees with rsync-equivalent fallback), standards (recursive
subdir discovery), profiles (F020 — recursive copy with chmod +x on
gate scripts), hooks (chmod +x), settings.json hook-wiring merge (now
via pure Python — no shell-embedded heredoc), SDLC tracker templates,
templates (`.tmpl` files), git hooks + scripts, `~/.claude/` path
rewrite (sed-equivalent in Python `pathlib`), F020 profile detection +
`.etc_sdlc/profiles.lock` write, summary block.

### BR-012: No silent failure modes
Every install step prints a status line via `rich.Console` (`✓` on
success, `⚠` on warning, `✗` on error). Failures of optional steps
(e.g., F020 profile detection on a project without language signals)
print a warning and continue. Failures of load-bearing steps (missing
`dist/`, settings.json merge failure) exit non-zero with a one-line
error.

## Acceptance Criteria

1. **AC-001 — Bootstrap line count.** `install.sh` is ≤ 50 lines of
   executable code (excluding comments and blank lines). A test
   `tests/test_install_sh_cli.py::test_bootstrap_line_count_under_50`
   asserts this.
2. **AC-002 — uv auto-install, no prompt.** Running `./install.sh` on a
   machine without `uv` on PATH triggers an automatic uv install. No
   interactive prompt fires for uv installation. If the install fails,
   the bootstrap exits non-zero with a one-line error mentioning the
   Astral docs URL.
3. **AC-003 — Python module importable.** `python3 -c "import
   etc_installer; print(etc_installer.__name__)"` prints `etc_installer`
   from the repo root.
4. **AC-004 — CLI argv preservation.** `./install.sh --help` prints
   usage text that includes the literal substrings `--client`,
   `--scope`, `claude|antigravity`, and `global|project`.
   `./install.sh --unknown-flag` exits non-zero and prints usage to
   stderr.
5. **AC-005 — INFO_LINE byte-for-byte.** The four strings
   `F010_INFO_LINE`, `F011_INFO_LINE`, `F016_INFO_LINE`,
   `F018_INFO_LINE` defined at `install.sh:196-199` appear
   byte-for-byte in `etc_installer/preflights.py` (or whichever module
   exposes them). The existing pin assertions in
   `tests/test_design_skill.py` and `tests/test_build_stacked_prs.py`
   continue to pass.
6. **AC-006 — Banner is TTY-gated.** When `sys.stdout.isatty()` is
   True, the install starts by writing the raw bytes of
   `assets/etsy-logo.ascii` to stdout. When stdout is piped or
   redirected, no logo bytes appear in the output. A test
   `tests/test_etc_installer.py::test_banner_skipped_when_not_tty`
   asserts this.
7. **AC-007 — Status-line prompt verbatim.** Interactive install (no
   `--client` flag) prints `Install the etc default status line? This
   will overwrite your existing status line if you have one. [y/N]`
   exactly, then waits for input. On `y` / `yes`, the status line is
   installed; on `n` (default) or empty input, the step is skipped.
8. **AC-008 — Sandbox-config prompt verbatim.** Interactive install
   prints `Install the etc default sandbox config? This enables
   auto-mode without --dangerously-skip-permissions. [y/N]` exactly.
   On `y` / `yes`, the sandbox defaults are merged into the target
   settings.json `permissions` block.
9. **AC-009 — Test split.** `tests/test_install_sh_cli.py` covers only
   bootstrap behavior (argv parsing, uv detection, hand-off).
   `tests/test_etc_installer.py` exists and covers the Python module
   via `typer.testing.CliRunner`. Both pass under `python3 -m pytest`.
10. **AC-010 — Windows compat.** `tests/test_windows_compatibility.py`
    passes against the new installer. Under Git Bash on Windows
    (uname returns `MINGW*`), the installer completes without
    `unicodeescape` errors and without falling into the Microsoft Store
    python3 stub trap.
11. **AC-011 — Install-step parity.** Running
    `./install.sh --client claude --scope project` against a fresh CWD
    produces the same set of installed files (by path and content) as
    the current `install.sh` produces. A parity test
    `tests/test_etc_installer.py::test_install_step_parity` captures
    the current install's output and diffs against the new install's
    output.
12. **AC-012 — Status-line discipline.** Every install step in
    `etc_installer/cli.py` emits exactly one status line via
    `rich.Console` prefixed with `✓` (success), `⚠` (warning), or `✗`
    (error). A test asserts the count of emitted lines matches the
    expected step count.
13. **AC-013 — Missing-dist preflight.** Running `./install.sh` in a
    repo without `dist/` exits non-zero and prints a one-line error
    mentioning `compile-sdlc.py`.

## Edge Cases

1. **uv install fails** (network down, curl missing, Astral domain
   blocked, install script returns non-zero). Bootstrap exits non-zero
   with a one-line error including the Astral docs URL. No partial
   install state is left behind.
2. **`dist/` directory missing.** Existing preflight at
   `install.sh:118` is preserved: print error mentioning `compile-sdlc.py
   spec/etc_sdlc.yaml`, exit 1. New bootstrap delegates this check to
   the Python module so the message is single-source.
3. **`./install.sh` run from raw cmd.exe on Windows** (no Git Bash).
   Bootstrap is a `.sh` file; cmd.exe cannot execute it. The README
   points Windows operators to Git Bash; this is the published
   constraint. No code change needed beyond the existing F004 README
   guidance.
4. **`assets/etsy-logo.ascii` missing.** Banner step prints
   `⚠ banner asset not found at assets/etsy-logo.ascii — continuing`
   and proceeds. Banner is decorative, not load-bearing.
5. **Existing `settings.json` is invalid JSON.** Settings-merge step
   prints `✗ settings.json at <path> is not valid JSON — skipping
   merge` and continues with the remaining install steps. Final exit
   code is non-zero so operator sees the failure.
6. **Operator answers `y` to status-line prompt and overwrites a
   custom status line.** Operator was warned in the prompt text ("will
   overwrite your existing status line if you have one"). Overwrite is
   the documented behavior on `y`. No undo.
7. **`python3` exists but is the Microsoft Store stub** (Windows). The
   bootstrap uses `uv` to manage Python — it never calls `python3`
   directly. The stub trap from
   `memory/feedback-windows-install-portability.md` is bypassed by
   design.
8. **Operator passes `--scope project` from a directory without write
   permission.** Python installer fails on first file write with a
   `PermissionError`; rich prints
   `✗ cannot write to <path>: Permission denied`; exit 1.
9. **Truecolor terminal not detected** (e.g., `TERM=dumb` or rendering
   through `less`). `rich.Console.color_system` returns `None` or
   `'standard'`; banner is still emitted as raw ANSI bytes (per BR-006
   — banner is jp2a output, not rich-rendered). Some operators may see
   raw escape sequences; documented in the README as a known
   limitation; out-of-scope to fall back to plain-text banner for v1.
10. **uv on PATH is an older version** missing `--from`. uv has
    supported `--from` since v0.4 (March 2025). If hit, the `uv run`
    invocation fails; bootstrap surfaces uv's stderr and exits
    non-zero. Operator can `uv self update` and retry.
11. **Concurrent `./install.sh` invocations against the same
    TARGET_DIR.** Race conditions on file writes are possible
    (last-writer-wins). Documented as not-supported; out-of-scope for
    v1.
12. **`$HOME` path with spaces or non-ASCII characters.** Python
    `pathlib` handles natively; cygpath wrapper preserves existing
    Windows-path-with-spaces behavior.
    `tests/test_windows_compatibility.py::test_install_with_spaces_in_home`
    covers.
13. **F020 profile detection fails** (no profile signals in CWD).
    Existing behavior preserved: print warning, write empty
    `.etc_sdlc/profiles.lock`, continue.
14. **Operator cancels at the status-line or sandbox-config prompt
    with Ctrl+C.** Python module catches `KeyboardInterrupt`, prints
    `\n✗ install cancelled by operator`, exits 130 (standard SIGINT
    convention).
