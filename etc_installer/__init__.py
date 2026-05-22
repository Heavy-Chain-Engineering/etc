"""etc_installer — Python installer for the etc SDLC harness.

Replaces the bash install.sh's body. Invoked by the ~30-line install.sh
bootstrap via `uv run --from "$SCRIPT_DIR" -m etc_installer "$@"`.

See `.etc_sdlc/features/active/Ftmp-5afddbce-python-installer-rewrite/` for
the PRD, design, and ADRs.
"""

from __future__ import annotations

__version__ = "0.1.0"
