"""cli — typer app, top-level argv parsing + install orchestration.

API-layer module. Owns the argv surface (``--client``, ``--scope``,
``--help``, plus operational flags ``--dist-dir``, ``--target-dir``,
``--dry-run``), the missing-dist preflight (AC-013), and composition of
the eleven install steps from ``etc_installer.install_steps``.

Per design.md Module Structure, this module sits at the API layer.
Direct imports from Infrastructure modules (settings_merge, status_line,
sandbox_config, profiles, paths) are routed through
``etc_installer.install_steps`` — cli.py does NOT touch the filesystem
directly. The exception is the missing-dist preflight, which must run
before any step composition.

Reference: spec.md BR-004 (CLI argv compatibility), BR-012 (no silent
failures), AC-004 / AC-011 / AC-012 / AC-013.
"""

from __future__ import annotations

import enum
import os
import sys
from pathlib import Path

import typer
from rich.console import Console

from etc_installer import banner, install_steps, paths
from etc_installer.preflights import OperatorMode

# ── Public app surface ───────────────────────────────────────────────────

# typer pretty-traceback adds rich-rendered exception decoration that
# breaks the AC-013 "one-line error mentioning compile-sdlc.py" contract.
# Disabling pretty exceptions keeps the error path predictable.
app = typer.Typer(
    add_completion=False,
    pretty_exceptions_enable=False,
    no_args_is_help=False,
    help=(
        "etc — Engineering Team, Codified — installer\n\n"
        "Usage: install.sh [--client {claude|antigravity|codex}] "
        "[--scope {global|project}] [--help]"
    ),
)

_console = Console()
_error_console = Console(stderr=True)


# ── argv enums (BR-004 — verbatim --client / --scope surface) ─────────────


class ClientChoice(str, enum.Enum):
    """--client values. Members named to match the bash bootstrap's argv."""

    CLAUDE = "claude"
    ANTIGRAVITY = "antigravity"
    CODEX = "codex"


class ScopeChoice(str, enum.Enum):
    """--scope values. ``global`` lands in $HOME/.claude (or $CLAUDE_CONFIG_DIR);
    ``project`` lands in $PWD/.claude."""

    GLOBAL = "global"
    PROJECT = "project"
    USER = "user"


# ── helpers ──────────────────────────────────────────────────────────────


def _default_dist_dir() -> Path:
    """Resolve the default dist/ directory.

    The bash bootstrap invokes ``uv run --project "$SCRIPT_DIR" -m
    etc_installer "$@"``; ``$SCRIPT_DIR`` is the repo root, so dist/
    lives one parent above this module.
    """
    return Path(__file__).resolve().parent.parent / "dist"


def _resolve_target_dir(client: ClientChoice, scope: ScopeChoice) -> Path:
    """Resolve $TARGET_DIR from (client, scope).

    Mirrors install.sh:152-169. Honors $CLAUDE_CONFIG_DIR for Claude
    global scope.
    """
    home = paths.resolve_home()
    if client is ClientChoice.CODEX:
        if scope is ScopeChoice.PROJECT:
            if project_dir := os.environ.get("ETC_PROJECT_DIR"):
                return Path(project_dir)
            return Path.cwd()
        raise ValueError(
            "Codex user/global install is not enabled. Use --scope project "
            "for project-local install."
        )
    if client is ClientChoice.CLAUDE:
        if scope is ScopeChoice.PROJECT:
            return Path.cwd() / ".claude"
        return Path(os.environ.get("CLAUDE_CONFIG_DIR", str(home / ".claude")))
    # antigravity / Gemini
    if scope is ScopeChoice.PROJECT:
        return Path.cwd() / ".gemini" / "antigravity"
    return home / ".gemini" / "antigravity"


def _resolve_dist_dir(client: ClientChoice | None, dist_dir: Path | None) -> Path:
    """Resolve the dist source for the selected client."""
    if dist_dir is not None:
        return dist_dir
    default_dist = _default_dist_dir()
    if client is ClientChoice.CODEX:
        return default_dist / "codex"
    return default_dist


def _preflight_dist(dist_dir: Path, client: ClientChoice | None = None) -> None:
    """Verify dist/ exists; print and exit 1 if not (AC-013, BR-012).

    The error message is a single line mentioning ``compile-sdlc.py`` so
    the operator knows what to run to populate dist/.
    """
    if client is ClientChoice.CODEX:
        if (
            dist_dir.is_dir()
            and (dist_dir / "AGENTS.md").is_file()
            and (dist_dir / ".codex" / "hooks.json").is_file()
        ):
            return
        _error_console.print(
            f"✗ Codex dist/ not found at {dist_dir} — run "
            "`python3 compile-sdlc.py spec/etc_sdlc.yaml --client codex` first"
        )
        raise typer.Exit(code=1)

    if dist_dir.is_dir() and (dist_dir / "settings-hooks.json").is_file():
        return
    _error_console.print(
        f"✗ dist/ not found at {dist_dir} — run "
        "`python3 compile-sdlc.py spec/etc_sdlc.yaml` first"
    )
    raise typer.Exit(code=1)


def _select_client_interactive() -> ClientChoice:
    """Prompt for client when --client is not passed (install.sh:142-148)."""
    _console.print("[bold]Select your AI coding assistant:[/bold]")
    _console.print("  1) Claude Code")
    _console.print("  2) Antigravity / Gemini")
    choice = typer.prompt("Enter choice [1 or 2]", default="1")
    if choice.strip() == "1":
        return ClientChoice.CLAUDE
    if choice.strip() == "2":
        return ClientChoice.ANTIGRAVITY
    _error_console.print("✗ invalid choice — please run again and select 1 or 2")
    raise typer.Exit(code=1)


