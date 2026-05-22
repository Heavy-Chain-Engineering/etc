"""paths — POSIX-to-native path conversion, TTY detection, HOME resolution.

Low-layer helper module. Per `standards/architecture/layer-boundaries.md`,
this module is infrastructure-tier and MUST NOT import from cli or
install_steps.

Per design.md `Technical Constraints`: subprocess invocations always use
argv-list form — never a shell string — so operator-controlled paths
cannot inject shell metacharacters.
"""

from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path

_WINDOWS_SHELL_PREFIXES = ("MINGW", "MSYS", "CYGWIN")


def to_native_path(path: Path) -> str:
    """Convert a POSIX-style path to a native path string.

    Under Git Bash / MSYS2 / Cygwin on Windows (detected via
    `platform.uname().system` prefix MINGW/MSYS/CYGWIN), shells out to
    `cygpath -w <path>` via `subprocess.run` with an argv list. On
    macOS, Linux, and WSL (Linux), returns `str(path)` unchanged.

    Mirrors install.sh's `_to_native_path()` (lines 24-39).

    Args:
        path: A Path object representing a POSIX-style path.

    Returns:
        The native path string. On Windows shells: backslash-form. On
        POSIX systems: forward-slash form (identity).
    """
    system = platform.uname().system
    if not system.startswith(_WINDOWS_SHELL_PREFIXES):
        return str(path)

    completed = subprocess.run(
        ["cygpath", "-w", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    # cygpath emits trailing newline (and CRLF on some MSYS variants); strip both.
    return completed.stdout.rstrip("\r\n")


def is_stdout_tty() -> bool:
    """Return True if sys.stdout is a TTY, False otherwise.

    Honest TTY detection per ADR-005: `sys.stdout.isatty()` is the
    canonical check. Returns False conservatively if stdout has no
    `isatty` attribute (captured / non-stream replacements).
    """
    isatty = getattr(sys.stdout, "isatty", None)
    if isatty is None:
        return False
    return bool(isatty())


def resolve_home() -> Path:
    """Resolve the operator's HOME directory.

    Prefers the `HOME` environment variable (POSIX convention); falls
    back to `Path.home()` which consults `USERPROFILE` on Windows.
    """
    home_env = os.environ.get("HOME")
    if home_env:
        return Path(home_env)
    return Path.home()
