#!/usr/bin/env bash
# etc — Engineering Team, Codified — installer bootstrap.
#
# This script is the bash bootstrap layer (Ftmp-5afddbce). It resolves the
# Python toolchain via uv (Astral) and hands off to the etc_installer
# Python module. All install logic lives in Python; see ADR-001
# (docs/adrs/Ftmp-5afddbce-001-uv-as-bootstrap.md) and the design at
# .etc_sdlc/features/active/Ftmp-5afddbce-python-installer-rewrite/design.md.
#
# Argv surface (contract-pinned; preserved byte-for-byte for tests):
#   --client {claude|antigravity}
#   --scope  {global|project}
#   --help, -h

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Minimal usage block. Once etc_installer ships (tasks 002-005), the
# typer-rendered --help becomes the operator-facing surface; this block
# stays as the bootstrap's own fallback for the case where the hand-off
# itself fails (no uv, no network). The four substrings --client,
# --scope, claude|antigravity, global|project are AC-004-pinned.
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'USAGE'
etc — Engineering Team, Codified — installer

Usage: ./install.sh [--client {claude|antigravity}] [--scope {global|project}] [--help]

Options:
  --client {claude|antigravity}   Skip interactive client prompt.
  --scope  {global|project}       Install scope. Defaults to 'global'.
  --help, -h                      Show this help and exit.
USAGE
    exit 0
fi

# Detect uv on PATH; if absent, install via the official Astral curl-pipe
# installer. AC-002: no interactive prompt; on failure, exit non-zero with
# a one-line error pointing at the Astral docs URL.
if ! command -v uv >/dev/null 2>&1; then
    echo "etc: uv not found on PATH — installing via https://astral.sh/uv/install.sh" >&2
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
        echo "etc: uv install failed — see https://astral.sh/uv/install.sh for manual install instructions" >&2
        exit 1
    fi
    # uv's installer drops the binary under ~/.local/bin or ~/.cargo/bin;
    # both are added to PATH by the installer's shell hook but not in the
    # current process. Source the standard locations so the exec below
    # finds uv.
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"
fi

# Hand off to the Python module via process replacement so exit codes
# propagate naturally. `--project "$SCRIPT_DIR"` points uv at the
# inline-in-repo etc_installer package (per ADR-003 — etc_installer
# lives at the repo root); tasks 002-005 ship the package itself.
#
# NOTE (design vs uv CLI): design.md and ADR-001 specify `--from
# "$SCRIPT_DIR"`, but `--from` is a `uv tool run` (uvx) flag; the
# `uv run` equivalent for "use the project at this path" is
# `--project`. Documented as Ftmp-5afddbce design-doc discrepancy;
# escalation to architect noted in task 001 completion report.
#
# PYTHONPATH NOTE (task 005, 2026-05-22): etc_installer ships inline at
# the repo root but is NOT a packaged distribution — pyproject.toml
# does not declare a [tool.hatch.build] target, and the flat-layout
# has multiple top-level dirs that defeat setuptools auto-discovery.
# Setting PYTHONPATH="$SCRIPT_DIR" makes `python -m etc_installer`
# resolve via the source tree directly, mirroring pytest's
# `pythonpath = ["."]` in pyproject.toml. This is the smallest change
# that makes the bootstrap → Python hand-off work end-to-end.
export PYTHONPATH="$SCRIPT_DIR${PYTHONPATH:+:$PYTHONPATH}"
exec uv run --project "$SCRIPT_DIR" -m etc_installer "$@"
