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

import sys
from pathlib import Path

from etc_installer import paths

# Resolve the asset path at module import time. The asset lives at
# `<repo_root>/assets/etsy-logo.ascii`; this module lives at
# `<repo_root>/etc_installer/banner.py`, so two parents up.
BANNER_ASSET_PATH: Path = (
    Path(__file__).resolve().parent.parent / "assets" / "etsy-logo.ascii"
)


def print_banner() -> None:
    """Write the raw bytes of the banner asset to sys.stdout.buffer.

    Gated by `paths.is_stdout_tty()`. When stdout is not a TTY (piped,
    redirected, or in CI), the function returns without writing
    anything. When the banner asset is missing, the function returns
    silently — the banner is decorative, not load-bearing (per spec
    Edge Case 4).
    """
    if not paths.is_stdout_tty():
        return
    if not BANNER_ASSET_PATH.is_file():
        return
    banner_bytes = BANNER_ASSET_PATH.read_bytes()
    sys.stdout.buffer.write(banner_bytes)
    sys.stdout.flush()
