"""install_steps — the 11 install-step functions composed by cli.py.

Service-layer module. Each step is a function that takes an
``InstallContext`` and emits exactly one rich.Console status line
prefixed with a check, warn, or cross glyph. Per design.md GA-003 the
11 steps live in a single module (twice-before-abstracting / YAGNI)
rather than 11 separate files.

Per design.md Module Structure this module sits at the Service layer
between cli.py (API) and the Infrastructure tier
(settings_merge / status_line / sandbox_config / profiles / paths).
The Infrastructure modules MUST NOT import from this file.

The eleven steps match install.sh's section numbering:

  1. Directory structure (mkdir -p the TARGET_DIR subtree).
  2. Install agents (.md files).
  3. Install skills (recursive dir copy; rsync if present, else cp -R).
  4. Install standards (recursive subdir discovery).
  5. Install F020 profiles (chmod +x on gate scripts).
  6. Install hooks (chmod +x).
  7. Merge settings.json hook wiring (pure-Python; see settings_merge).
  8. Install SDLC tracker templates.
  9. Install templates (*.tmpl).
 10. Install git hooks + utility scripts (chmod +x).
 11. F020 profile detection (write .etc_sdlc/profiles.lock).

Reference: spec.md BR-011 (install-step parity), BR-012 (no silent
failure modes), AC-011 / AC-012.
"""

from __future__ import annotations

import json
import shutil
import stat
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from rich.console import Console

from etc_installer import profiles, settings_merge
from etc_installer.preflights import OperatorMode

# Documented step count (AC-012). The test asserts this matches the
# number of glyph-prefixed status lines emitted under a full install run.
STEP_COUNT: int = 11


@dataclass(frozen=True, slots=True)
class InstallContext:
    """Composed parameters passed to each step function.

    Attributes:
        target_dir: Resolved install target. Either ``$HOME/.claude``
            (``--scope global``) or ``$PWD/.claude`` (``--scope project``);
            antigravity variants land under ``.gemini/antigravity``.
        dist_dir: Source tree produced by ``compile-sdlc.py``. Read-only.
        client_choice: ``"claude"`` or ``"antigravity"`` (value from
            ``cli.ClientChoice``).
        mode: ``OperatorMode.INTERACTIVE`` (no --client flag) or
            ``OperatorMode.NON_INTERACTIVE`` (--client flag set).
        repo_root: $PWD at install time; used as the F020 detection root
            and the location of ``.etc_sdlc/profiles.lock``.
    """

    target_dir: Path
    dist_dir: Path
    client_choice: str
    mode: OperatorMode
    repo_root: Path


@dataclass(frozen=True, slots=True)
class StepResult:
    """Outcome of one install step.

    Attributes:
        status: ``"ok"`` (success), ``"warn"`` (degraded), or
            ``"error"`` (load-bearing failure — caller exits non-zero).
        message: Human-readable status line. Printed by the caller with
            the matching glyph.
    """

    status: str
    message: str


# Step function signature.
StepFn = Callable[[InstallContext], StepResult]


# ── Step implementations ─────────────────────────────────────────────────


def step_directory_structure(ctx: InstallContext) -> StepResult:
    """Step 1: create the TARGET_DIR subtree (install.sh:276-288)."""
    subdirs = ("agents", "skills", "standards", "hooks", "sdlc", "scripts", "templates")
    for sub in subdirs:
        (ctx.target_dir / sub).mkdir(parents=True, exist_ok=True)
    # Standards categories discovered from dist (avoids hardcoded list drift).
    standards_src = ctx.dist_dir / "standards"
    if standards_src.is_dir():
        for category_dir in sorted(standards_src.iterdir()):
            if category_dir.is_dir():
                (ctx.target_dir / "standards" / category_dir.name).mkdir(
                    parents=True, exist_ok=True
                )
    return StepResult(status="ok", message="Directory structure ready")


def step_install_agents(ctx: InstallContext) -> StepResult:
    """Step 2: copy .md files from dist/agents/ (install.sh:290-299)."""
    src = ctx.dist_dir / "agents"
    dest = ctx.target_dir / "agents"
    count = 0
    if src.is_dir():
        for agent_path in sorted(src.glob("*.md")):
            shutil.copy2(agent_path, dest / agent_path.name)
            count += 1
    return StepResult(status="ok", message=f"Installed {count} agents")


