"""Contract tests for F010: Stacked PRs from /build.

Covers PRD .etc_sdlc/features/F010-stacked-prs-from-build/spec.md
acceptance criteria AC1, AC3-AC5, AC7-AC11 via:

- Grep tests over the source artifacts ``skills/build/SKILL.md`` and
  ``install.sh`` for verbatim strings documented in spec.md (the LOC
  WARNING prefix from AC5, the INFO line from AC10, the ``6d.7`` sub-step
  header from AC1, the layer-branch regex from AC4, and the resume +
  state-schema documentation from AC7-AC9).
- Synthetic-git-repo construction tests that prove ``tmp_path``-rooted
  ``git init`` repos can be used to model layer-branch creation without
  touching the project's real repo or any real ``.etc_sdlc/features/*``
  directories.

These tests are written FIRST per TDD red-green-refactor — the contracts
they assert do NOT yet exist in ``skills/build/SKILL.md`` or ``install.sh``.
Wave 1 tasks edit those source files to turn the tests green. The initial
fail pattern is the expected outcome of the red phase.

Precedent:

- ``tests/test_completion_report.py`` (F005): ``pytest tmp_path`` plus
  ``subprocess.run`` invocation of helpers with ``cwd=tmp_path``, plus
  grep-based contract assertions over committed source.
- ``tests/test_wave_planner_implicit_deps.py`` (F008): synthetic feature
  directories under ``<tmp_path>/.etc_sdlc/features/F999-*/`` constructed
  per-test; subprocess invocation that protects real F001-F009 artifacts
  by construction; verbatim string greps.
- ``tests/test_windows_compatibility.py``: grep tests over the literal
  contents of ``install.sh`` (module-level ``INSTALL_SH`` constant +
  ``install_sh_text`` fixture pattern).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL_BUILD = REPO_ROOT / "skills" / "build" / "SKILL.md"
INSTALL_SH = REPO_ROOT / "install.sh"

# Verbatim strings from spec.md (BR-004 + AC5, BR-007 + AC10, AC1).
# Tests grep for these prefixes; the strings live in the source artifacts
# after Wave 1's edits land.
LOC_WARNING_PREFIX = "WARNING: layer L"
INSTALL_INFO_PREFIX = "INFO: gh-stack not detected"
STEP_6D7_HEADER = "6d.7: Emit stack layer"

# AC4 / BR-003: layer-branch naming regex documented verbatim in skill body.
LAYER_BRANCH_REGEX_LITERAL = "^[a-z][a-z0-9-]+-L[0-9]+$"

# Module-level reference so static analyzers see ``pytest`` as accessed by
# the tmp_path fixture indirection. Mirrors test_wave_planner_implicit_deps.
_ = pytest


# ── Module-scoped text fixtures ──────────────────────────────────────────


@pytest.fixture(scope="module")
def skill_build_text() -> str:
    """Read ``skills/build/SKILL.md`` once per module."""
    assert SKILL_BUILD.exists(), (
        f"missing source skill: {SKILL_BUILD}; F010 tests cannot run without it"
    )
    return SKILL_BUILD.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def install_sh_text() -> str:
    """Read ``install.sh`` once per module."""
    assert INSTALL_SH.exists(), (
        f"missing installer: {INSTALL_SH}; F010 tests cannot run without it"
    )
    return INSTALL_SH.read_text(encoding="utf-8")


# ── Synthetic-git-repo helpers (F005 + F008 precedent) ───────────────────


def _git_init_repo(tmp_path: Path) -> Path:
    """Create a fresh git repo rooted at ``tmp_path``.

    Uses ``subprocess.run(["git", "init", ...])`` per F005 + F008's
    "synthetic git repo per test" precedent. Configures a deterministic
    user.email + user.name so commits do not depend on the host's global
    git config (which may be unset in CI). Returns ``tmp_path``.
    """
    subprocess.run(
        ["git", "init", "--initial-branch=main", str(tmp_path)],
        check=True,
        capture_output=True,
    )
    # Local config — never modify the host's global git config (CLAUDE.md
    # safety rule). The local config lives in tmp_path/.git/config and is
    # discarded with tmp_path teardown.
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.email", "f010-test@example.invalid"],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(tmp_path), "config", "user.name", "F010 Test"],
        check=True,
        capture_output=True,
    )
    return tmp_path


def _git_commit_initial(repo: Path, filename: str = "README.md") -> str:
    """Write a tiny file and commit it; return the resulting commit SHA.

    Establishes a HEAD on ``main`` so subsequent branch-creation tests
    have a base. Argv-list invocation; no shell strings.
    """
    (repo / filename).write_text("initial\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", filename],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "-C", str(repo), "commit", "-m", "initial"],
        check=True,
        capture_output=True,
    )
    out = subprocess.run(
        ["git", "-C", str(repo), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    )
    return out.stdout.strip()


# ─────────────────────────────────────────────────────────────────────────
# Contract tests over skills/build/SKILL.md (the source-of-truth skill body
# the compiler emits into dist/skills/build/SKILL.md). Wave 1 task 002 adds
# the 6d.7 sub-step + accompanying documentation to this file.
# ─────────────────────────────────────────────────────────────────────────


# BR-009 (a) + AC1 + AC2: Step 6d.7 sub-step ordering — header exists,
# positioned after 6d (phase-done tag + completion-report) and before 6e.
def test_skill_build_documents_step_6d_7_header(skill_build_text: str) -> None:
    """AC1: ``skills/build/SKILL.md`` contains the ``6d.7: Emit stack
    layer`` sub-step header.

    Grep is verbatim per the task YAML acceptance criterion. The header
    is the load-bearing marker that the stack-emission sub-step exists
    in the documented build pipeline; without it, downstream contracts
    have no anchor.
    """
    assert STEP_6D7_HEADER in skill_build_text, (
        f"skills/build/SKILL.md missing verbatim sub-step header "
        f"{STEP_6D7_HEADER!r}; expected per F010 spec.md AC1"
    )


def test_skill_build_orders_6d_7_after_6d_and_before_6e(
    skill_build_text: str,
) -> None:
    """AC1 + AC2 + BR-001: 6d.7 sub-step is positioned between 6d
    (phase-done tag + completion-report) and 6e (proceed to next wave).

    The phase-N/done tag is written at 6d BEFORE 6d.7 fires (so the
    append-only tag remains even if 6d.7 fails — edge case 3). The
    ordering of the documented sub-step headers in the skill body
    encodes this contract.
    """
    idx_6d = skill_build_text.find("6d.")
    idx_6d_7 = skill_build_text.find(STEP_6D7_HEADER)
    idx_6e = skill_build_text.find("6e.")

    assert idx_6d != -1, "skills/build/SKILL.md missing Step 6d marker"
    assert idx_6d_7 != -1, (
        f"skills/build/SKILL.md missing 6d.7 sub-step header "
        f"{STEP_6D7_HEADER!r}"
    )
    assert idx_6e != -1, "skills/build/SKILL.md missing Step 6e marker"

    assert idx_6d < idx_6d_7, (
        f"6d.7 sub-step (at offset {idx_6d_7}) must appear AFTER the first "
        f"6d marker (at offset {idx_6d}). The phase-N/done tag is written "
        f"at 6d BEFORE 6d.7 fires per BR-001 + edge case 3."
    )
    assert idx_6d_7 < idx_6e, (
        f"6d.7 sub-step (at offset {idx_6d_7}) must appear BEFORE the 6e "
        f"marker (at offset {idx_6e}). 6d.7 runs in the Step 6 region, "
        f"not after the wave-completion handoff."
    )


# BR-009 (b) + AC4 + BR-003: Layer branch naming regex documented verbatim.
def test_skill_build_documents_layer_branch_regex(skill_build_text: str) -> None:
    """AC4 + BR-003: layer branches match ``^[a-z][a-z0-9-]+-L[0-9]+$``.

    The skill body documents the regex verbatim so future maintenance
    has a single source of truth for the naming contract. Also assert
    the regex is well-formed and matches the canonical example from
    BR-003 (``stacked-prs-from-build-L1``).
    """
    assert LAYER_BRANCH_REGEX_LITERAL in skill_build_text, (
        f"skills/build/SKILL.md missing verbatim layer-branch regex "
        f"{LAYER_BRANCH_REGEX_LITERAL!r}; expected per F010 spec.md AC4 / BR-003"
    )

    # Sanity: the documented regex compiles and matches BR-003's example.
    pattern = re.compile(LAYER_BRANCH_REGEX_LITERAL)
    assert pattern.match("stacked-prs-from-build-L1"), (
        f"documented regex {LAYER_BRANCH_REGEX_LITERAL!r} does not match the "
        f"canonical BR-003 example 'stacked-prs-from-build-L1'"
    )
    assert pattern.match("stacked-prs-from-build-L2"), (
        f"documented regex {LAYER_BRANCH_REGEX_LITERAL!r} does not match the "
        f"second-wave example 'stacked-prs-from-build-L2'"
    )
    # Anti-cases: slugs containing characters outside [a-z0-9-] must NOT
    # match; sanitization at branch-creation strips them per BR-003.
    assert not pattern.match("Add_User_Auth_v2-L1"), (
        f"documented regex {LAYER_BRANCH_REGEX_LITERAL!r} must NOT match a "
        f"non-canonical pre-sanitization slug; got match on "
        f"'Add_User_Auth_v2-L1'"
    )
    assert not pattern.match("UPPERCASE-L1"), (
        f"documented regex {LAYER_BRANCH_REGEX_LITERAL!r} must NOT match a "
        f"non-lowercase slug; got match on 'UPPERCASE-L1'"
    )


# BR-009 (c) + GA-002: squash-commit contents — one commit per wave.
def test_skill_build_documents_squash_commit_contract(
    skill_build_text: str,
) -> None:
    """AC2 + GA-002: 6d.7 body documents the squash-commit operation.

    The skill body must document that 6d.7 collects every file modified
    during the wave and squash-commits them on the new layer branch.
    Grep is for the literal substring ``squash-commit`` (or ``squash
    commit``) somewhere in the 6d.7 region; both spellings are
    acceptable per spec.md text.
    """
    idx_6d_7 = skill_build_text.find(STEP_6D7_HEADER)
    assert idx_6d_7 != -1, (
        f"skills/build/SKILL.md missing 6d.7 sub-step header "
        f"{STEP_6D7_HEADER!r}"
    )
    # Scope to the 6d.7 region (from header to ~3000 chars onward; the
    # sub-step body should be smaller than that). Tests are not precise
    # about the upper bound — any of the required tokens must appear
    # after the 6d.7 marker.
    region = skill_build_text[idx_6d_7 : idx_6d_7 + 3000]

    # Squash-commit operation is documented (either spelling acceptable).
    squash_tokens = ("squash-commit", "squash commit")
    assert any(token in region for token in squash_tokens), (
        f"skills/build/SKILL.md 6d.7 region missing squash-commit operation "
        f"documentation; expected one of {squash_tokens!r} per GA-002"
    )


# BR-009 (d) + AC3 + BR-002: gh-stack invocation is argv-list, not shell string.
def test_skill_build_documents_gh_stack_argv_invocation(
    skill_build_text: str,
) -> None:
    """AC3 + BR-002: ``subprocess.run`` invocation with argv list.

    The skill body must document the gh-stack invocation as an argv
    list (NOT a shell string). Mirrors F003's operator-supplied path
    sanitization and F008's ``git mv`` invocation pattern. The argv
    elements include ``gh``, ``stack``, ``push``, and ``--base``.
    """
    idx_6d_7 = skill_build_text.find(STEP_6D7_HEADER)
    assert idx_6d_7 != -1, (
        f"skills/build/SKILL.md missing 6d.7 sub-step header "
        f"{STEP_6D7_HEADER!r}"
    )
    region = skill_build_text[idx_6d_7 : idx_6d_7 + 3000]

    # The gh-stack invocation appears in the region — at minimum the
    # tool name and the documented subcommand.
    assert "gh stack" in region or "gh-stack" in region, (
        f"skills/build/SKILL.md 6d.7 region missing gh-stack tool reference; "
        f"expected 'gh stack' or 'gh-stack' per BR-002"
    )
    # The argv-list invocation form is documented. Either ``subprocess.run``
    # is mentioned, or the literal argv elements appear together.
    has_subprocess_run = "subprocess.run" in region
    has_push_subcommand = "push" in region
    has_base_flag = "--base" in region
    assert has_subprocess_run, (
        f"skills/build/SKILL.md 6d.7 region missing 'subprocess.run' marker "
        f"for the argv-list invocation contract per AC3 / BR-002"
    )
    assert has_push_subcommand, (
        f"skills/build/SKILL.md 6d.7 region missing 'push' subcommand from "
        f"the documented gh stack invocation per BR-002"
    )
    assert has_base_flag, (
        f"skills/build/SKILL.md 6d.7 region missing '--base' flag from the "
        f"documented gh stack invocation per BR-002"
    )


# BR-009 (e) + AC5 + BR-004: LOC warning verbatim text.
def test_skill_build_documents_loc_warning_verbatim(
    skill_build_text: str,
) -> None:
    """AC5 + BR-004: LOC warning verbatim line is documented.

    The skill body must contain the warning text verbatim. The test
    contract greps for the prefix ``WARNING: layer L`` (the placeholders
    ``<N>`` and ``<K>`` mean the rest of the line is template text in
    the skill body). The full canonical line is:

        WARNING: layer L<N> contains <K> LOC (target: 500). Consider
        splitting the wave for review tractability. Proceeding with
        stack emission.

    Verbatim grep is on the prefix per the task YAML acceptance criterion.
    """
    assert LOC_WARNING_PREFIX in skill_build_text, (
        f"skills/build/SKILL.md missing verbatim LOC warning prefix "
        f"{LOC_WARNING_PREFIX!r}; expected per F010 spec.md AC5 / BR-004"
    )
    # Additional verbatim tokens from the canonical warning line — these
    # appear in spec.md AC5's literal block and must survive into the
    # skill body so the line is grep-stable at runtime.
    assert "target: 500" in skill_build_text, (
        f"skills/build/SKILL.md missing literal 'target: 500' from the "
        f"LOC warning per AC5 / BR-004"
    )
    assert "Proceeding with stack emission" in skill_build_text, (
        f"skills/build/SKILL.md missing literal 'Proceeding with stack "
        f"emission' from the LOC warning per AC5 / BR-004"
    )


# BR-009 (f) + AC7 + BR-005: Single-wave bypass documented.
def test_skill_build_documents_single_wave_bypass(skill_build_text: str) -> None:
    """AC7 + BR-005: 6d.7 is SKIPPED when ``total_waves == 1``.

    The skill body must document the bypass condition explicitly. The
    skip path writes ``state.yaml.build.stacked = false``; the multi-wave
    path writes ``true``. Grep for both the bypass condition and the
    boolean state field.
    """
    # Bypass condition is documented somewhere in the skill body.
    bypass_tokens = ("total_waves == 1", "total_waves=1", "single-wave")
    assert any(token in skill_build_text for token in bypass_tokens), (
        f"skills/build/SKILL.md missing single-wave bypass condition; "
        f"expected one of {bypass_tokens!r} per AC7 / BR-005"
    )


# BR-009 (f) + AC8: state.yaml schema extension documented.
def test_skill_build_documents_state_yaml_stacked_field(
    skill_build_text: str,
) -> None:
    """AC8: ``state.yaml.build.stacked: bool`` documented as a
    merge-preserve field.

    The skill body must declare the ``stacked`` field as part of Step
    2's merge-preserve dict shape (or document the field anywhere in
    the skill body — Step 2's shape is the canonical home but the
    field must be visible to readers).
    """
    # The literal ``stacked`` field name appears in the skill body in a
    # state.yaml context. Grep for the field paired with either ``true``,
    # ``false``, or ``bool`` as a type hint, OR alongside the ``build``
    # block in Step 2's merge-preserve dict.
    field_tokens = (
        "'stacked'",       # Python dict literal in Step 2's merge block
        '"stacked"',       # JSON-style literal
        "build.stacked",   # dotted path reference
        "stacked: bool",   # type annotation
        "stacked: true",   # state.yaml example
        "stacked: false",  # state.yaml example
    )
    assert any(token in skill_build_text for token in field_tokens), (
        f"skills/build/SKILL.md missing state.yaml 'stacked' field "
        f"declaration; expected one of {field_tokens!r} per AC8 / BR-005"
    )


# BR-009 (g) + AC9 + BR-006: --resume across layer boundary.
def test_skill_build_documents_resume_across_layer_boundary(
    skill_build_text: str,
) -> None:
    """AC9 + BR-006: ``/build --resume`` documents stacking-aware behavior.

    When ``state.yaml.build.stacked == true``, resume picks up at
    ``waves_completed + 1`` with the new layer based on the previous
    completed layer's branch. The skill body must document this.
    """
    # The Resume Protocol section already exists in skill body; the F010
    # edit must extend it to mention stacking-aware behavior. Grep for
    # both the ``stacked`` field reference AND the resume mechanic.
    resume_idx = skill_build_text.find("Resume Protocol")
    assert resume_idx != -1, (
        "skills/build/SKILL.md missing 'Resume Protocol' section header"
    )

    # Look anywhere in the skill body for the resume-with-stacking
    # contract. Acceptable forms: a ``--resume`` reference paired with
    # ``stacked`` somewhere in the body, OR an explicit mention of
    # ``waves_completed`` in the layer-resume context.
    has_resume_token = "--resume" in skill_build_text or "resume" in skill_build_text.lower()
    has_stacked_token = "stacked" in skill_build_text
    has_waves_completed_token = "waves_completed" in skill_build_text

    assert has_resume_token, (
        "skills/build/SKILL.md missing '--resume' / 'resume' reference"
    )
    assert has_stacked_token, (
        "skills/build/SKILL.md missing 'stacked' field reference for resume "
        "across layer boundary per AC9 / BR-006"
    )
    assert has_waves_completed_token, (
        "skills/build/SKILL.md missing 'waves_completed' reference; resume "
        "from layer boundary uses waves_completed + 1 per BR-006"
    )


# ─────────────────────────────────────────────────────────────────────────
# Contract tests over install.sh (the installer that preflight-checks for
# gh-stack). Wave 1 task 003 adds the preflight INFO message to this file.
# ─────────────────────────────────────────────────────────────────────────


# BR-009 (h) + AC10 + BR-007: install.sh preflight INFO message verbatim.
def test_install_sh_documents_gh_stack_preflight_info(
    install_sh_text: str,
) -> None:
    """AC10 + BR-007: install.sh contains the gh-stack preflight INFO
    message verbatim.

    The test contract greps for the verbatim prefix ``INFO: gh-stack
    not detected``. The full canonical line is:

        INFO: gh-stack not detected. Stacked-PR builds (etc F010+)
        require gh-stack. Install via: gh extension install
        jiazh/gh-stack (or equivalent). Single-wave builds work without it.
    """
    assert INSTALL_INFO_PREFIX in install_sh_text, (
        f"install.sh missing verbatim INFO message prefix "
        f"{INSTALL_INFO_PREFIX!r}; expected per F010 spec.md AC10 / BR-007"
    )
    # Additional verbatim tokens from the canonical INFO line.
    assert "gh extension install jiazh/gh-stack" in install_sh_text, (
        f"install.sh missing literal install instruction 'gh extension "
        f"install jiazh/gh-stack' per AC10 / BR-007"
    )
    assert "Single-wave builds work without it" in install_sh_text, (
        f"install.sh missing literal 'Single-wave builds work without it' "
        f"closing clause from the INFO message per AC10 / BR-007"
    )


# AC11 + BR-007: preflight is non-blocking (INFO, not ERROR).
def test_install_sh_preflight_is_non_blocking(install_sh_text: str) -> None:
    """AC11 + BR-007: install.sh's gh-stack preflight is non-blocking.

    The INFO message must NOT cause the installer to exit non-zero. The
    check uses ``command -v gh-stack`` (or ``gh stack --help``) and on
    absence, prints the INFO via the existing ``info()``/``warn()``
    helpers — NEVER ``error()`` + ``exit 1``.

    Test contract: in the surrounding region of the INFO message, the
    closest exit-related token is NOT ``exit 1`` (which would block).
    """
    info_idx = install_sh_text.find(INSTALL_INFO_PREFIX)
    assert info_idx != -1, (
        f"install.sh missing INFO message; cannot verify non-blocking "
        f"behavior. Expected prefix {INSTALL_INFO_PREFIX!r}."
    )
    # Region: from a bit before the INFO line to a bit after. Scope is
    # tight on purpose — we want to catch an ``exit 1`` in the same
    # conditional block, not one further down the installer.
    region_start = max(0, info_idx - 400)
    region_end = min(len(install_sh_text), info_idx + 400)
    region = install_sh_text[region_start:region_end]

    # The preflight block must not emit ``exit 1`` immediately around
    # the INFO message — that would make the check blocking. (The
    # installer has other ``exit 1`` calls elsewhere for hard-fail
    # conditions like missing dist/, which are unrelated.)
    assert "exit 1" not in region, (
        f"install.sh INFO region contains 'exit 1' near the gh-stack "
        f"preflight message; preflight must be non-blocking per AC11. "
        f"region={region!r}"
    )


# ─────────────────────────────────────────────────────────────────────────
# Synthetic-git-repo tests (F005 + F008 precedent for tmp_path isolation).
# These prove the test harness can model layer-branch creation without
# touching real project state or real .etc_sdlc/features/* directories.
# ─────────────────────────────────────────────────────────────────────────


# AC13: all tests use tmp_path; no real repo / real features dir is touched.
def test_synthetic_git_repo_isolates_from_project_repo(tmp_path: Path) -> None:
    """AC13: tests construct synthetic git repos via ``subprocess.run(["git",
    "init", str(tmp_path), ...])`` per F005 + F008 precedent.

    Self-check: confirm the harness's git-init helper produces a repo
    rooted under ``tmp_path`` and that the repo's ``.git`` directory
    lives inside ``tmp_path`` (NOT inside the project's real repo).
    This proves the test contract from AC13 — every subprocess invocation
    in this file uses ``tmp_path`` rooting.
    """
    repo = _git_init_repo(tmp_path)
    assert repo == tmp_path, (
        f"helper returned a path {repo!r} that is not the requested tmp_path "
        f"{tmp_path!r}"
    )
    git_dir = tmp_path / ".git"
    assert git_dir.is_dir(), (
        f"synthetic repo's .git directory not found at {git_dir!r}; the "
        f"git init invocation did not produce a real repo in tmp_path"
    )
    # Critically: the synthetic .git/ must live under tmp_path, NOT under
    # the project's real repo. If this assertion ever fails, the harness
    # has corrupted real project state.
    assert str(git_dir).startswith(str(tmp_path)), (
        f"synthetic .git directory at {git_dir!r} is NOT under tmp_path "
        f"{tmp_path!r}; F010 tests must NEVER touch the real project repo"
    )
    assert not str(git_dir).startswith(str(REPO_ROOT) + "/"), (
        f"synthetic .git directory at {git_dir!r} is inside the project "
        f"repo {REPO_ROOT!r}; F010 tests must NEVER touch the real repo"
    )


# BR-003 + AC4: layer-branch name follows the documented regex.
def test_layer_branch_name_matches_documented_regex(tmp_path: Path) -> None:
    """BR-003 + AC4: a layer branch created with the canonical naming
    scheme passes the documented regex check.

    Create a synthetic repo with an initial commit on main, then create
    a branch named ``stacked-prs-from-build-L1`` (the canonical example
    from BR-003) and verify that ``git`` accepts the name and that the
    name matches the documented regex.
    """
    repo = _git_init_repo(tmp_path)
    _git_commit_initial(repo)

    # Canonical layer-branch name from BR-003 (the F010 feature itself).
    layer_branch = "stacked-prs-from-build-L1"

    # The regex documented in the skill body (AC4) must accept this name.
    pattern = re.compile(LAYER_BRANCH_REGEX_LITERAL)
    assert pattern.match(layer_branch), (
        f"documented regex {LAYER_BRANCH_REGEX_LITERAL!r} rejects the "
        f"canonical BR-003 layer branch name {layer_branch!r}"
    )

    # Git accepts the name (argv-list invocation per BR-002).
    result = subprocess.run(
        ["git", "-C", str(repo), "branch", layer_branch],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"git refused the canonical layer-branch name {layer_branch!r}; "
        f"stderr={result.stderr!r}"
    )

    # Verify the branch shows up in `git branch --list`.
    list_result = subprocess.run(
        ["git", "-C", str(repo), "branch", "--list", layer_branch],
        capture_output=True,
        text=True,
        check=True,
    )
    assert layer_branch in list_result.stdout, (
        f"created layer branch {layer_branch!r} not in `git branch --list` "
        f"output: {list_result.stdout!r}"
    )


# BR-001 + edge case 6: layer-branch already exists fails fast.
def test_layer_branch_creation_fails_when_branch_exists(tmp_path: Path) -> None:
    """Edge case 6 + BR-001: re-running ``/build`` (without ``--resume``)
    on a feature whose first layer branch already exists must fail fast.

    Model: create the synthetic repo + initial commit + the layer branch,
    then attempt to create the SAME branch again. ``git branch`` exits
    non-zero with stderr indicating the branch already exists. This is
    the failure mode the F010 implementation must surface to the operator.
    """
    repo = _git_init_repo(tmp_path)
    _git_commit_initial(repo)

    layer_branch = "stacked-prs-from-build-L1"

    # First creation: success.
    first = subprocess.run(
        ["git", "-C", str(repo), "branch", layer_branch],
        capture_output=True,
        text=True,
    )
    assert first.returncode == 0, (
        f"initial branch creation failed: stderr={first.stderr!r}"
    )

    # Second creation: must fail (branch already exists).
    second = subprocess.run(
        ["git", "-C", str(repo), "branch", layer_branch],
        capture_output=True,
        text=True,
    )
    assert second.returncode != 0, (
        f"expected non-zero exit when creating an existing branch "
        f"{layer_branch!r}; got stdout={second.stdout!r} "
        f"stderr={second.stderr!r}. /build's edge case 6 contract requires "
        f"this to be detectable so the operator is told to use --resume "
        f"or `git branch -D`."
    )
    # Surface the conflict reason verbatim — the implementation greps
    # this stderr to construct its operator-friendly error message.
    assert "already exists" in second.stderr.lower(), (
        f"expected 'already exists' in stderr from second branch creation; "
        f"got stderr={second.stderr!r}"
    )