def _print_codex_dry_run_plan(dist_dir: Path, project_dir: Path) -> None:
    """Print the project-local Codex install plan without writing files."""
    _console.print("[bold]Dry run: Codex project install plan[/bold]")
    _console.print()
    _console.print(f"  Source:         {dist_dir}", soft_wrap=True)
    _console.print(f"  Target project: {project_dir}", soft_wrap=True)
    _console.print("  Write scope:    selected project only")
    _console.print()
    _console.print("  Would create/update:")
    _console.print(f"    instructions/config/hooks: {project_dir / '.codex'}", soft_wrap=True)
    _console.print(
        f"    repo skills:               {project_dir / '.agents' / 'skills'}",
        soft_wrap=True,
    )
    _console.print(
        f"    repo standards path:       {project_dir / 'standards'}",
        soft_wrap=True,
    )
    _console.print(
        f"    project agents:            {project_dir / '.codex' / 'agents'}",
        soft_wrap=True,
    )
    _console.print(
        f"    schemas/proof data:        {project_dir / '.codex' / 'schemas'}",
        soft_wrap=True,
    )
    _console.print(
        f"    expected output snapshot:  {project_dir / '.codex' / 'expected'}",
        soft_wrap=True,
    )
    _console.print(
        f"    source snapshot:           {project_dir / '.codex' / 'source'}",
        soft_wrap=True,
    )
    _console.print(
        f"    gate classifications:      {project_dir / 'gate-classification.json'}",
        soft_wrap=True,
    )
    _console.print()
    _console.print("  No files were written.")
    _console.print("  No user-global Codex or Claude config will be modified.")


# ── main entry point (typer callback — root command) ─────────────────────


@app.callback(invoke_without_command=True)
def main(  # noqa: PLR0913 -- typer surface; the flags ARE the contract
    client: ClientChoice | None = typer.Option(
        None,
        "--client",
        help="Skip interactive client prompt. claude|antigravity|codex",
        case_sensitive=False,
    ),
    scope: ScopeChoice = typer.Option(
        ScopeChoice.GLOBAL,
        "--scope",
        help="Install scope. global|project. Defaults to 'global'.",
        case_sensitive=False,
    ),
    dist_dir: Path = typer.Option(
        None,
        "--dist-dir",
        help="Override the dist/ source directory (default: repo-root/dist).",
    ),
    target_dir: Path = typer.Option(
        None,
        "--target-dir",
        help="Override the install target directory (default: resolved from --client + --scope).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Short-circuit before any file writes; argv + preflight only.",
    ),
) -> None:
    """Install the etc SDLC harness.

    Composes the eleven steps in ``etc_installer.install_steps`` against
    the resolved (client, scope, target_dir) triple. Emits exactly one
    rich.Console status line per step (AC-012). Exits non-zero on
    load-bearing failures.
    """
    # Resolve dist_dir before banner so the missing-dist preflight runs
    # ahead of any decorative output. AC-013 contract.
    resolved_dist = _resolve_dist_dir(client, dist_dir)
    _preflight_dist(resolved_dist, client)

    # Banner is decorative; TTY-gated; safe to emit after preflight passes.
    banner.print_banner()
    _console.print()
    _console.print("[bold]etc — Engineering Team, Codified[/bold]")
    _console.print("Installing coding harness...")
    _console.print()

    # Resolve client (prompt if not passed).
    resolved_client = client if client is not None else _select_client_interactive()

    # Mode: --client flag set → NON_INTERACTIVE; unset → INTERACTIVE.
    mode = (
        OperatorMode.NON_INTERACTIVE if client is not None else OperatorMode.INTERACTIVE
    )

    # Target dir: explicit override or computed.
    try:
        if resolved_client is ClientChoice.CODEX and scope is not ScopeChoice.PROJECT:
            raise ValueError(
                "Codex user/global install is not enabled. Use --scope project "
                "for project-local install."
            )
        resolved_target = (
            target_dir
            if target_dir is not None
            else _resolve_target_dir(resolved_client, scope)
        )
    except ValueError as exc:
        _error_console.print(f"✗ {exc}")
        raise typer.Exit(code=1) from exc

    _console.print(f"  ✓ Scope: {scope.value} — installing into {resolved_target}")

    if dry_run:
        if resolved_client is ClientChoice.CODEX:
            _print_codex_dry_run_plan(resolved_dist, resolved_target)
            return
        _console.print("  ✓ Dry-run: skipping all file writes")
        return

    # Compose the install steps.
    context = install_steps.InstallContext(
        target_dir=resolved_target,
        dist_dir=resolved_dist,
        client_choice=resolved_client.value,
        mode=mode,
        repo_root=Path.cwd(),
    )
    exit_code = install_steps.run_all(context, _console)
    if exit_code != 0:
        raise typer.Exit(code=exit_code)


def _entrypoint() -> None:
    """Module entrypoint — invoked by ``python -m etc_installer``."""
    try:
        app()
    except KeyboardInterrupt:
        # Edge Case 14: Ctrl+C at any prompt → exit 130 (SIGINT).
        _error_console.print("\n✗ install cancelled by operator")
        sys.exit(130)
