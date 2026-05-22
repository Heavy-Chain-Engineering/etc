"""Module entrypoint — invoked by ``python -m etc_installer`` / the bash
bootstrap's ``exec uv run --project "$SCRIPT_DIR" -m etc_installer "$@"``.

Per design.md Module Structure this file is intentionally minimal: a
single import of ``etc_installer.cli`` and a call to ``app()``. All
argv parsing and orchestration lives in ``etc_installer.cli``.
"""

from __future__ import annotations

from etc_installer import cli

cli.app()