def step_install_skills(ctx: InstallContext) -> StepResult:
    """Step 3: recursively copy skill subdirectories (install.sh:301-323).

    Uses rsync when available (clean tree sync); falls back to ``cp -R``
    via subprocess.run argv list. The rsync/cp shell-out is mandated by
    the test_init_project recursive-copy guard (Ftmp-5afddbce task 006).
    """
    src = ctx.dist_dir / "skills"
    dest = ctx.target_dir / "skills"
    count = 0
    if not src.is_dir():
        return StepResult(status="ok", message="Installed 0 skills")

    dest.mkdir(parents=True, exist_ok=True)
    rsync_path = shutil.which("rsync")
    for skill_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        target_skill = dest / skill_dir.name
        target_skill.mkdir(parents=True, exist_ok=True)
        if rsync_path:
            # rsync semantics: trailing slash on source copies contents.
            subprocess.run(
                [rsync_path, "-a", "--delete", f"{skill_dir}/", f"{target_skill}/"],
                check=True,
                shell=False,
            )
        else:
            # Portable fallback: clear target then cp -R.
            if target_skill.exists():
                shutil.rmtree(target_skill)
            subprocess.run(
                ["cp", "-R", str(skill_dir), str(target_skill)],
                check=True,
                shell=False,
            )
        count += 1
    return StepResult(status="ok", message=f"Installed {count} skills")


def step_install_standards(ctx: InstallContext) -> StepResult:
    """Step 4: install standards (recursive subdir discovery, install.sh:325-340).

    Carries both prose standards (``*.md``) and the declarative standards
    loaded at runtime (``*.yaml``/``*.yml``/``*.toml`` — e.g.
    ``architecture/layer-rubrics.yaml`` read by ``layer_review.py``, and
    ``code/ruff-reference.toml``). A markdown-only copy silently stranded
    the rubric registry, degrading /architect's Phase 2.9 layer-review
    engine to advisory mode in every installed environment.

    The standards/code/profiles/ subtree (F020) is deeper than this
    top-level copy; install_profiles handles it as a sibling step. The
    per-category scan is non-recursive, so profiles/ is untouched here.
    """
    src = ctx.dist_dir / "standards"
    dest = ctx.target_dir / "standards"
    count = 0
    if not src.is_dir():
        return StepResult(status="ok", message="Installed 0 standards")
    for category_dir in sorted(p for p in src.iterdir() if p.is_dir()):
        category_dest = dest / category_dir.name
        category_dest.mkdir(parents=True, exist_ok=True)
        standard_files = sorted(
            f
            for f in category_dir.iterdir()
            if f.is_file() and f.suffix in _STANDARDS_EXTENSIONS
        )
        for standard_file in standard_files:
            shutil.copy2(standard_file, category_dest / standard_file.name)
            count += 1
    return StepResult(status="ok", message=f"Installed {count} standards")


def step_install_profiles(ctx: InstallContext) -> StepResult:
    """Step 5: install F020 profiles subtree (install.sh:342-353).

    Copies dist/standards/code/profiles/ recursively, then chmod +x on
    *.sh gate scripts.
    """
    src = ctx.dist_dir / "standards" / "code" / "profiles"
    if not src.is_dir():
        return StepResult(status="warn", message="No F020 profiles directory in dist")
    dest_parent = ctx.target_dir / "standards" / "code"
    dest_parent.mkdir(parents=True, exist_ok=True)
    dest = dest_parent / "profiles"
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest)
    # chmod +x on gate scripts.
    for sh_file in dest.rglob("*.sh"):
        _chmod_exec(sh_file)
    profile_count = sum(1 for p in dest.iterdir() if p.is_dir())
    return StepResult(
        status="ok", message=f"Installed {profile_count} language profile(s)"
    )


