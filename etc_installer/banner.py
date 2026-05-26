"""banner — TTY-gated raw-bytes write of assets/etsy-logo.ascii.

Per ADR-005 (Banner via raw-bytes passthrough): the banner is the
pre-rendered jp2a ANSI-truecolor output of the etc logo. To prevent
re-interpretation by rich.Console, the bytes are written directly to
`sys.stdout.buffer`. TTY-gated via `sys.stdout.isatty()` — non-TTY
invocations (CI, piped, redirected) skip the banner.

Low-layer module. Per `standards/architecture/layer-boundaries.md`,
this module MUST NOT import from cli or install_steps.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

from etc_installer import paths

# Resolve the asset path at module import time. The asset lives at
# `<repo_root>/assets/etsy-logo.ascii`; this module lives at
# `<repo_root>/etc_installer/banner.py`, so two parents up.
BANNER_ASSET_PATH: Path = (
    Path(__file__).resolve().parent.parent / "assets" / "etsy-logo.ascii"
)

# Visible width of the pre-rendered jp2a output (106 cols × 66 lines,
# measured via `re.sub(r'\x1b\[[0-9;]*m', '', line)` ANSI-strip).
# Terminals narrower than this wrap the banner into garbled lines.
_BANNER_VISIBLE_WIDTH: int = 106


def print_banner() -> None:
    """Write the raw bytes of the banner asset to sys.stdout.buffer.

    Gated by three checks in order:
    1. `paths.is_stdout_tty()` — non-TTY (piped, redirected, CI) skips.
    2. Asset file exists — missing asset is silent skip per ADR-005.
    3. Terminal width >= banner visible width (106 cols, strict less-than
       skips). Narrow terminals wrap jp2a output into visual garbage.
    """
    if not paths.is_stdout_tty():
        return
    if not BANNER_ASSET_PATH.is_file():
        return
    if shutil.get_terminal_size(fallback=(80, 24)).columns < _BANNER_VISIBLE_WIDTH:
        return
    banner_bytes = BANNER_ASSET_PATH.read_bytes()
    sys.stdout.buffer.write(banner_bytes)
    sys.stdout.flush()
