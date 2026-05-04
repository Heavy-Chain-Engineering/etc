"""Contract tests for Windows Install + Compile Compatibility (F004 / BR-006).

Covers PRD .etc_sdlc/features/F004-windows-install-compile-compat/spec.md
BR-006, BR-007, AC7, AC8, AC11, AC15 (and Edge Case 8) via grep-based
assertions over:

- install.sh — the `_to_native_path()` bash helper definition and its
  application at both python3 heredoc call sites.
- compile-sdlc.py — explicit `encoding="utf-8"` keyword argument on every
  text-mode file-open site, and the intentionally-preserved binary-mode
  read at line 527.

Precedent: tests/test_user_flow_completeness.py (F001), tests/
test_spec_enforcer_reachability.py (F002), and tests/
test_orphan_surface_dispatch_gate.py (F003). Same autouse session-scoped
compile fixture pattern; same `Path(...).read_text(encoding="utf-8")`
reading idiom; same grep-based assertions over committed source plus
compiled dist/ outputs.

This file's tests assert on source content (install.sh, compile-sdlc.py)
rather than dist/. The autouse compile fixture is retained anyway for
consistency with F001/F002/F003 and so a future test added here that does
need dist/ can rely on it. Per BR-007, the tests run on macOS/Linux
without a Windows VM — no `cygpath`, no `uname`, no Windows-specific
subprocess.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"
COMPILE_SDLC_PY = REPO_ROOT / "compile-sdlc.py"


# -- Session-scoped compile fixture ------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def _compile_sdlc() -> None:
    """Run compile-sdlc.py once at session start so dist/ is fresh.

    The compiler is idempotent — running twice is fine. We do NOT mock the
    compile step. F004's tests assert on source files (install.sh and
    compile-sdlc.py), so dist/ freshness is not load-bearing for THIS
    file's assertions; the fixture is retained for consistency with
    F001/F002/F003 and so a future test added here that does need dist/
    can rely on it.
    """
    subprocess.run(
        ["python3", "compile-sdlc.py", "spec/etc_sdlc.yaml"],
        check=True,
        cwd=str(REPO_ROOT),
        capture_output=True,
    )


# Module-level reference so Pyright sees the autouse fixture as accessed.
# The fixture is invoked by pytest at session start regardless of this line;
# the line exists only to silence Pyright's "is not accessed" hint, which is
# independent of `# pyright: ignore` directives and can only be silenced by
# an actual reference to the symbol.
_ = _compile_sdlc


# -- Module-scoped text fixtures ---------------------------------------------


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    assert INSTALL_SH.exists(), f"missing install script: {INSTALL_SH}"
    return INSTALL_SH.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compile_sdlc_text() -> str:
    assert COMPILE_SDLC_PY.exists(), (
        f"missing compile script: {COMPILE_SDLC_PY}"
    )
    return COMPILE_SDLC_PY.read_text(encoding="utf-8")


# -- Helper: extract python3 heredoc bodies from install.sh ------------------


def _extract_python3_heredoc_bodies(install_sh_text: str) -> list[str]:
    """Return the bodies of every `python3 -c "..."` heredoc in install.sh.

    install.sh embeds two python3 heredocs (the `merge_settings` function
    and the HOOK_EVENTS counter). Each begins with `python3 -c "` and
    ends at the matching closing `"`. The bodies are sliced for negative
    assertions: the unwrapped `open('$SETTINGS')` and `open('$HOOKS_TEMPLATE')`
    patterns must NOT appear inside any heredoc body — only the
    `$(_to_native_path "$VAR")` wrapped form should be present.
    """
    bodies: list[str] = []
    cursor = 0
    opener = 'python3 -c "'
    while True:
        start = install_sh_text.find(opener, cursor)
        if start == -1:
            break
        body_start = start + len(opener)
        # The closing `"` for the heredoc is on its own line in install.sh
        # (after the python source). Find the next bare `"` that isn't part
        # of the python source. install.sh's two heredocs are delimited by
        # `\n"` on a fresh line — search for that sequence to avoid stopping
        # at a `"` inside the python source itself.
        end = install_sh_text.find('\n"', body_start)
        assert end != -1, (
            f"install.sh python3 heredoc starting at offset {start} has no "
            "closing newline-quote terminator"
        )
        bodies.append(install_sh_text[body_start:end])
        cursor = end + 1
    return bodies


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


def test_install_sh_defines_to_native_path_helper(install_sh_text: str) -> None:
    """AC1 / BR-001 / BR-004: install.sh contains the `_to_native_path()`
    bash helper near the top of the file, with the `MINGW*|MSYS*|CYGWIN*`
    detection pattern, the `cygpath -w` invocation, and the
    `command -v cygpath` availability guard (Edge Case 1).
    """
    assert "_to_native_path()" in install_sh_text, (
        "install.sh missing helper definition: '_to_native_path()'"
    )
    assert 'case "$(uname -s)"' in install_sh_text, (
        "install.sh missing uname-based detection literal: "
        "'case \"$(uname -s)\"'"
    )
    # Detection patterns: assert each shell match present (the canonical
    # spec form combines them as MINGW*|MSYS*|CYGWIN* but we check each
    # individually so a future split into separate cases still passes).
    assert "MINGW*" in install_sh_text, (
        "install.sh missing MINGW* detection pattern"
    )
    assert "MSYS*" in install_sh_text, (
        "install.sh missing MSYS* detection pattern"
    )
    assert "CYGWIN*" in install_sh_text, (
        "install.sh missing CYGWIN* detection pattern"
    )
    assert "cygpath -w" in install_sh_text, (
        "install.sh missing 'cygpath -w' path-translation invocation"
    )
    assert "command -v cygpath" in install_sh_text, (
        "install.sh missing 'command -v cygpath' availability check "
        "(Edge Case 1: Git Bash install incomplete)"
    )


def test_install_sh_heredoc_paths_use_helper(install_sh_text: str) -> None:
    """AC2 / AC3 / BR-002: both python3 heredocs in install.sh wrap their
    path arguments with `_to_native_path()`. The merge_settings heredoc
    references `$SETTINGS` (read + write) and `$HOOKS_TEMPLATE` (read);
    the HOOK_EVENTS counter heredoc references `$HOOKS_TEMPLATE` (read).
    """
    settings_wrapped = '$(_to_native_path "$SETTINGS")'
    hooks_template_wrapped = '$(_to_native_path "$HOOKS_TEMPLATE")'

    settings_count = install_sh_text.count(settings_wrapped)
    hooks_template_count = install_sh_text.count(hooks_template_wrapped)

    assert settings_count >= 2, (
        f"install.sh must wrap $SETTINGS with _to_native_path() at every "
        f"heredoc reference; found {settings_count} occurrence(s) of "
        f"{settings_wrapped!r} (expected >= 2: read + write in merge_settings)"
    )
    assert hooks_template_count >= 2, (
        f"install.sh must wrap $HOOKS_TEMPLATE with _to_native_path() at "
        f"every heredoc reference; found {hooks_template_count} occurrence(s) "
        f"of {hooks_template_wrapped!r} (expected >= 2: merge_settings + "
        "HOOK_EVENTS counter)"
    )


def test_install_sh_no_unwrapped_paths_in_heredocs(
    install_sh_text: str,
) -> None:
    """AC4: negative assertion — neither `open('$SETTINGS')` nor
    `open('$HOOKS_TEMPLATE')` may appear in any python3 heredoc body.
    Only the `$(_to_native_path "$VAR")` wrapped form is permitted.
    """
    bodies = _extract_python3_heredoc_bodies(install_sh_text)
    assert len(bodies) >= 2, (
        f"install.sh expected to contain at least 2 python3 heredoc bodies; "
        f"found {len(bodies)}"
    )

    unwrapped_settings = "open('$SETTINGS')"
    unwrapped_hooks_template = "open('$HOOKS_TEMPLATE')"

    for idx, body in enumerate(bodies):
        assert unwrapped_settings not in body, (
            f"install.sh python3 heredoc #{idx} contains unwrapped path "
            f"pattern {unwrapped_settings!r}; must use "
            "$(_to_native_path \"$SETTINGS\") wrapping (BR-002 / AC4)"
        )
        assert unwrapped_hooks_template not in body, (
            f"install.sh python3 heredoc #{idx} contains unwrapped path "
            f"pattern {unwrapped_hooks_template!r}; must use "
            "$(_to_native_path \"$HOOKS_TEMPLATE\") wrapping (BR-002 / AC4)"
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
