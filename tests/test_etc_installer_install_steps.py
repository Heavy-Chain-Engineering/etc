"""Tests for etc_installer.install_steps -- the 11 install-step functions.

Covers AC-011 (parity step-by-step) and AC-012 (status-line discipline)
from Ftmp-5afddbce task 005:

- ``STEP_COUNT`` is exactly 11 (documented in AC-012; matches
  install.sh's 11 sections after consolidation).
- ``STEPS`` is a tuple of 11 ``(name, fn)`` entries with matching count.
- ``InstallContext`` is a frozen dataclass with the fields the step
  functions read from.
- Each step function returns a ``StepResult`` with status in
  ``{"ok", "warn", "error"}``.
- ``run_all`` emits exactly STEP_COUNT status lines to the rich.Console
  (AC-012 -- one line per step, each prefixed with one of three glyphs).
- Each step's filesystem effects match install.sh's section: directories
  created, files copied, executable bit set where install.sh sets it.

Reference: spec.md BR-011 (install-step parity), BR-012 (no silent
failures).
"""

from __future__ import annotations

import json
import stat
import sys
from io import StringIO
from pathlib import Path
from unittest import mock

import pytest
from rich.console import Console

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from etc_installer import install_steps  # noqa: E402
from etc_installer.preflights import OperatorMode  # noqa: E402

# -- Test fixture: a minimal dist/ tree mirroring compile-sdlc.py output --


def _seed_minimal_dist(dist: Path) -> None:
    """Create a minimal dist/ tree exercising every step's source paths."""
    # agents/
    agents = dist / "agents"
    agents.mkdir(parents=True)
    (agents / "backend-developer.md").write_text("# backend\n", encoding="utf-8")
    (agents / "code-reviewer.md").write_text("# review\n", encoding="utf-8")

    # skills/ with a templates subdir (the recursive-copy bug guard).
    skill = dist / "skills" / "implement"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("# implement\n", encoding="utf-8")
    (skill / "templates").mkdir()
    (skill / "templates" / "ticket.md.template").write_text(
        "template\n", encoding="utf-8"
    )

    # standards/<category>/*.md
    for category in ("code", "process"):
        cat = dist / "standards" / category
        cat.mkdir(parents=True)
        (cat / f"{category}-rule.md").write_text(
            f"# {category}\n", encoding="utf-8"
        )

    # Non-markdown standards that are loaded at RUNTIME. The
    # layered-architecture-review feature (fc83132) added a .yaml rubric
    # registry that layer_review.py reads via REPO_ROOT-relative path; a
    # markdown-only install silently strands it. ruff-reference.toml is the
    # second orphan. Both must land in the installed standards tree.
    arch = dist / "standards" / "architecture"
    arch.mkdir(parents=True)
    (arch / "layer-boundaries.md").write_text("# layers\n", encoding="utf-8")
    (arch / "layer-rubrics.yaml").write_text(
        "layers: []\n", encoding="utf-8"
    )
    (dist / "standards" / "code" / "ruff-reference.toml").write_text(
        "[tool.ruff]\n", encoding="utf-8"
    )

    # standards/code/profiles/<lang>/
    profiles_dir = dist / "standards" / "code" / "profiles" / "python"
    profiles_dir.mkdir(parents=True)
    (profiles_dir / "detection.yaml").write_text(
        "name: python\n", encoding="utf-8"
    )
    gate_script = profiles_dir / "gate.sh"
    gate_script.write_text(
        "#!/usr/bin/env bash\necho gate\n", encoding="utf-8"
    )

    # hooks/*.sh
    hooks = dist / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "check-test-exists.sh").write_text(
        "#!/usr/bin/env bash\n", encoding="utf-8"
    )
    (hooks / "check-completion-discipline.sh").write_text(
        "#!/usr/bin/env bash\n", encoding="utf-8"
    )

    # hooks/helpers/* -- .py modules invoked by dispatcher hooks
    helpers = dist / "hooks" / "helpers"
    helpers.mkdir(parents=True)
    (helpers / "check_mutable_globals.py").write_text(
        "# mutable globals helper\n", encoding="utf-8"
    )

    # hooks/git/*
    git_hooks = dist / "hooks" / "git"
    git_hooks.mkdir(parents=True)
    (git_hooks / "post-commit").write_text(
        "#!/usr/bin/env bash\n", encoding="utf-8"
    )

    # scripts/* -- include detect_profiles.py so step 11 has a target
    scripts = dist / "scripts"
    scripts.mkdir(parents=True)
    detect = scripts / "detect_profiles.py"
    detect.write_text(
        "#!/usr/bin/env python3\nimport sys\nsys.exit(0)\n",
        encoding="utf-8",
    )
    (scripts / "feature_id.py").write_text(
        "#!/usr/bin/env python3\n", encoding="utf-8"
    )

    # sdlc/tracker.py + dod-templates.json
    sdlc = dist / "sdlc"
    sdlc.mkdir(parents=True)
    (sdlc / "tracker.py").write_text(
        "#!/usr/bin/env python3\n", encoding="utf-8"
    )
    (sdlc / "dod-templates.json").write_text("{}\n", encoding="utf-8")

    # templates/*.tmpl
    templates = dist / "templates"
    templates.mkdir(parents=True)
    (templates / "agent.md.tmpl").write_text("agent\n", encoding="utf-8")
    (templates / "task.yaml.tmpl").write_text("task\n", encoding="utf-8")

    # settings-hooks.json -- the merge template
    (dist / "settings-hooks.json").write_text(
        json.dumps({"hooks": {"PreToolUse": []}}, indent=2) + "\n",
        encoding="utf-8",
    )


