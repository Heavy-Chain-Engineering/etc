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
import re
import subprocess
import sys
from pathlib import Path

_WINDOWS_SHELL_PREFIXES = ("MINGW", "MSYS", "CYGWIN")

# Git-Bash-style drive-prefixed POSIX path: /c, /c/Users/... etc.
_POSIX_DRIVE_PATTERN = re.compile(r"^/([A-Za-z])(?:/(.*))?$")


def to_native_path(path: Path) -> str:
    """Convert a POSIX-style path to a native path string.

    Two Windows detection branches (audit init 2 — the second was missing,
    so the conversion could never fire under the uv-provisioned NATIVE
    Windows CPython the install.sh bootstrap runs on):

    1. Git Bash / MSYS2 / Cygwin python (``platform.uname().system``
       prefix MINGW/MSYS/CYGWIN): shell out to ``cygpath -w`` via argv
       list — cygpath is guaranteed present in those environments.
       Mirrors install.sh's old ``_to_native_path()``.
    2. Native Windows CPython (``os.name == 'nt'``, uname reports
       "Windows", cygpath NOT guaranteed on PATH): convert drive-prefixed
       POSIX paths (``/c/Users/...`` — the shape a Git-Bash-set ``$HOME``
       produces) textually to ``C:\\Users\\...``. Non-drive paths pass
       through unchanged.

    On macOS, Linux, and WSL, returns ``str(path)`` unchanged.

    Args:
        path: A Path object representing a POSIX-style path.

    Returns:
        The native path string. On Windows: backslash-form. On POSIX
        systems: forward-slash form (identity).
    """
    raw = str(path)
    system = platform.uname().system
    if system.startswith(_WINDOWS_SHELL_PREFIXES):
        completed = subprocess.run(
            ["cygpath", "-w", raw],
            check=True,
            capture_output=True,
            text=True,
        )
        # cygpath emits trailing newline (CRLF on some MSYS variants); strip both.
        return completed.stdout.rstrip("\r\n")

    if os.name == "nt":
        match = _POSIX_DRIVE_PATTERN.match(raw.replace("\\", "/"))
        if match:
            drive = match.group(1).upper()
            rest = match.group(2) or ""
            return f"{drive}:\\" + rest.replace("/", "\\")

    return raw


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
