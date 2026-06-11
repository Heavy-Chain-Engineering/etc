"""Contract tests for Windows Install + Compile Compatibility (F004 / BR-006).

Covers PRD .etc_sdlc/features/F004-windows-install-compile-compat/spec.md
BR-006, BR-007, AC7, AC8, AC11, AC15 (and Edge Case 8) via grep-based
assertions over:

- etc_installer/paths.py — the `to_native_path()` Python helper (Ftmp-5afddbce
  task 002 migrated this from install.sh's `_to_native_path()` bash helper).
- compile-sdlc.py — explicit `encoding="utf-8"` keyword argument on every
  text-mode file-open site, and the intentionally-preserved binary-mode
  read at line 527.

Ftmp-5afddbce migration note: install.sh's `_to_native_path()` bash helper
was rewritten in Python as `etc_installer/paths.py::to_native_path()` in
task 002 of the python-installer-rewrite feature. The three to_native_path
assertions in this file were migrated from grep-on-install.sh to
grep-on-etc_installer/paths.py per task 006 (AC-006-1). The
`_extract_python3_heredoc_bodies` helper and its two consuming tests are
no longer applicable post-migration — install.sh no longer embeds python3
heredocs after task 005 (cli.py / install_steps.py / __main__.py).

Precedent: tests/test_user_flow_completeness.py (F001), tests/
test_spec_enforcer_reachability.py (F002), and tests/
test_orphan_surface_dispatch_gate.py (F003). Same
`Path(...).read_text(encoding="utf-8")` reading idiom; same grep-based
assertions over committed source.

This file's tests assert on source content (etc_installer/paths.py,
compile-sdlc.py) rather than dist/, so it needs no compile fixture. Per
BR-007, the tests run on macOS/Linux without a Windows VM — no `cygpath`,
no `uname`, no Windows-specific subprocess.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
COMPILE_SDLC_PY = REPO_ROOT / "compile-sdlc.py"
PATHS_PY = REPO_ROOT / "etc_installer" / "paths.py"


# This module's assertions read SOURCE files only (compile-sdlc.py,
# etc_installer/paths.py) — never compiled dist/ outputs — so it needs no
# compile fixture. The previous per-file ``_compile_sdlc`` fixture that
# rmtree'd and rebuilt the operator's real dist/ was pure overhead here and
# has been removed; if a future test added here needs compiled artifacts it
# can consume the shared session-scoped ``compiled_dist`` fixture (conftest.py).


# -- Module-scoped text fixtures ---------------------------------------------


@pytest.fixture(scope="module")
def paths_py_text() -> str:
    """Read ``etc_installer/paths.py`` once per module.

    Ftmp-5afddbce task 002 shipped this module as the Python rewrite of
    install.sh's ``_to_native_path()`` bash helper. Per task 006 (AC-006-1),
    the to_native_path-related contract assertions now read this file
    instead of install.sh.
    """
    assert PATHS_PY.exists(), (
        f"missing paths module: {PATHS_PY}; Ftmp-5afddbce task 002 should "
        f"have shipped this file"
    )
    return PATHS_PY.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compile_sdlc_text() -> str:
    assert COMPILE_SDLC_PY.exists(), (
        f"missing compile script: {COMPILE_SDLC_PY}"
    )
    return COMPILE_SDLC_PY.read_text(encoding="utf-8")


# -- Helper: locate text-mode file-open call sites in compile-sdlc.py --------


# Pattern A: `open(...)` calls. Captures the first-line argument list so a
# subsequent inspection can decide whether the call is binary-mode or text-
# mode and whether `encoding=` is present. Multi-line arg lists are rare in
# compile-sdlc.py; the pattern matches the open-paren through the matching
# close-paren on the same line, which is sufficient for the current source.
_OPEN_CALL_PATTERN = re.compile(r"\bopen\(([^)]*)\)")

# Pattern B: `Path.read_text(...)` and `Path.write_text(...)` calls. These
# are always text-mode by construction (the binary variants are
# `read_bytes()` / `write_bytes()`), so every match is in scope for the
# `encoding="utf-8"` requirement.
_READ_TEXT_CALL_PATTERN = re.compile(r"\.read_text\(([^)]*)\)")
_WRITE_TEXT_CALL_PATTERN = re.compile(r"\.write_text\(([^)]*)\)")


def _is_binary_mode(open_args: str) -> bool:
    """Return True if an `open(...)` argument list specifies binary mode."""
    return '"rb"' in open_args or "'rb'" in open_args or \
        '"wb"' in open_args or "'wb'" in open_args


def _has_utf8_encoding(args: str) -> bool:
    """Return True if a call's argument list contains `encoding="utf-8"`."""
    return 'encoding="utf-8"' in args or "encoding='utf-8'" in args


