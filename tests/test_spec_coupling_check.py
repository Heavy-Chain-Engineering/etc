"""Tests for scripts/spec_coupling_check.py (F015 / Step 7.5).

The detector scans spec.md (and design.md) for scope-change markers
anchored to AC/BR/ADR references and checks coverage in decisions/
or docs/adrs/. These tests use a synthetic feature directory under
pytest's tmp_path so the gate runs against controlled inputs.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

SCRIPT = Path(__file__).parent.parent / "scripts" / "spec_coupling_check.py"


def _run(feature_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCRIPT), str(feature_dir)],
        capture_output=True,
        text=True,
        timeout=15,
    )


def _make_feature(
    tmp_path: Path,
    feature_id: str = "F999",
    spec_body: str = "",
    design_body: str | None = None,
    decisions: dict[str, str] | None = None,
    adrs: dict[str, str] | None = None,
) -> Path:
    """Build a fake feature directory + optional ADR layout under tmp_path.

    Returns the feature_dir path. No git tag is created — the detector
    falls back to "scan whole file" when the tag is missing.
    """
    repo = tmp_path
    # Init a git repo at the fixture root so repo_root_from() resolves to
    # `repo` and finds docs/adrs/ correctly. The detector's git-tag lookup
    # gracefully degrades when the tag is missing — that's fine for these
    # tests; we just need the repo root.
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    feature_dir = repo / ".etc_sdlc" / "features" / f"{feature_id}-test-feature"
    feature_dir.mkdir(parents=True)
    (feature_dir / "spec.md").write_text(spec_body, encoding="utf-8")
    if design_body is not None:
        (feature_dir / "design.md").write_text(design_body, encoding="utf-8")
    if decisions:
        (feature_dir / "decisions").mkdir()
        for name, content in decisions.items():
            (feature_dir / "decisions" / name).write_text(content, encoding="utf-8")
    if adrs:
        (repo / "docs" / "adrs").mkdir(parents=True)
        for name, content in adrs.items():
            (repo / "docs" / "adrs" / name).write_text(content, encoding="utf-8")
    return feature_dir


class TestNoFindings:
    """When the spec has no markers, exit 0 with empty output."""

    def test_spec_with_no_markers_exits_zero(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n## Acceptance Criteria\n\n- AC-01: Implement widgets.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 0


class TestMarkerDetection:
    """AC-02: each marker is recognized when anchored."""

    def test_deferred_marker_with_AC_anchor_triggers_finding(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-12: Widget normalizer **deferred** to F999.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "AC-12" in result.stdout

    def test_removed_marker_with_BR_anchor_triggers_finding(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- BR-007: counter has been **removed**.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "BR-007" in result.stdout

    def test_scope_narrowed_with_anchor_triggers(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-05: scope narrowed; only handles uppercase.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2


class TestAnchorRequirement:
    """AC-03: marker without anchor is excluded (false-positive reduction)."""

    def test_marker_without_anchor_is_excluded(self, tmp_path: Path) -> None:
        """Plain narrative use of 'deferred' (no AC/BR/ADR reference, no
        backtick) MUST NOT trigger a finding."""
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\nLast quarter we deferred this conversation. Moving on.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 0

    def test_marker_with_backtick_phrase_anchor_triggers(self, tmp_path: Path) -> None:
        """A marker paired with a backticked quoted phrase counts as anchored."""
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\nThe `operating_locations` field is **deferred** to a follow-up.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2


class TestCodeBlockExclusion:
    """AC-04: markers inside fenced code blocks are excluded."""

    def test_marker_inside_code_block_is_excluded(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body=(
                "# Feature\n\n"
                "Here's a code example:\n\n"
                "```\n"
                "# AC-12 explicitly excluded from this snippet\n"
                "```\n\n"
                "Implementation continues.\n"
            ),
        )
        result = _run(feature_dir)
        assert result.returncode == 0


class TestOutOfScopeHeaderExclusion:
    """AC-05: 'Out of Scope' / 'Not in Scope' HEADER lines are not findings."""

    def test_out_of_scope_header_alone_is_not_a_finding(self, tmp_path: Path) -> None:
        """The header text contains 'out of scope' but is just a section
        marker — not a scope change."""
        feature_dir = _make_feature(
            tmp_path,
            spec_body=(
                "# Feature\n\n"
                "## Out of Scope\n\n"
                "- Some boundary statement that doesn't reference an AC.\n"
            ),
        )
        result = _run(feature_dir)
        assert result.returncode == 0


class TestCoverageByDecisionMemo:
    """AC-07: a finding with a decision memo referencing its AC is covered."""

    def test_finding_covered_by_decision_memo_passes(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-12: Normalizer **deferred** to F999.\n",
            decisions={
                "ac-12-decision.md": (
                    "# Decision: defer AC-12\n\n"
                    "AC-12 was deferred because backend research revealed no real "
                    "user demand. Options considered: (a) ship, (b) defer, (c) drop.\n"
                ),
            },
        )
        result = _run(feature_dir)
        assert result.returncode == 0

    def test_finding_uncovered_when_memo_does_not_reference_AC(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-12: Normalizer **deferred** to F999.\n",
            decisions={
                "unrelated.md": "# Decision: something else entirely.\n\nNo AC reference here.\n",
            },
        )
        result = _run(feature_dir)
        assert result.returncode == 2


class TestCoverageByADRAppendix:
    """AC-08: a finding covered by ADR with required phrase."""

    def test_finding_covered_by_adr_with_scope_clarification(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- BR-007: ETL backfill **scope-narrowed** to addresses only.\n",
            adrs={
                "F999-001.md": (
                    "# ADR-F999-001: ETL backfill scope\n\n"
                    "## Scope clarification\n\n"
                    "BR-007 narrowed: only address-shaped entries are backfilled.\n"
                ),
            },
        )
        result = _run(feature_dir)
        assert result.returncode == 0

    def test_adr_without_required_phrase_does_not_cover(self, tmp_path: Path) -> None:
        """ADR mentions the BR but lacks 'scope clarification' / 'appendix'
        / 'scope-narrowed' — does NOT count as coverage."""
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- BR-007: ETL backfill **scope-narrowed** to addresses only.\n",
            adrs={
                "F999-001.md": (
                    "# ADR-F999-001: ETL backfill\n\n"
                    "BR-007 is a thing.\n"
                ),
            },
        )
        result = _run(feature_dir)
        assert result.returncode == 2


class TestBlockReport:
    """AC-09: stdout on block contains file:line + remediation hints."""

    def test_block_report_includes_file_line(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n\n- AC-12: Normalizer **deferred** to F999.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "spec.md:" in result.stdout

    def test_block_report_lists_remediation_options(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-12: Normalizer **deferred**.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "Decision memo" in result.stdout
        assert "ADR appendix" in result.stdout
        assert "--skip-spec-coupling-check" in result.stdout


class TestUsage:
    def test_missing_arg_exits_one(self) -> None:
        result = subprocess.run(
            ["python3", str(SCRIPT)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 1

    def test_nonexistent_feature_dir_exits_one(self, tmp_path: Path) -> None:
        result = _run(tmp_path / "does-not-exist")
        assert result.returncode == 1


class TestDesignMdScanned:
    """design.md is also scanned if present."""

    def test_design_md_marker_triggers_finding(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-01: ship widgets.\n",
            design_body="# Architecture\n\n- BR-007: caching layer **removed**.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "design.md:" in result.stdout


class TestRelativeFeatureDirPath:
    """#38 regression: the gate must not crash when invoked with a feature_dir
    passed as a path relative to the repo root.

    `repo_root_from()` resolves to an absolute path, but a memo discovered
    under a relative `feature_dir` stays relative. `memo.relative_to(repo_root)`
    then raises ValueError (mixed absolute/relative operands), crashing the
    gate with an uncaught traceback. Every memo-cleared build that passed a
    relative feature path tripped this. The display-path computation must be
    robust to mixed path kinds.
    """

    def _run_relative(self, repo: Path, rel_feature_dir: str):
        return subprocess.run(
            ["python3", str(SCRIPT), rel_feature_dir],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=15,
        )

    def test_memo_covered_finding_with_relative_feature_dir_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-12: Normalizer **deferred** to F999.\n",
            decisions={
                "ac-12-decision.md": (
                    "# Decision: defer AC-12\n\n"
                    "AC-12 was deferred because backend research revealed no real "
                    "user demand. Options considered: (a) ship, (b) defer, (c) drop.\n"
                ),
            },
        )
        rel = str(feature_dir.relative_to(tmp_path))
        result = self._run_relative(tmp_path, rel)
        # The memo covers AC-12, so the gate passes (exit 0) — but only if the
        # relative_to() display computation does not raise.
        assert "Traceback" not in result.stderr, result.stderr
        assert "ValueError" not in result.stderr, result.stderr
        assert result.returncode == 0, (result.returncode, result.stderr)

    def test_adr_covered_finding_with_relative_feature_dir_does_not_crash(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- BR-007: ETL backfill **scope-narrowed** to addresses only.\n",
            adrs={
                "F999-001.md": (
                    "# ADR-F999-001: ETL backfill scope\n\n"
                    "## Scope clarification\n\n"
                    "BR-007 narrowed: only address-shaped entries are backfilled.\n"
                ),
            },
        )
        rel = str(feature_dir.relative_to(tmp_path))
        result = self._run_relative(tmp_path, rel)
        assert "Traceback" not in result.stderr, result.stderr
        assert "ValueError" not in result.stderr, result.stderr
        assert result.returncode == 0, (result.returncode, result.stderr)