@pytest.fixture
def install_context(tmp_path: Path) -> install_steps.InstallContext:
    """Build a ready-to-use InstallContext rooted at tmp_path."""
    dist = tmp_path / "dist"
    target = tmp_path / "target"
    _seed_minimal_dist(dist)
    target.mkdir()
    return install_steps.InstallContext(
        target_dir=target,
        dist_dir=dist,
        client_choice="claude",
        mode=OperatorMode.NON_INTERACTIVE,
        repo_root=tmp_path,
    )


# -- AC-012: step count + glyph discipline ------------------------------


class TestStepCount:
    """AC-012: STEP_COUNT is exactly 11 and STEPS matches."""

    def test_should_expose_step_count_equal_to_eleven(self) -> None:
        assert install_steps.STEP_COUNT == 11

    def test_should_expose_steps_tuple_with_step_count_entries(self) -> None:
        assert len(install_steps.STEPS) == install_steps.STEP_COUNT

    def test_should_have_unique_step_names_in_steps_tuple(self) -> None:
        names = [name for name, _ in install_steps.STEPS]
        assert len(names) == len(set(names)), "duplicate step name in STEPS"


class TestStatusLineDiscipline:
    """AC-012: run_all emits exactly STEP_COUNT lines, each glyph-prefixed."""

    def test_should_emit_exactly_step_count_lines_when_run_all_completes(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange -- captured console
        sio = StringIO()
        # width=10_000 prevents rich from word-wrapping status lines that
        # contain long absolute paths (the tmp_path fixture's parent prefix
        # alone can push a status message past 120 chars). Wrapping would
        # split one logical status into two physical lines and break the
        # count assertion non-deterministically — observed flake on
        # 2026-05-22 full-suite runs.
        console = Console(
            file=sio, force_terminal=False, no_color=True, width=10_000
        )

        # Act
        install_steps.run_all(install_context, console)

        # Assert -- STEP_COUNT non-empty lines, each beginning with one of
        # the three glyphs after leading whitespace.
        emitted_lines = [
            ln for ln in sio.getvalue().splitlines() if ln.strip()
        ]
        assert len(emitted_lines) == install_steps.STEP_COUNT, (
            f"Expected {install_steps.STEP_COUNT} status lines, got "
            f"{len(emitted_lines)}: {emitted_lines}"
        )

    def test_should_prefix_each_line_with_one_of_three_glyphs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange
        sio = StringIO()
        # width=10_000 prevents rich from word-wrapping status lines that
        # contain long absolute paths (the tmp_path fixture's parent prefix
        # alone can push a status message past 120 chars). Wrapping would
        # split one logical status into two physical lines and break the
        # count assertion non-deterministically — observed flake on
        # 2026-05-22 full-suite runs.
        console = Console(
            file=sio, force_terminal=False, no_color=True, width=10_000
        )

        # Act
        install_steps.run_all(install_context, console)

        # Assert -- every line has a check, warn, or cross glyph.
        emitted_lines = [
            ln for ln in sio.getvalue().splitlines() if ln.strip()
        ]
        for line in emitted_lines:
            stripped = line.lstrip()
            assert (
                stripped.startswith("✓")  # check
                or stripped.startswith("⚠")  # warn
                or stripped.startswith("✗")  # cross
            ), f"line missing glyph prefix: {line!r}"


# -- BR-011 / AC-011: per-step filesystem effects -----------------------


class TestStepDirectoryStructure:
    """Step 1: TARGET_DIR/{agents,skills,standards,hooks,sdlc,scripts,templates}."""

    def test_should_create_seven_top_level_subdirs_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        result = install_steps.step_directory_structure(install_context)

        assert result.status == "ok"
        for sub in (
            "agents",
            "skills",
            "standards",
            "hooks",
            "sdlc",
            "scripts",
            "templates",
        ):
            assert (install_context.target_dir / sub).is_dir(), (
                f"missing {sub}/"
            )


class TestStepInstallAgents:
    """Step 2: copy dist/agents/*.md -> target/agents/."""

    def test_should_copy_every_agent_md_file_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_agents(install_context)

        assert result.status == "ok"
        agents = list((install_context.target_dir / "agents").glob("*.md"))
        assert len(agents) >= 2


class TestStepInstallSkills:
    """Step 3: skills install recursively (templates/ subdir lands)."""

    def test_should_preserve_skill_templates_subdir_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_skills(install_context)

        assert result.status == "ok"
        templates_dir = (
            install_context.target_dir / "skills" / "implement" / "templates"
        )
        assert templates_dir.is_dir(), "templates/ subdir must land"
        assert (templates_dir / "ticket.md.template").is_file()


class TestStepInstallStandards:
    """Step 4: standards/<category>/*.md copied recursively by category."""

    def test_should_copy_each_category_markdown_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_standards(install_context)

        assert result.status == "ok"
        for category in ("code", "process"):
            md = list(
                (install_context.target_dir / "standards" / category).glob(
                    "*.md"
                )
            )
            assert len(md) >= 1, f"no {category}/ standards installed"


class TestStepInstallStandardsNonMarkdown:
    """Step 4 must carry runtime-loaded non-markdown standards.

    Regression guard for the install gap where step_install_standards
    globbed only ``*.md``, stranding ``layer-rubrics.yaml`` (read by
    ``layer_review.py``) and ``ruff-reference.toml`` so /architect's
    Phase 2.9 layer-review engine degraded to advisory mode in every
    installed (non-repo) environment.
    """

    def test_should_install_runtime_yaml_registry_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_standards(install_context)

        assert result.status == "ok"
        rubrics = (
            install_context.target_dir
            / "standards"
            / "architecture"
            / "layer-rubrics.yaml"
        )
        assert rubrics.is_file(), (
            "layer-rubrics.yaml must land — layer_review.py reads it at runtime"
        )

    def test_should_install_toml_reference_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_standards(install_context)

        assert result.status == "ok"
        toml = (
            install_context.target_dir
            / "standards"
            / "code"
            / "ruff-reference.toml"
        )
        assert toml.is_file(), "ruff-reference.toml must land"

    def test_should_still_install_category_markdown_alongside_data_files(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        install_steps.step_install_standards(install_context)

        # The markdown sibling in the same category dir must still land —
        # broadening the glob must not regress the original behavior.
        assert (
            install_context.target_dir
            / "standards"
            / "architecture"
            / "layer-boundaries.md"
        ).is_file()


class TestStepInstallProfiles:
    """Step 5: standards/code/profiles/ subtree + chmod +x on gates."""

    def test_should_install_profile_subtree_and_set_executable(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_profiles(install_context)

        assert result.status == "ok"
        gate = (
            install_context.target_dir
            / "standards"
            / "code"
            / "profiles"
            / "python"
            / "gate.sh"
        )
        assert gate.is_file()
        # Check the executable bit is set for owner
        assert gate.stat().st_mode & stat.S_IXUSR


class TestStepInstallHooks:
    """Step 6: hooks/*.sh installed with +x."""

    def test_should_set_executable_bit_on_each_hook_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_hooks(install_context)

        assert result.status == "ok"
        for hook in (install_context.target_dir / "hooks").glob("*.sh"):
            assert hook.stat().st_mode & stat.S_IXUSR, (
                f"{hook.name} not +x"
            )

    def test_should_propagate_helpers_subdir_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        """Install-side twin of compiler Fix 1: hooks/helpers/*.py must land.

        Dispatcher hooks import .py helpers from hooks/helpers/; the old
        step copied only top-level *.sh, so verify-green's helpers were
        missing in every installed environment.
        """
        install_steps.step_directory_structure(install_context)

        install_steps.step_install_hooks(install_context)

        helper = (
            install_context.target_dir
            / "hooks"
            / "helpers"
            / "check_mutable_globals.py"
        )
        assert helper.exists(), (
            "step_install_hooks must recursively propagate hooks/helpers/"
        )


class TestStepMergeSettings:
    """Step 7: settings.json hooks section replaced via pure Python."""

    def test_should_create_settings_when_target_has_none(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_merge_settings(install_context)

        assert result.status == "ok"
        body = json.loads(
            (install_context.target_dir / "settings.json").read_text(
                encoding="utf-8"
            )
        )
        assert "hooks" in body

    def test_should_replace_hooks_section_when_settings_exists(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange -- pre-existing settings.json with other keys
        install_steps.step_directory_structure(install_context)
        settings = install_context.target_dir / "settings.json"
        settings.write_text(
            json.dumps(
                {"other_key": "preserved", "hooks": {"OldEvent": []}}
            )
            + "\n",
            encoding="utf-8",
        )

        result = install_steps.step_merge_settings(install_context)

        assert result.status == "ok"
        body = json.loads(settings.read_text(encoding="utf-8"))
        assert body["other_key"] == "preserved", (
            "non-hooks keys preserved"
        )
        assert "PreToolUse" in body["hooks"], "hooks section replaced"
        assert "OldEvent" not in body["hooks"], "old hooks dropped"

    def test_should_substitute_hooks_dir_placeholder_into_target_dir(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange — compiler emits {{ETC_HOOKS_DIR}} placeholder; step 7
        # must substitute it with target_dir/hooks so hook command paths
        # match the operator's actual install location.
        install_steps.step_directory_structure(install_context)
        template = install_context.dist_dir / "settings-hooks.json"
        template.write_text(
            json.dumps(
                {
                    "hooks": {
                        "PreToolUse": [
                            {
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": "{{ETC_HOOKS_DIR}}/check-test-exists.sh",
                                    }
                                ]
                            }
                        ]
                    }
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )

        result = install_steps.step_merge_settings(install_context)

        assert result.status == "ok"
        body = json.loads(
            (install_context.target_dir / "settings.json").read_text(
                encoding="utf-8"
            )
        )
        command = body["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        expected = (
            f"{install_context.target_dir / 'hooks'}/check-test-exists.sh"
        )
        assert command == expected, (
            "step_merge_settings must substitute {{ETC_HOOKS_DIR}} for "
            f"target_dir/hooks; got {command!r}"
        )


class TestStepInstallSdlc:
    """Step 8: sdlc/tracker.py + dod-templates.json with +x on tracker."""

    def test_should_install_tracker_executable_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_sdlc(install_context)

        assert result.status == "ok"
        tracker = install_context.target_dir / "sdlc" / "tracker.py"
        assert tracker.is_file()
        assert tracker.stat().st_mode & stat.S_IXUSR


class TestStepInstallTemplates:
    """Step 9: templates/*.tmpl copied."""

    def test_should_copy_every_tmpl_file_when_step_runs(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_templates(install_context)

        assert result.status == "ok"
        tmpls = list(
            (install_context.target_dir / "templates").glob("*.tmpl")
        )
        assert len(tmpls) >= 2


class TestStepInstallGitHooksAndScripts:
    """Step 10: hooks/git/* and scripts/* installed with +x."""

    def test_should_set_executable_bit_on_git_hooks_and_scripts(
        self, install_context: install_steps.InstallContext
    ) -> None:
        install_steps.step_directory_structure(install_context)

        result = install_steps.step_install_git_hooks_and_scripts(
            install_context
        )

        assert result.status == "ok"
        for git_hook in (
            install_context.target_dir / "hooks" / "git"
        ).iterdir():
            if git_hook.is_file():
                assert git_hook.stat().st_mode & stat.S_IXUSR
        for script in (install_context.target_dir / "scripts").iterdir():
            if script.is_file():
                assert script.stat().st_mode & stat.S_IXUSR


class TestStepProfileDetection:
    """Step 11: F020 detect_profiles invocation against repo_root."""

    def test_should_return_ok_status_when_detect_script_runs_cleanly(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange -- install scripts (so detect_profiles.py is at target)
        install_steps.step_directory_structure(install_context)
        install_steps.step_install_git_hooks_and_scripts(install_context)

        result = install_steps.step_profile_detection(install_context)

        # The stub script returns 0 and writes empty lock; status is ok.
        assert result.status == "ok"


# -- InstallContext dataclass ------------------------------------------


class TestInstallContextDataclass:
    """InstallContext is a frozen dataclass with the documented fields."""

    def test_should_be_frozen_when_constructed(self, tmp_path: Path) -> None:
        ctx = install_steps.InstallContext(
            target_dir=tmp_path / "target",
            dist_dir=tmp_path / "dist",
            client_choice="claude",
            mode=OperatorMode.NON_INTERACTIVE,
            repo_root=tmp_path,
        )
        with pytest.raises((AttributeError, TypeError)):
            ctx.target_dir = tmp_path  # type: ignore[misc]


# -- StepResult dataclass ----------------------------------------------


class TestStepResult:
    """StepResult exposes status + message; status is one of ok/warn/error."""

    def test_should_construct_with_status_and_message(self) -> None:
        r = install_steps.StepResult(status="ok", message="done")
        assert r.status == "ok"
        assert r.message == "done"


# -- Error-path: invalid settings.json triggers error status ---------


class TestSettingsMergeInvalidJson:
    """Step 7 returns status="error" when existing settings.json is malformed."""

    def test_should_return_error_when_existing_settings_is_invalid_json(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange -- corrupt settings.json
        install_steps.step_directory_structure(install_context)
        settings = install_context.target_dir / "settings.json"
        settings.write_text("not-valid-json{", encoding="utf-8")

        result = install_steps.step_merge_settings(install_context)

        assert result.status == "error"
        assert "not valid JSON" in result.message


# -- Third-party preflight composition (the audit dead-surface fix) ----


class TestRunThirdPartyPreflights:
    """run_third_party_preflights composes preflights.offer_install per tool.

    The audit found offer_install + the four INFO_LINE constants shipped
    with ZERO call sites — fresh installs never learned the third-party
    tools were missing. This is the composition that wires them.
    """

    def test_should_offer_install_for_each_absent_tool_when_interactive(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange -- INTERACTIVE mode; force every tool to read as absent.
        ctx = install_steps.InstallContext(
            target_dir=install_context.target_dir,
            dist_dir=install_context.dist_dir,
            client_choice="claude",
            mode=OperatorMode.INTERACTIVE,
            repo_root=install_context.repo_root,
        )
        console = Console(file=StringIO())

        # Act -- patch detection to absent + offer_install to a spy.
        with mock.patch.object(
            install_steps.preflights, "is_gh_stack_present", return_value=False
        ), mock.patch.object(
            install_steps.preflights, "is_impeccable_present", return_value=False
        ), mock.patch.object(
            install_steps.preflights, "is_mergiraf_present", return_value=False
        ), mock.patch.object(
            install_steps.preflights,
            "is_google_designmd_present",
            return_value=False,
        ), mock.patch.object(
            install_steps.preflights, "offer_install"
        ) as offer_spy:
            install_steps.run_third_party_preflights(ctx)

        # Assert -- one offer per absent tool, all four INFO lines passed.
        offered_info_lines = {call.args[1] for call in offer_spy.call_args_list}
        assert install_steps.preflights.F010_INFO_LINE in offered_info_lines
        assert install_steps.preflights.F011_INFO_LINE in offered_info_lines
        assert install_steps.preflights.F016_INFO_LINE in offered_info_lines
        assert install_steps.preflights.F018_INFO_LINE in offered_info_lines

    def test_should_pass_operator_mode_through_to_offer_install(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange -- NON_INTERACTIVE mode must reach offer_install so it
        # prints the INFO line instead of prompting.
        ctx = install_steps.InstallContext(
            target_dir=install_context.target_dir,
            dist_dir=install_context.dist_dir,
            client_choice="claude",
            mode=OperatorMode.NON_INTERACTIVE,
            repo_root=install_context.repo_root,
        )
        console = Console(file=StringIO())

        with mock.patch.object(
            install_steps.preflights, "is_gh_stack_present", return_value=False
        ), mock.patch.object(
            install_steps.preflights, "is_impeccable_present", return_value=False
        ), mock.patch.object(
            install_steps.preflights, "is_mergiraf_present", return_value=False
        ), mock.patch.object(
            install_steps.preflights,
            "is_google_designmd_present",
            return_value=False,
        ), mock.patch.object(
            install_steps.preflights, "offer_install"
        ) as offer_spy:
            install_steps.run_third_party_preflights(ctx)

        # Assert -- every offer got ctx.mode (the 4th positional arg).
        modes = {call.args[3] for call in offer_spy.call_args_list}
        assert modes == {OperatorMode.NON_INTERACTIVE}

    def test_should_not_offer_for_tools_already_present(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # Arrange -- every tool present → no offers at all.
        ctx = install_steps.InstallContext(
            target_dir=install_context.target_dir,
            dist_dir=install_context.dist_dir,
            client_choice="claude",
            mode=OperatorMode.INTERACTIVE,
            repo_root=install_context.repo_root,
        )
        console = Console(file=StringIO())

        with mock.patch.object(
            install_steps.preflights, "is_gh_stack_present", return_value=True
        ), mock.patch.object(
            install_steps.preflights, "is_impeccable_present", return_value=True
        ), mock.patch.object(
            install_steps.preflights, "is_mergiraf_present", return_value=True
        ), mock.patch.object(
            install_steps.preflights,
            "is_google_designmd_present",
            return_value=True,
        ), mock.patch.object(
            install_steps.preflights, "offer_install"
        ) as offer_spy:
            install_steps.run_third_party_preflights(ctx)

        assert offer_spy.call_count == 0


# -- Interactive extras composition (status-line + sandbox prompts) ----


class TestRunInteractiveExtras:
    """run_interactive_extras composes the status-line + sandbox prompts.

    The audit found install_status_line + install_sandbox_config shipped
    with ZERO call sites. This is the composition that wires them, gated
    on ctx.mode (the field the audit found was computed but never read).
    """

    def test_should_invoke_both_prompts_when_interactive(
        self, install_context: install_steps.InstallContext
    ) -> None:
        ctx = install_steps.InstallContext(
            target_dir=install_context.target_dir,
            dist_dir=install_context.dist_dir,
            client_choice="claude",
            mode=OperatorMode.INTERACTIVE,
            repo_root=install_context.repo_root,
        )

        with mock.patch.object(
            install_steps.status_line, "install_status_line"
        ) as sl_spy, mock.patch.object(
            install_steps.sandbox_config, "install_sandbox_config"
        ) as sc_spy:
            install_steps.run_interactive_extras(ctx)

        sl_spy.assert_called_once_with(ctx.target_dir, OperatorMode.INTERACTIVE)
        sc_spy.assert_called_once_with(ctx.target_dir, OperatorMode.INTERACTIVE)

    def test_should_pass_non_interactive_mode_through(
        self, install_context: install_steps.InstallContext
    ) -> None:
        # NON_INTERACTIVE still reaches the installers — they self-skip on
        # mode internally; the composition must not branch on mode itself.
        ctx = install_steps.InstallContext(
            target_dir=install_context.target_dir,
            dist_dir=install_context.dist_dir,
            client_choice="claude",
            mode=OperatorMode.NON_INTERACTIVE,
            repo_root=install_context.repo_root,
        )

        with mock.patch.object(
            install_steps.status_line, "install_status_line"
        ) as sl_spy, mock.patch.object(
            install_steps.sandbox_config, "install_sandbox_config"
        ) as sc_spy:
            install_steps.run_interactive_extras(ctx)

        sl_spy.assert_called_once_with(
            ctx.target_dir, OperatorMode.NON_INTERACTIVE
        )
        sc_spy.assert_called_once_with(
            ctx.target_dir, OperatorMode.NON_INTERACTIVE
        )