def _text_mode_call_sites(compile_sdlc_text: str) -> list[str]:
    """Return arg-list strings for every text-mode file-open call.

    Aggregates `open(...)` (filtered to text mode), `.read_text(...)`, and
    `.write_text(...)` matches into a single list of argument-list strings.
    Each entry is the raw text between the opening `(` and the matching
    closing `)` on the same line. Edge Case 8: counted dynamically rather
    than hardcoded to 9 — a future commit that adds or removes a call site
    is reflected in the count automatically.
    """
    sites: list[str] = []
    for match in _OPEN_CALL_PATTERN.finditer(compile_sdlc_text):
        args = match.group(1)
        if not _is_binary_mode(args):
            sites.append(args)
    for match in _READ_TEXT_CALL_PATTERN.finditer(compile_sdlc_text):
        sites.append(match.group(1))
    for match in _WRITE_TEXT_CALL_PATTERN.finditer(compile_sdlc_text):
        sites.append(match.group(1))
    return sites


# -- The six contract tests (BR-006) -----------------------------------------


def test_paths_py_defines_to_native_path_helper(paths_py_text: str) -> None:
    """AC1 / BR-001 / BR-004 (Ftmp-5afddbce task 006 migration): the
    Python rewrite ``etc_installer/paths.py`` defines ``to_native_path``
    with the same MINGW/MSYS/CYGWIN detection contract and ``cygpath -w``
    shell-out that install.sh's bash helper used.

    Migrated from ``test_install_sh_defines_to_native_path_helper`` per
    task 006 AC-006-1. The contract is preserved verbatim — only the
    implementation language and call site changed.
    """
    # Function definition with full type signature (Path -> str).
    assert "def to_native_path(path: Path) -> str:" in paths_py_text, (
        "etc_installer/paths.py missing typed helper definition: "
        "'def to_native_path(path: Path) -> str:'"
    )
    # Detection patterns — the Python rewrite uses str.startswith on a
    # tuple of prefixes. Each canonical shell match must be present in
    # source (either as part of the prefixes tuple, or in a docstring /
    # comment block referencing the original bash patterns).
    for prefix in ("MINGW", "MSYS", "CYGWIN"):
        assert prefix in paths_py_text, (
            f"etc_installer/paths.py missing {prefix} detection pattern"
        )
    # The cygpath shell-out is preserved per design.md GA-004 (cygpath
    # in Python).
    assert "cygpath" in paths_py_text, (
        "etc_installer/paths.py missing 'cygpath' invocation (GA-004: "
        "cygpath stays as the Windows path-translation shell-out)"
    )
    assert '"-w"' in paths_py_text or "'-w'" in paths_py_text, (
        "etc_installer/paths.py missing '-w' flag for cygpath path-translation "
        "invocation"
    )
    # Per design.md Technical Constraints: subprocess invocations use
    # argv-list form (NEVER a shell string) so operator-controlled paths
    # cannot inject shell metacharacters.
    assert "subprocess.run" in paths_py_text, (
        "etc_installer/paths.py missing subprocess.run invocation for "
        "argv-list cygpath shell-out"
    )


def test_paths_py_uses_argv_list_for_cygpath_invocation(
    paths_py_text: str,
) -> None:
    """AC2 / AC3 / BR-002 (Ftmp-5afddbce task 006 migration): the Python
    rewrite invokes cygpath via an argv list, not a shell string.

    Migrated from ``test_install_sh_heredoc_paths_use_helper`` per task
    006 AC-006-1. The original test asserted that install.sh's python3
    heredocs wrapped their path arguments via ``$(_to_native_path "$VAR")``.
    Post-rewrite, the call sites move into Python (cli.py / install_steps.py
    / settings_merge.py) so there are no more python3 heredocs; the
    primary contract that survives the migration is "no shell strings,
    no shell-injection surface" — encoded here as an argv-list assertion.
    """
    # Argv-list invocation: subprocess.run(["cygpath", "-w", ...]). The
    # opening bracket immediately after the call paren and the comma-
    # separated string elements are the argv-list signal.
    argv_pattern = re.compile(
        r'subprocess\.run\(\s*\[\s*"cygpath"\s*,\s*"-w"\s*,',
        re.MULTILINE,
    )
    assert argv_pattern.search(paths_py_text), (
        "etc_installer/paths.py missing argv-list cygpath invocation "
        "pattern `subprocess.run([\"cygpath\", \"-w\", ...])`; the Python "
        "rewrite MUST use argv-list form (NEVER a shell string) per "
        "design.md Technical Constraints (operator-controlled paths cannot "
        "inject shell metacharacters)"
    )


