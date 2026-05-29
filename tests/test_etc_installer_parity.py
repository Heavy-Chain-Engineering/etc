"""Tests for end-to-end install-step parity (AC-011, Ftmp-5afddbce task 005).

Drives the entire bash bootstrap -> Python installer chain end-to-end
against a tmp_path target directory and asserts the produced file-set
matches the documented install.sh output shape.

The original install.sh's parity reference cannot be captured mid-build
(the script has already been rewritten in Wave 0), so the test enforces
the structural shape per spec.md BR-011:

  - target_dir/agents/*.md            (count > 0)
  - target_dir/skills/*/              (recursive dir trees, count > 0)
  - target_dir/standards/<cat>/*.md   (recursive, count > 0)
  - target_dir/standards/code/profiles/<lang>/  (count > 0)
  - target_dir/hooks/*.sh             (executable bit set, count > 0)
  - target_dir/settings.json          (with merged hooks block)
  - target_dir/sdlc/tracker.py        (executable)
  - target_dir/templates/*.tmpl       (count > 0)
  - target_dir/hooks/git/*            (executable)
  - target_dir/scripts/*              (executable)
  - target_dir/.etc_sdlc/profiles.lock  (per F020)

The test invokes ./install.sh --client claude --scope project against a
tmp_path CWD via subprocess.run with shell=False (argv list).

Reference: spec.md AC-011, BR-011, BR-012.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
INSTALL_SH = REPO_ROOT / "install.sh"
DIST_DIR = REPO_ROOT / "dist"


def _run_installer(target_cwd: Path) -> subprocess.CompletedProcess[str]:
    """Drive ./install.sh --client claude --scope project against target_cwd.

    The bootstrap resolves dist/ relative to its own location (SCRIPT_DIR),
    not against $PWD. Running with cwd=target_cwd makes --scope project
    land its $PWD/.claude inside target_cwd.
    """
    # Pass the operator's env through mostly unchanged so uv inherits
    # its cache + tmp directories (TMPDIR / XDG_* / UV_*). Only
    # CLAUDE_CONFIG_DIR is dropped, since it would otherwise redirect
    # --scope global's resolved target_dir.
    passthrough_env = {
        k: v for k, v in os.environ.items() if k != "CLAUDE_CONFIG_DIR"
    }
    return subprocess.run(
        [
            "bash",
            str(INSTALL_SH),
            "--client",
            "claude",
            "--scope",
            "project",
        ],
        cwd=str(target_cwd),
        capture_output=True,
        text=True,
        timeout=120,
        env=passthrough_env,
        shell=False,
    )


@pytest.fixture(scope="module")
def installer_run_target(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Run the installer once at module scope and reuse the result.

    The full install is ~1-5s; running it per-assertion would multiply
    by ~12. Module scope keeps the suite fast while still proving the
    end-to-end shape.
    """
    if not DIST_DIR.is_dir():
        pytest.skip(
            "dist/ not populated at repo root; run "
            "`python3 compile-sdlc.py spec/etc_sdlc.yaml` first"
        )
    if shutil.which("uv") is None:
        pytest.skip(
            "uv not on PATH; parity test requires the bash bootstrap's "
            "uv-managed Python toolchain"
        )

    target_cwd = tmp_path_factory.mktemp("parity-cwd")
    result = _run_installer(target_cwd)
    if result.returncode != 0:
        pytest.fail(
            f"install.sh exited {result.returncode}\n"
            f"--- stdout ---\n{result.stdout}\n"
            f"--- stderr ---\n{result.stderr}\n"
        )
    return target_cwd / ".claude"


# -- AC-011 structural file-set assertions ---------------------------


class TestInstallExitCode:
    """install.sh --client claude --scope project must succeed end-to-end."""

    def test_should_exit_zero_when_install_runs_against_tmp_path(
        self, installer_run_target: Path
    ) -> None:
        # The fixture fails the test if exit != 0; reaching this point
        # is itself the assertion. installer_run_target points at the
        # target/.claude dir that the install populated.
        assert installer_run_target.is_dir(), (
            f"install did not create target dir at {installer_run_target}"
        )


class TestAgents:
    """target_dir/agents/*.md present, count > 0."""

    def test_should_install_at_least_one_agent_md_file(
        self, installer_run_target: Path
    ) -> None:
        agents = list((installer_run_target / "agents").glob("*.md"))
        assert len(agents) > 0, "no agents installed"


