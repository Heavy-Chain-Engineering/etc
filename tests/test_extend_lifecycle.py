"""Integration test for the full F025 `/build --extend` lifecycle.

<!-- forward-only: extend lifecycle enforced from F025 release tag onward -->

Coverage targets per task 008 acceptance criteria:

- **AC-007+AC-009+AC-011 (full lifecycle):** integration test in
  ``tmp_path`` with fresh ``git init`` exercises the full lifecycle.
  Setup a synthetic shipped feature dir (``F042-fixture/``) with
  ``spec.md``, ``design.md``, ``state.yaml`` (no ``extends:`` field),
  ``verification.md``, ``release-notes.md``, existing
  ``etc/feature/F042/release`` tag.
- **Step 1 (composition test):** invoke ``extend_resolver`` flow —
  ``generate_extend_id``, ``classify`` (light), ``reopen``,
  ``record_extend``, ``complete_extend``, ``close``.
- **AC-007 (release-tag append-only):** the original
  ``etc/feature/F042/release`` tag's SHA is UNCHANGED; a new
  extension release tag exists at the post-close HEAD.
- **AC-008 (release-notes ## Extensions section):** the
  ``release-notes.md`` gains an ``## Extensions`` section; the
  pre-existing markdown content is preserved byte-equivalent in its
  prefix.
- **AC-009 (audit-log emission):** a single row with
  ``event_type=extend_dispatch`` is appended to
  ``.etc_sdlc/efficiency/turn-events.jsonl`` (simulated — the skill
  body emits this, not the helper); the row carries the 8 fields
  documented in design.md Data Model Entity 3.
- **AC-011 (legacy state.yaml):** a pre-F025 ``state.yaml`` without
  the ``extends:`` field gets the field created on first ``--extend``
  call; legacy fields (``id_history``, ``build``) preserved
  byte-equivalent.

The test exercises the integration boundary — it does NOT re-implement
helper functions. It calls ``extend_resolver.<fn>`` and
``release_notes.build`` directly via Python import. The audit-log
JSONL emission is performed inline by the test (the skill body does
this; per design.md the helper script itself does not).

Spec-contract caveat — git ref namespace collision (CONTRACT GAP):

    The F025 spec asserts both ``etc/feature/F<NNN>/release`` AND
    ``etc/feature/F<NNN>/release/<extend_id>`` must coexist as git
    refs (spec.md AC-007, design.md). Git's ref namespace is
    hierarchical — a leaf ref at ``foo/release`` makes
    ``foo/release/X`` unreachable (``cannot lock ref ...; foo/release
    exists; cannot create foo/release/X``). The main lifecycle test
    below uses an underscore-separated extension-tag scheme
    (``etc/feature/F<NNN>/release_<extend_id>``) so the lifecycle
    composition is exercisable; a separate xfail test documents the
    spec-literal contract gap so it surfaces in CI until F025's tag
    schema is reconciled.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Final

import pytest
import yaml

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import extend_resolver  # pyright: ignore[reportMissingImports]  # noqa: E402, I001  — sys.path inserted above
import release_notes  # pyright: ignore[reportMissingImports]  # noqa: E402, I001  — sys.path inserted above

_FIXTURE_FEATURE_ID = "F042"
_FIXTURE_SLUG = "fixture"
_FIXTURE_DIR_NAME = f"{_FIXTURE_FEATURE_ID}-{_FIXTURE_SLUG}"
_ORIGINAL_RELEASE_TAG = f"etc/feature/{_FIXTURE_FEATURE_ID}/release"
_LIGHT_PROBLEM = (
    "swap shadcn for radix in frontend/src/SettingsPage.tsx"
)
# Final-annotated tuple — module-level immutable; the lifecycle helpers
# accept any Sequence/list of agent role strings.
_DISPATCHED_AGENTS: Final[tuple[str, ...]] = ("frontend-developer",)


# ── helpers ─────────────────────────────────────────────────────────────


def _init_git_repo(repo_root: Path) -> None:
    """Initialize a fresh git repo at ``repo_root`` with an initial commit.

    Mirrors the pattern in tests/test_feature_id_full_flow.py so this
    integration test does not depend on cross-file fixtures.
    """
    subprocess.run(
        ["git", "init", "-q"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Test"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", "initial"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )


def _git_rev_parse(repo_root: Path, ref: str) -> str:
    """Return the SHA of ``ref`` in ``repo_root``."""
    result = subprocess.run(
        ["git", "rev-parse", ref],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _git_tag_list(repo_root: Path, pattern: str) -> list[str]:
    """Return matching git tag names under ``pattern``."""
    result = subprocess.run(
        ["git", "tag", "--list", pattern],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _git_commit_empty(repo_root: Path, message: str) -> None:
    """Create an empty commit (advances HEAD without touching the working tree)."""
    subprocess.run(
        ["git", "commit", "-q", "--allow-empty", "-m", message],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )


def _write_legacy_shipped_feature(etc_sdlc_root: Path) -> tuple[Path, dict[str, Any], str]:
    """Create a synthetic pre-F025 shipped feature dir.

    The state.yaml has NO ``extends:`` field — this exercises the
    AC-011 legacy-bootstrap path. The remaining feature-dir files
    mirror what /build's terminal close leaves behind: ``spec.md``,
    ``design.md``, ``verification.md``, ``release-notes.md``.

    Returns ``(shipped_dir, state_yaml_dict, release_notes_text)`` so
    callers can assert byte-equivalence on subsequent reads.
    """
    shipped_dir = etc_sdlc_root / "features" / "shipped" / _FIXTURE_DIR_NAME
    shipped_dir.mkdir(parents=True)

    state: dict[str, Any] = {
        "id_history": [
            {
                "form": "final",
                "value": _FIXTURE_FEATURE_ID,
                "written_at": "2026-05-01T00:00:00+00:00",
            }
        ],
        "spec_phase": {"completed_at": "2026-05-01T01:00:00+00:00"},
        "architect_phase": {"completed_at": "2026-05-01T02:00:00+00:00"},
        "build": {
            "completed_at": "2026-05-01T03:00:00+00:00",
            "phases_closed": 1,
        },
    }
    (shipped_dir / "state.yaml").write_text(yaml.safe_dump(state, sort_keys=False))
    (shipped_dir / "spec.md").write_text("# Spec F042\n\nFixture content.\n")
    (shipped_dir / "design.md").write_text("# Design F042\n\nFixture content.\n")
    (shipped_dir / "verification.md").write_text(
        "# Verification F042\n\nAll AC: PASS\n"
    )
    release_notes_text = (
        "# Release Notes — F042-fixture\n"
        "\n"
        "## Phases\n"
        "\n"
        "### Phase 0\n"
        "\n"
        "- Source: `build/phase-0/completion-report.md`\n"
        "- PRD: Fixture (F042)\n"
        "- Acceptance Criteria: 1 passed, 0 failed\n"
        "\n"
    )
    (shipped_dir / "release-notes.md").write_text(release_notes_text)

    return shipped_dir, state, release_notes_text


def _emit_extend_dispatch_row(
    *,
    audit_log_path: Path,
    feature_id: str,
    extend_id: str,
    triage: str,
    problem: str,
    dispatched_agents: tuple[str, ...],
    started_at: str,
) -> dict[str, Any]:
    """Simulate the skill body's audit-log emission (design.md Entity 3).

    Per AC-009 the helper script does NOT emit this row — the skill
    body (``skills/build/SKILL.md`` Step A8) does. The integration test
    simulates that emission inline so the lifecycle's 8-field schema
    can be asserted end-to-end.
    """
    audit_log_path.parent.mkdir(parents=True, exist_ok=True)
    row: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event_type": "extend_dispatch",
        "feature_id": feature_id,
        "extend_id": extend_id,
        "triage": triage,
        "problem_truncated_80": problem[:80],
        "dispatched_agents": list(dispatched_agents),
        "started_at": started_at,
    }
    with audit_log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")
    return row


# ── AC-007 + AC-009 + AC-011 (full lifecycle integration) ──────────────


class TestExtendLifecycleFullFlow:
    def test_should_complete_full_extend_lifecycle_when_light_triage_runs_end_to_end(
        self, tmp_path: Path
    ) -> None:
        # Arrange: fresh git repo + synthetic shipped F042 fixture.
        _init_git_repo(tmp_path)
        etc_sdlc_root = tmp_path / ".etc_sdlc"
        shipped_dir, legacy_state, original_release_notes = (
            _write_legacy_shipped_feature(etc_sdlc_root)
        )

        # Write the original release tag at the initial commit; capture
        # its SHA so we can later assert the tag was not retagged.
        subprocess.run(
            ["git", "tag", _ORIGINAL_RELEASE_TAG],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        original_release_sha = _git_rev_parse(tmp_path, _ORIGINAL_RELEASE_TAG)

        # Step 1: generate_extend_id (BR-006).
        extend_id = extend_resolver.generate_extend_id()
        assert len(extend_id) == 8
        assert all(ch in "0123456789abcdef" for ch in extend_id)

        # Step 2: classify (BR-002). "swap shadcn for radix in
        # frontend/src/SettingsPage.tsx" -> light (1 file path, no
        # architectural keywords).
        triage = extend_resolver.classify(_LIGHT_PROBLEM, shipped_dir)
        assert triage == "light"

        # Step 3: reopen (BR-004). shipped/ -> active/.
        active_dir = extend_resolver.reopen(shipped_dir, etc_sdlc_root)
        assert active_dir.is_dir()
        assert active_dir.parent.name == "active"
        assert not shipped_dir.exists()

        # Step 4: record_extend (BR-005). Append entry to extends; the
        # legacy state.yaml had NO extends field — AC-011 requires this
        # call to create it.
        extend_resolver.record_extend(
            target_dir=active_dir,
            extend_id=extend_id,
            problem=_LIGHT_PROBLEM,
            triage=triage,
            dispatched_agents=list(_DISPATCHED_AGENTS),
        )

        # AC-011 assertion 1: extends field was created.
        post_record_state: dict[str, Any] = yaml.safe_load(
            (active_dir / "state.yaml").read_text()
        )
        assert "extends" in post_record_state, (
            "AC-011: extends field was not created on legacy state.yaml"
        )
        assert isinstance(post_record_state["extends"], list)
        assert len(post_record_state["extends"]) == 1

        # AC-011 assertion 2: legacy fields preserved byte-equivalent.
        for legacy_key in ("id_history", "spec_phase", "architect_phase", "build"):
            assert post_record_state[legacy_key] == legacy_state[legacy_key], (
                f"AC-011: legacy field {legacy_key} mutated by record_extend"
            )

        # Step 5: simulate the skill body's audit-log emission (AC-009).
        # The helper script itself does not emit this — design.md is
        # explicit that the skill body does. We simulate inline.
        audit_log_path = etc_sdlc_root / "efficiency" / "turn-events.jsonl"
        started_at = post_record_state["extends"][0]["started_at"]
        emitted_row = _emit_extend_dispatch_row(
            audit_log_path=audit_log_path,
            feature_id=_FIXTURE_FEATURE_ID,
            extend_id=extend_id,
            triage=triage,
            problem=_LIGHT_PROBLEM,
            dispatched_agents=_DISPATCHED_AGENTS,
            started_at=started_at,
        )

        # Step 6: simulate the dispatched-work commit (skill body's
        # Step A9 work would land changes; we model it with an empty
        # commit so the post-close release-tag points somewhere
        # different from the original release tag).
        _git_commit_empty(tmp_path, "simulated extend dispatch work")

        # Step 7: complete_extend (BR-010). Set completed_at +
        # release_tag.
        #
        # NOTE (contract gap): the F025 spec mandates the release tag
        # shape ``etc/feature/F<NNN>/release/<extend_id>`` — which is
        # impossible alongside ``etc/feature/F<NNN>/release`` because
        # git ref namespaces are hierarchical (a leaf ref at
        # ``foo/release`` makes ``foo/release/X`` unreachable). We use
        # an underscore-separated scheme here so the lifecycle
        # composition is exercisable; the xfail test below documents
        # the spec-literal gap.
        release_tag = (
            f"etc/feature/{_FIXTURE_FEATURE_ID}/release_{extend_id}"
        )
        extend_resolver.complete_extend(
            target_dir=active_dir,
            extend_id=extend_id,
            release_tag=release_tag,
        )

        # Step 8: simulate the skill body's release-tag write (BR-007).
        # The helper does not write tags — that is the skill body's
        # job (mirrors how feature_id.py leaves tag writes to the skill).
        subprocess.run(
            ["git", "tag", release_tag],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )

        # Step 9: simulate the skill body's release-notes update
        # (BR-008). The release_notes._render_extensions_section helper
        # renders the current state.yaml's extends list into an
        # ## Extensions section. The original release-notes prefix is
        # preserved verbatim per AC-008 (append-only).
        rendered_extensions = release_notes._render_extensions_section(
            release_notes._collect_extends(active_dir)
        )
        updated_release_notes = original_release_notes + rendered_extensions
        (active_dir / "release-notes.md").write_text(updated_release_notes)

        # Step 10: close (BR-010). active/ -> shipped/.
        final_shipped_dir = extend_resolver.close(active_dir, etc_sdlc_root)
        assert final_shipped_dir.is_dir()
        assert final_shipped_dir.parent.name == "shipped"
        assert not active_dir.exists()

        # ── Assertions ──────────────────────────────────────────────

        # AC-005 / AC-007 / AC-011: state.yaml.extends has one entry
        # with non-null completed_at.
        final_state: dict[str, Any] = yaml.safe_load(
            (final_shipped_dir / "state.yaml").read_text()
        )
        extends_list = final_state["extends"]
        assert len(extends_list) == 1
        entry = extends_list[0]
        assert entry["extend_id"] == extend_id
        assert entry["triage"] == "light"
        assert entry["problem"] == _LIGHT_PROBLEM
        assert entry["dispatched_agents"] == list(_DISPATCHED_AGENTS)
        assert entry["completed_at"] is not None, (
            "AC-005: completed_at remained null after complete_extend"
        )
        assert entry["release_tag"] == release_tag

        # AC-007: original release tag still exists at its ORIGINAL SHA.
        post_close_release_sha = _git_rev_parse(tmp_path, _ORIGINAL_RELEASE_TAG)
        assert post_close_release_sha == original_release_sha, (
            f"AC-007: {_ORIGINAL_RELEASE_TAG} SHA mutated: "
            f"{original_release_sha} -> {post_close_release_sha}"
        )

        # AC-007: extension release tag exists and is distinct.
        all_release_tags = _git_tag_list(
            tmp_path, f"etc/feature/{_FIXTURE_FEATURE_ID}/*"
        )
        assert _ORIGINAL_RELEASE_TAG in all_release_tags, (
            f"AC-007: original release tag missing from "
            f"git tag --list: {all_release_tags}"
        )
        assert release_tag in all_release_tags, (
            f"AC-007: extension release tag {release_tag} not present "
            f"in {all_release_tags}"
        )
        extension_release_sha = _git_rev_parse(tmp_path, release_tag)
        assert extension_release_sha != original_release_sha, (
            "AC-007: extension release tag points at the original "
            "SHA — should be distinct (post-dispatch HEAD)."
        )

        # AC-008: release-notes.md has an ## Extensions section
        # appended; the pre-existing content is byte-equivalent at the
        # prefix.
        final_release_notes_text = (
            final_shipped_dir / "release-notes.md"
        ).read_text()
        assert final_release_notes_text.startswith(original_release_notes), (
            "AC-008: original release-notes content not preserved "
            "byte-equivalent at the prefix"
        )
        assert "## Extensions" in final_release_notes_text, (
            "AC-008: release-notes.md missing ## Extensions section"
        )
        assert f"### Extension {extend_id}" in final_release_notes_text, (
            "AC-008: release-notes.md missing the per-extend sub-section"
        )

        # AC-009: audit log contains exactly one extend_dispatch row.
        audit_lines = audit_log_path.read_text().splitlines()
        dispatch_rows = [
            json.loads(line)
            for line in audit_lines
            if line.strip()
        ]
        assert len(dispatch_rows) == 1, (
            f"AC-009: expected exactly one audit row; got "
            f"{len(dispatch_rows)}: {dispatch_rows!r}"
        )
        row = dispatch_rows[0]
        assert row["event_type"] == "extend_dispatch"

        # AC-009: all 8 fields from design.md Entity 3 present.
        expected_fields = {
            "ts",
            "event_type",
            "feature_id",
            "extend_id",
            "triage",
            "problem_truncated_80",
            "dispatched_agents",
            "started_at",
        }
        assert set(row.keys()) == expected_fields, (
            f"AC-009: audit-row field set mismatch; expected "
            f"{expected_fields}, got {set(row.keys())}"
        )
        assert row["feature_id"] == _FIXTURE_FEATURE_ID
        assert row["extend_id"] == extend_id
        assert row["triage"] == "light"
        assert row["problem_truncated_80"] == _LIGHT_PROBLEM[:80]
        assert row["dispatched_agents"] == list(_DISPATCHED_AGENTS)
        assert row["started_at"] == started_at
        # Sanity check: the emit helper returned the row we wrote.
        assert row == emitted_row


# ── Contract gap: spec-literal release-tag shape ────────────────────────


class TestSpecLiteralReleaseTagShape:
    """Document the F025 spec/git-ref-namespace contract gap.

    The F025 spec (spec.md BR-007 + AC-007, design.md Entity 1) states
    the extension release tag MUST be
    ``etc/feature/F<NNN>/release/<extend_id>`` AND coexist with the
    original ``etc/feature/F<NNN>/release``. Git's ref namespace is
    hierarchical; the two cannot coexist as refs. This xfail captures
    that gap as a test artifact so it surfaces in CI until the F025
    tag schema is reconciled (likely via underscore separator, double
    colon, or a different naming scheme at the schema level).
    """

    @pytest.mark.xfail(
        reason=(
            "F025 contract gap: git ref namespace cannot hold both "
            "etc/feature/F042/release and etc/feature/F042/release/<id>. "
            "Tracking: surface to architect for F025 tag-schema "
            "reconciliation before release."
        ),
        strict=True,
    )
    def test_should_coexist_etc_feature_release_leaf_and_subscript_when_extend_closes(
        self, tmp_path: Path
    ) -> None:
        _init_git_repo(tmp_path)
        # Write the leaf tag first.
        subprocess.run(
            ["git", "tag", _ORIGINAL_RELEASE_TAG],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        # Attempt the spec-literal subscript tag. This will raise
        # CalledProcessError because git rejects the namespace collision.
        extend_id = extend_resolver.generate_extend_id()
        spec_literal_tag = (
            f"etc/feature/{_FIXTURE_FEATURE_ID}/release/{extend_id}"
        )
        subprocess.run(
            ["git", "tag", spec_literal_tag],
            cwd=tmp_path,
            check=True,
            capture_output=True,
        )
        # Unreached on the strict-xfail path; if git's behavior ever
        # changes to allow the collision, this assertion documents the
        # spec contract that should then hold.
        tags = _git_tag_list(
            tmp_path, f"etc/feature/{_FIXTURE_FEATURE_ID}/*"
        )
        assert _ORIGINAL_RELEASE_TAG in tags
        assert spec_literal_tag in tags
