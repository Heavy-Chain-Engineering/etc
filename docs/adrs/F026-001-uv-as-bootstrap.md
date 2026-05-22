# ADR-001: uv as bootstrap technology

**Date:** 2026-05-22
**Status:** Accepted

**Context:** The installer needs to run on a fresh machine where Python may not be installed, may be the Microsoft Store python3 stub on Windows, or may be an incompatible version. Past install incidents (memory/feedback-windows-install-portability.md) trace directly to assumed-present-Python prerequisites. The installer must resolve its own Python toolchain before doing any install work — the bootstrap chicken-and-egg.

Three candidates were considered:
- (a) uv (Astral) — single static binary, official curl-pipe-shell install for Unix, PowerShell installer for Windows, manages its own Python.
- (b) System python3 + venv — assume `python3 -m venv .venv && .venv/bin/pip install -e .` works. Falls into the Microsoft Store python3 stub trap on Windows.
- (c) Self-contained binary (pyinstaller / shiv / nuitka) — bundle the installer as a single .bin/.exe; no Python prerequisite, no uv prerequisite.

**Decision:** Use uv. The bash bootstrap detects uv on PATH; if absent, runs `curl -LsSf https://astral.sh/uv/install.sh | sh` (Unix) or the official PowerShell equivalent (Windows under Git Bash). After uv is present, hand off via `uv run --from "$SCRIPT_DIR" -m etc_installer "$@"`.

Pin floor: uv >= 0.4 (March 2025 — when `--from` flag stabilized).

**Consequences:**
- *Easier*: Cross-platform Python toolchain management is uv's job, not ours. uv handles Python version selection, venv lifecycle, dependency resolution. Operator never installs Python directly. Bypasses the Microsoft Store python3 stub trap by design.
- *Harder*: Supply-chain trust extends to Astral's distribution (mitigated by HTTPS + same trust posture as existing brew/npm install commands the current install.sh already offers). One new external dependency for first-time installs (network access required for the curl).
- *Deferred*: PyInstaller-style single-binary distribution (Tier 3); package-manager submissions (Homebrew formula, apt repo).
- *Cannot defer*: bash bootstrap must handle uv-install failure (network down, curl missing) with a clear error pointing at Astral docs — failing silently here would erase the entire UX win.

**Related ADRs:** ADR-002 (typer + rich), ADR-003 (etc_installer location).
