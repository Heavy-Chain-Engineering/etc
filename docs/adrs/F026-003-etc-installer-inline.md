# ADR-003: etc_installer lives inline in repo, not on PyPI

**Date:** 2026-05-22
**Status:** Accepted

**Context:** The Python installer module needs a distribution shape. Three candidates:

- (a) Inline in repo at `etc_installer/`; bootstrap runs `uv run --from "$SCRIPT_DIR" -m etc_installer` against the cloned repo.
- (b) Embedded in dist/ output (compile-sdlc.py copies etc_installer/ source into dist/etc_installer/).
- (c) Published to PyPI as `etc-installer`; bootstrap runs `uv tool install etc-installer && etc-installer ...`.

**Decision:** Inline in repo (option a). The package source lives at `etc_installer/` in the etc repo root. `pyproject.toml` declares it as a package with typer/rich runtime dependencies.

**Consequences:**
- *Easier*: Zero published-package infrastructure (no PyPI account, no release automation, no version-bump discipline). Matches the current `./install.sh` workflow where the operator clones the repo and runs the installer locally. No duplication of source under dist/.
- *Harder*: Operators who don't clone the repo can't install. (The current install.sh already requires a cloned repo, so this is no regression.)
- *Deferred*: PyPI publication (Tier 2 distribution) until marketing+billing+licensing infrastructure is ready, per `memory/project-plugin-packaging-strategy.md`. Single-binary distribution via PyInstaller (Tier 3).
- *Cannot defer*: The bootstrap's `uv run --from "$SCRIPT_DIR"` requires the etc_installer source at a known relative path. If the source moves, bootstrap moves.

**Related ADRs:** ADR-001 (uv bootstrap — the inline-source distribution depends on uv's `--from <path>` flag); ADR-002 (typer + rich runtime deps).