def step_install_hooks(ctx: InstallContext) -> StepResult:
    """Step 6: copy hook .sh files and chmod +x (install.sh:355-365)."""
    src = ctx.dist_dir / "hooks"
    dest = ctx.target_dir / "hooks"
    count = 0
    if not src.is_dir():
        return StepResult(status="ok", message="Installed 0 hooks")
    dest.mkdir(parents=True, exist_ok=True)
    for hook_path in sorted(src.glob("*.sh")):
        target = dest / hook_path.name
        shutil.copy2(hook_path, target)
        _chmod_exec(target)
        count += 1

    # Propagate hooks/helpers/ (.py modules imported by dispatcher hooks).
    # No exec bit — they are imported, not invoked directly.
    helpers_src = src / "helpers"
    if helpers_src.is_dir():
        helpers_dest = dest / "helpers"
        helpers_dest.mkdir(parents=True, exist_ok=True)
        for helper_path in sorted(helpers_src.glob("*")):
            if helper_path.is_file():
                shutil.copy2(helper_path, helpers_dest / helper_path.name)

    return StepResult(status="ok", message=f"Installed {count} hooks (executable)")


def step_merge_settings(ctx: InstallContext) -> StepResult:
    """Step 7: merge hooks section into settings.json (install.sh:367-401).

    Pure-Python — no shell-embedded heredoc (ADR-004 / BR-011). If no
    existing settings.json, copies the template wholesale.
    """
    settings = ctx.target_dir / "settings.json"
    template = ctx.dist_dir / "settings-hooks.json"
    if not template.is_file():
        return StepResult(
            status="error", message="dist/settings-hooks.json missing"
        )

    hooks_dir = ctx.target_dir / "hooks"

    if not settings.is_file():
        # Same placeholder substitution as merge_hooks, applied here for
        # the "no existing settings.json" branch so the operator gets
        # absolute hook paths regardless of install target.
        rendered = settings_merge.substitute_hooks_dir(
            template.read_text(encoding="utf-8"), hooks_dir
        )
        settings.write_text(rendered, encoding="utf-8")
        return StepResult(
            status="ok", message="Created settings.json with hook wiring"
        )

    try:
        settings_merge.merge_hooks(settings, template, hooks_dir)
    except json.JSONDecodeError:
        # Edge Case 5 (spec.md): invalid existing settings.json -> warn,
        # continue. Final exit code is non-zero so the operator notices.
        return StepResult(
            status="error",
            message=f"settings.json at {settings} is not valid JSON - skipping merge",
        )
    return StepResult(
        status="ok",
        message="Merged hook wiring into settings.json (replaced hooks section)",
    )


def step_install_sdlc(ctx: InstallContext) -> StepResult:
    """Step 8: copy SDLC tracker.py + dod-templates.json (install.sh:403-409)."""
    src = ctx.dist_dir / "sdlc"
    dest = ctx.target_dir / "sdlc"
    if not src.is_dir():
        return StepResult(status="warn", message="No dist/sdlc directory")
    dest.mkdir(parents=True, exist_ok=True)
    tracker = src / "tracker.py"
    if tracker.is_file():
        target_tracker = dest / "tracker.py"
        shutil.copy2(tracker, target_tracker)
        _chmod_exec(target_tracker)
    templates_json = src / "dod-templates.json"
    if templates_json.is_file():
        shutil.copy2(templates_json, dest / "dod-templates.json")
    return StepResult(status="ok", message="Installed SDLC tracker templates")


def step_install_templates(ctx: InstallContext) -> StepResult:
    """Step 9: copy *.tmpl files (install.sh:411-420)."""
    src = ctx.dist_dir / "templates"
    dest = ctx.target_dir / "templates"
    count = 0
    if not src.is_dir():
        return StepResult(status="ok", message="Installed 0 templates")
    dest.mkdir(parents=True, exist_ok=True)
    for tmpl in sorted(src.glob("*.tmpl")):
        shutil.copy2(tmpl, dest / tmpl.name)
        count += 1
    return StepResult(status="ok", message=f"Installed {count} templates")


def step_install_git_hooks_and_scripts(ctx: InstallContext) -> StepResult:
    """Step 10: install git hook templates + utility scripts (install.sh:422-440)."""
    git_count = _copy_dir_chmod_exec(
        ctx.dist_dir / "hooks" / "git", ctx.target_dir / "hooks" / "git"
    )
    script_count = _copy_dir_chmod_exec(
        ctx.dist_dir / "scripts", ctx.target_dir / "scripts"
    )
    if git_count == 0 and script_count == 0:
        return StepResult(
            status="warn", message="No git hooks or scripts in dist"
        )
    return StepResult(
        status="ok",
        message=f"Installed {git_count} git hook templates + {script_count} utility scripts",
    )