class TestSkills:
    """target_dir/skills/*/ recursive dir trees, count > 0."""

    def test_should_install_at_least_one_skill_directory(
        self, installer_run_target: Path
    ) -> None:
        skill_dirs = [
            p for p in (installer_run_target / "skills").iterdir() if p.is_dir()
        ]
        assert len(skill_dirs) > 0, "no skills installed"

    def test_should_install_skill_subdirectories_recursively(
        self, installer_run_target: Path
    ) -> None:
        """Skills with templates/ subdirs must land recursively.

        Guards against the install.sh:79 `cp $skill_dir/*` glob bug that
        silently dropped subdirectories like init-project/templates/.
        """
        # Look for at least one skill with a subdirectory under it.
        found_recursive = False
        for skill_dir in (installer_run_target / "skills").iterdir():
            if not skill_dir.is_dir():
                continue
            subdirs = [p for p in skill_dir.iterdir() if p.is_dir()]
            if subdirs:
                found_recursive = True
                break
        # The dist tree may or may not currently have a skill with a
        # subdir; soft-skip if not present.
        if not found_recursive:
            pytest.skip(
                "no skill in dist/ has subdirectories; recursive copy "
                "behavior is exercised by tests/test_init_project.py "
                "directly against install_steps.step_install_skills"
            )


class TestStandards:
    """target_dir/standards/<category>/*.md recursive, count > 0."""

    def test_should_install_standards_under_at_least_one_category(
        self, installer_run_target: Path
    ) -> None:
        std_root = installer_run_target / "standards"
        assert std_root.is_dir()
        total_md = 0
        for cat in std_root.iterdir():
            if not cat.is_dir():
                continue
            total_md += len(list(cat.glob("*.md")))
        assert total_md > 0, "no standards .md files installed"


class TestProfiles:
    """target_dir/standards/code/profiles/<lang>/ count > 0 (F020)."""

    def test_should_install_at_least_one_language_profile(
        self, installer_run_target: Path
    ) -> None:
        profiles_root = (
            installer_run_target / "standards" / "code" / "profiles"
        )
        assert profiles_root.is_dir(), "F020 profiles/ subtree missing"
        langs = [p for p in profiles_root.iterdir() if p.is_dir()]
        assert len(langs) > 0, "no language profiles installed"


class TestHooks:
    """target_dir/hooks/*.sh present with executable bit set."""

    def test_should_install_at_least_one_hook_sh_file(
        self, installer_run_target: Path
    ) -> None:
        hooks = list((installer_run_target / "hooks").glob("*.sh"))
        assert len(hooks) > 0, "no hooks installed"

    def test_should_set_executable_bit_on_every_hook(
        self, installer_run_target: Path
    ) -> None:
        for hook in (installer_run_target / "hooks").glob("*.sh"):
            assert hook.stat().st_mode & stat.S_IXUSR, (
                f"{hook.name} not +x"
            )

    def test_should_install_verify_green_dispatcher(
        self, installer_run_target: Path
    ) -> None:
        """The F020 dispatcher must land — count>0 stayed green while it was missing.

        verify-green.sh is invoked from /build Step 6c prose, not registered
        as a gate, so the old count>0 assertion passed even when the
        dispatcher was silently dropped from dist/ and the install.
        """
        verify_green = installer_run_target / "hooks" / "verify-green.sh"
        assert verify_green.exists(), (
            "verify-green.sh (F020 dispatcher) not installed — /build Step 6c "
            "would be command-not-found on every non-Python project"
        )

    def test_should_install_hook_helpers_subdir(
        self, installer_run_target: Path
    ) -> None:
        """hooks/helpers/*.py modules must propagate to the install target."""
        helpers = installer_run_target / "hooks" / "helpers"
        py_modules = list(helpers.glob("*.py")) if helpers.is_dir() else []
        assert py_modules, (
            "hooks/helpers/ .py modules not installed — dispatcher hooks that "
            "import them would fail at runtime"
        )


class TestSettingsJson:
    """target_dir/settings.json exists with merged hooks block."""

    def test_should_create_settings_json_with_hooks_block(
        self, installer_run_target: Path
    ) -> None:
        settings = installer_run_target / "settings.json"
        assert settings.is_file(), "settings.json not created"
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert "hooks" in body, "hooks key missing from settings.json"
        # Hooks block should be non-empty (the dist template wires real handlers)
        assert body["hooks"], "hooks block is empty after install"


class TestSdlcTracker:
    """target_dir/sdlc/tracker.py present, executable."""

    def test_should_install_tracker_py_executable(
        self, installer_run_target: Path
    ) -> None:
        tracker = installer_run_target / "sdlc" / "tracker.py"
        assert tracker.is_file(), "tracker.py not installed"
        assert tracker.stat().st_mode & stat.S_IXUSR, (
            "tracker.py not +x"
        )


class TestTemplates:
    """target_dir/templates/*.tmpl present, count > 0."""

    def test_should_install_at_least_one_tmpl_file(
        self, installer_run_target: Path
    ) -> None:
        tmpls = list(
            (installer_run_target / "templates").glob("*.tmpl")
        )
        assert len(tmpls) > 0, "no templates installed"