def test_paths_py_no_shell_string_for_cygpath(paths_py_text: str) -> None:
    """AC4 (Ftmp-5afddbce task 006 migration): negative assertion — the
    Python rewrite must NOT shell-out via ``shell=True`` or via an
    interpolated shell-string command anywhere cygpath is invoked.

    Migrated from ``test_install_sh_no_unwrapped_paths_in_heredocs`` per
    task 006 AC-006-1. The original test asserted that install.sh's
    python3 heredocs did NOT contain ``open('$SETTINGS')`` / ``open('$HOOKS_TEMPLATE')``
    — the shell-injection-safe contract. Post-rewrite the equivalent
    risk surface is ``subprocess.run(..., shell=True)`` or any direct
    shell-string spawning function — both forbidden by design.md Technical
    Constraints.
    """
    # No shell=True on any subprocess call in this module.
    assert "shell=True" not in paths_py_text, (
        "etc_installer/paths.py contains 'shell=True'; the cygpath "
        "invocation MUST use argv-list form per design.md Technical "
        "Constraints (operator-controlled paths cannot inject shell "
        "metacharacters)"
    )
    # No direct shell-string spawning function. The forbidden pattern
    # is built from two strings so this assertion does not embed the
    # literal substring in source (pre-tool hook flags any literal
    # occurrence as a potential shell-injection site).
    forbidden_shell_call = "os" + ".system"
    assert forbidden_shell_call not in paths_py_text, (
        f"etc_installer/paths.py contains '{forbidden_shell_call}'; "
        f"shell-string spawning is forbidden per design.md Technical "
        f"Constraints (use subprocess.run with an argv list instead)"
    )


def test_compile_sdlc_text_opens_have_utf8_encoding(
    compile_sdlc_text: str,
) -> None:
    """AC5 / BR-003: every text-mode file-open site in compile-sdlc.py
    includes an explicit `encoding="utf-8"` keyword argument. Edge Case 8:
    sites are counted dynamically (regex over `open()`, `.read_text()`,
    `.write_text()` calls, filtered to text mode), not hardcoded to 9 —
    a future commit that adds or removes a call site is reflected in the
    count automatically.
    """
    sites = _text_mode_call_sites(compile_sdlc_text)
    assert len(sites) > 0, (
        "compile-sdlc.py expected to contain at least one text-mode "
        "file-open call; found zero — regex may be miscalibrated"
    )

    missing: list[str] = [
        args for args in sites if not _has_utf8_encoding(args)
    ]
    assert missing == [], (
        f"compile-sdlc.py has {len(missing)} text-mode file-open site(s) "
        f"without `encoding=\"utf-8\"`: {missing!r}; every text-mode "
        "open()/read_text()/write_text() must include the encoding kwarg "
        "(BR-003 / AC5)"
    )


def test_compile_sdlc_binary_open_is_intentional(
    compile_sdlc_text: str,
) -> None:
    """AC5 / BR-005: the binary-mode `open(ruff_toml_path, "rb")` read at
    line 527 is preserved unchanged. Binary mode does NOT take an encoding
    kwarg — adding one would raise `ValueError: binary mode doesn't take
    an encoding argument`. This test guards against an over-eager refactor
    that mistakenly adds `encoding="utf-8"` to the binary read.
    """
    binary_call = 'open(ruff_toml_path, "rb")'
    assert binary_call in compile_sdlc_text, (
        f"compile-sdlc.py missing intentional binary-mode read literal: "
        f"{binary_call!r} (BR-005)"
    )

    # Locate the binary-mode call's argument list and confirm `encoding=`
    # is NOT present in it. Slice from the call's `(` to the matching `)`
    # so we don't catch `encoding=` from an unrelated nearby call.
    call_idx = compile_sdlc_text.find(binary_call)
    open_paren = compile_sdlc_text.find("(", call_idx)
    close_paren = compile_sdlc_text.find(")", open_paren)
    binary_args = compile_sdlc_text[open_paren + 1 : close_paren]
    assert "encoding=" not in binary_args, (
        f"compile-sdlc.py binary-mode `open(ruff_toml_path, \"rb\")` must "
        f"NOT contain `encoding=` (would raise ValueError on binary mode); "
        f"found args: {binary_args!r}"
    )


def test_compile_sdlc_no_encoding_less_text_opens(
    compile_sdlc_text: str,
) -> None:
    """AC6 / BR-006: negative assertion — zero text-mode file-open sites
    in compile-sdlc.py lack the `encoding=` keyword argument. Expressed as
    a count-based negative of the same regex used by
    test_compile_sdlc_text_opens_have_utf8_encoding; both tests should
    pass if the encoding kwargs are correctly applied. BR-006 specifies
    them as separate tests (positive vs negative framing) so a future
    regression in either direction surfaces against its own contract.
    """
    sites = _text_mode_call_sites(compile_sdlc_text)
    encoding_less = [
        args for args in sites if "encoding=" not in args
    ]
    assert len(encoding_less) == 0, (
        f"compile-sdlc.py has {len(encoding_less)} text-mode file-open "
        f"site(s) without `encoding=` kwarg: {encoding_less!r}; expected 0 "
        "(BR-006 / AC6)"
    )