def step_profile_detection(ctx: InstallContext) -> StepResult:
    """Step 11: F020 profile detection (install.sh:472-492).

    Shells out to the installed detect_profiles.py against ctx.repo_root
    and writes ``.etc_sdlc/profiles.lock``.
    """
    detect_script = ctx.target_dir / "scripts" / "detect_profiles.py"
    if not detect_script.is_file():
        return StepResult(
            status="warn", message="detect_profiles.py not installed; skipped"
        )
    result = profiles.detect_and_write_lock(
        detect_script=detect_script, repo_root=ctx.repo_root
    )
    if not result.ok:
        return StepResult(
            status="warn",
            message=f"Profile detection failed: {result.message}",
        )
    if not result.detected:
        return StepResult(
            status="ok",
            message=f"No language profiles detected in {ctx.repo_root}",
        )
    return StepResult(
        status="ok",
        message=f"Detected profiles: {' '.join(result.detected)}",
    )


# ── Composition ──────────────────────────────────────────────────────────


STEPS: tuple[tuple[str, StepFn], ...] = (
    ("directory_structure", step_directory_structure),
    ("install_agents", step_install_agents),
    ("install_skills", step_install_skills),
    ("install_standards", step_install_standards),
    ("install_profiles", step_install_profiles),
    ("install_hooks", step_install_hooks),
    ("merge_settings", step_merge_settings),
    ("install_sdlc", step_install_sdlc),
    ("install_templates", step_install_templates),
    ("install_git_hooks_and_scripts", step_install_git_hooks_and_scripts),
    ("profile_detection", step_profile_detection),
)

assert len(STEPS) == STEP_COUNT, (
    f"STEPS tuple has {len(STEPS)} entries but STEP_COUNT={STEP_COUNT}"
)


# Standards file extensions carried by step_install_standards. Markdown is
# prose; yaml/yml/toml are declarative standards loaded at runtime (the
# layer-rubrics.yaml registry, ruff-reference.toml). Non-recursive per
# category dir, so the profiles/ subtree (own step) is never swept in.
_STANDARDS_EXTENSIONS: frozenset[str] = frozenset({".md", ".yaml", ".yml", ".toml"})


_GLYPHS: Mapping[str, str] = MappingProxyType(
    {
        "ok": "[green]✓[/green]",
        "warn": "[yellow]⚠[/yellow]",
        "error": "[red]✗[/red]",
    }
)


def run_all(ctx: InstallContext, console: Console) -> int:
    """Execute every step in STEPS, emitting one status line per step.

    Returns:
        Process exit code. ``0`` if every step returned ``status="ok"``
        or ``status="warn"``; ``1`` if any step returned
        ``status="error"``.

    Args:
        ctx: Resolved InstallContext.
        console: rich.Console used for status line emission.
    """
    final_exit = 0
    for _, fn in STEPS:
        result = fn(ctx)
        glyph = _GLYPHS[result.status]
        console.print(f"  {glyph} {result.message}")
        if result.status == "error":
            final_exit = 1
    return final_exit


# ── Helpers ──────────────────────────────────────────────────────────────


def _chmod_exec(path: Path) -> None:
    """Set the executable bit on ``path`` for u+g+o (chmod +x equivalent)."""
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def _copy_dir_chmod_exec(src: Path, dest: Path) -> int:
    """Copy every file in ``src`` to ``dest`` and chmod +x. Returns count.

    Mirrors install.sh:422-440's git-hook + scripts loops. Both
    directories make their contents executable by contract.
    """
    if not src.is_dir():
        return 0
    dest.mkdir(parents=True, exist_ok=True)
    count = 0
    for entry in sorted(src.iterdir()):
        if not entry.is_file():
            continue
        target = dest / entry.name
        shutil.copy2(entry, target)
        _chmod_exec(target)
        count += 1
    return count