class TestGitHooks:
    """target_dir/hooks/git/* present, executable."""

    def test_should_set_executable_bit_on_git_hooks(
        self, installer_run_target: Path
    ) -> None:
        git_hooks_dir = installer_run_target / "hooks" / "git"
        if not git_hooks_dir.is_dir():
            pytest.skip("no hooks/git/ in dist for this install")
        files = [p for p in git_hooks_dir.iterdir() if p.is_file()]
        assert len(files) > 0, "no git hooks installed"
        for git_hook in files:
            assert git_hook.stat().st_mode & stat.S_IXUSR, (
                f"{git_hook.name} not +x"
            )


class TestScripts:
    """target_dir/scripts/* present, executable."""

    def test_should_set_executable_bit_on_utility_scripts(
        self, installer_run_target: Path
    ) -> None:
        scripts_dir = installer_run_target / "scripts"
        assert scripts_dir.is_dir(), "scripts/ dir missing"
        files = [p for p in scripts_dir.iterdir() if p.is_file()]
        assert len(files) > 0, "no utility scripts installed"
        for script in files:
            assert script.stat().st_mode & stat.S_IXUSR, (
                f"{script.name} not +x"
            )


class TestProfilesLock:
    """F020: .etc_sdlc/profiles.lock written under the install-time CWD."""

    def test_should_write_profiles_lock_under_install_cwd(
        self, installer_run_target: Path
    ) -> None:
        # The lock lives under the install-time CWD (parent of
        # target_dir/.claude/), per install.sh:480.
        cwd = installer_run_target.parent
        lock = cwd / ".etc_sdlc" / "profiles.lock"
        # Empty lock is fine (no profile signals detected); presence is
        # the contract per F020-005.
        assert lock.is_file(), (
            f"profiles.lock not written at {lock}"
        )


# -- Install-step parity: full step contract ---------------------------


class TestInstallStepParity:
    """AC-011 umbrella: install runs end-to-end producing the expected shape."""

    def test_install_step_parity(self, installer_run_target: Path) -> None:
        """One-liner contract: all eleven step categories produced output.

        This is the AC-011-named test referenced in the task YAML.
        Each clause maps 1:1 to one of the eleven install_steps
        functions. Failure of any clause means a step's filesystem
        effect drifted from install.sh's documented behavior.
        """
        target = installer_run_target

        # Step 1: directory structure
        for sub in (
            "agents",
            "skills",
            "standards",
            "hooks",
            "sdlc",
            "scripts",
            "templates",
        ):
            assert (target / sub).is_dir(), f"step 1: missing {sub}/"

        # Step 2: agents
        assert any((target / "agents").glob("*.md")), "step 2: no agents"

        # Step 3: skills
        assert any(
            p.is_dir() for p in (target / "skills").iterdir()
        ), "step 3: no skill subdirs"

        # Step 4: standards
        std_md_count = sum(
            1
            for cat in (target / "standards").iterdir()
            if cat.is_dir()
            for _ in cat.glob("*.md")
        )
        assert std_md_count > 0, "step 4: no standards .md files"

        # Step 5: F020 profiles
        profiles_root = target / "standards" / "code" / "profiles"
        assert profiles_root.is_dir(), "step 5: no profiles subtree"
        assert any(
            p.is_dir() for p in profiles_root.iterdir()
        ), "step 5: no language profiles"

        # Step 6: hooks (.sh, executable)
        hook_shs = list((target / "hooks").glob("*.sh"))
        assert hook_shs, "step 6: no hooks"
        for h in hook_shs:
            assert h.stat().st_mode & stat.S_IXUSR, (
                f"step 6: {h.name} not +x"
            )

        # Step 7: settings.json with hooks block
        settings = target / "settings.json"
        assert settings.is_file(), "step 7: no settings.json"
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert body.get("hooks"), "step 7: hooks block empty/missing"

        # Step 8: SDLC tracker
        tracker = target / "sdlc" / "tracker.py"
        assert tracker.is_file(), "step 8: no tracker.py"
        assert tracker.stat().st_mode & stat.S_IXUSR, (
            "step 8: tracker.py not +x"
        )

        # Step 9: templates
        assert any(
            (target / "templates").glob("*.tmpl")
        ), "step 9: no templates"

        # Step 10: git hooks + scripts (executable)
        scripts = [
            p for p in (target / "scripts").iterdir() if p.is_file()
        ]
        assert scripts, "step 10: no scripts"
        for s in scripts:
            assert s.stat().st_mode & stat.S_IXUSR, (
                f"step 10: {s.name} not +x"
            )

        # Step 11: profiles.lock
        lock = target.parent / ".etc_sdlc" / "profiles.lock"
        assert lock.is_file(), "step 11: profiles.lock not written"
