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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        timeout=10,
        capture_output=True,
        text=True,
    )


def _make_feature(
    tmp_path: Path,
    feature_id: str = "F999",
    spec_body: str = "",
    design_body: str | None = None,
    decisions: dict[str, str] | None = None,
    adrs: dict[str, str] | None = None,
    baseline_spec: str | None = None,
    baseline_design: str | None = None,
) -> Path:
    """Build a fake feature directory + optional ADR layout under tmp_path.

    Returns the feature_dir path.

    Baseline semantics: the detector only scans lines that are NEW relative
    to a usable git baseline (the spec content committed and tagged at
    `etc/feature/<id>/spec`). When `baseline_spec` is provided, that content
    is committed and the leaf `spec` tag is laid down BEFORE `spec_body` is
    written on top — so `spec_body`'s added lines are the scan surface and
    markers in them fire. When `baseline_spec` is None there is NO usable
    baseline (the tag is absent, and in the real harness the feature dir is
    gitignored so the content is untracked anyway) — the detector must then
    PASS CLEAN, scanning nothing.
    """
    repo = tmp_path
    # Init a git repo at the fixture root so repo_root_from() resolves to
    # `repo` and finds docs/adrs/ correctly.
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    feature_dir = repo / ".etc_sdlc" / "features" / f"{feature_id}-test-feature"
    feature_dir.mkdir(parents=True)
    spec_path = feature_dir / "spec.md"

    if baseline_spec is not None or baseline_design is not None:
        # Lay down a real, tracked baseline + leaf tag the detector can diff
        # against. Force-add because the harness gitignores feature dirs; the
        # fixture commits the baseline so `git show <tag>:<rel>` succeeds.
        rel_paths: list[str] = []
        if baseline_spec is not None:
            spec_path.write_text(baseline_spec, encoding="utf-8")
            rel_paths.append(str(spec_path.relative_to(repo)))
        if baseline_design is not None:
            design_path = feature_dir / "design.md"
            design_path.write_text(baseline_design, encoding="utf-8")
            rel_paths.append(str(design_path.relative_to(repo)))
        _git(repo, "add", "-f", *rel_paths)
        _git(repo, "commit", "-q", "-m", "baseline spec")
        _git(repo, "tag", f"etc/feature/{feature_id}/spec")

    spec_path.write_text(spec_body, encoding="utf-8")
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


def _make_dated_feature(
    tmp_path: Path,
    feature_id: str,
    spec_body: str,
    baseline_spec: str,
) -> Path:
    """Build a date-form feature whose directory NAME IS the feature_id.

    Date-form ids (``F-YYYY-MM-DD-<slug>``) carry no separate ``-<slug>``
    suffix — the directory name itself is the id, and the baseline tag is
    ``etc/feature/<full-id>/spec``. This mirrors the real layout the gate
    must support after the F023 ID-scheme revision.
    """
    repo = tmp_path
    subprocess.run(["git", "init", "-q", str(repo)], check=True, timeout=10)
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test")
    feature_dir = repo / ".etc_sdlc" / "features" / feature_id
    feature_dir.mkdir(parents=True)
    spec_path = feature_dir / "spec.md"

    spec_path.write_text(baseline_spec, encoding="utf-8")
    _git(repo, "add", "-f", str(spec_path.relative_to(repo)))
    _git(repo, "commit", "-q", "-m", "baseline spec")
    _git(repo, "tag", f"etc/feature/{feature_id}/spec")

    spec_path.write_text(spec_body, encoding="utf-8")
    return feature_dir


class TestDateFormFeatureId:
    """The ID scheme moved to ``F-YYYY-MM-DD-<slug>``. The F015 baseline-tag
    lookup must fire for date-form features (the gate previously parsed only
    legacy ``F<NNN>`` ids → the tag ``etc/feature/<id>/spec`` was never built →
    the gate silently no-opped for every current feature)."""

    def test_should_find_baseline_tag_when_feature_is_date_form(
        self, tmp_path: Path
    ) -> None:
        feature_dir = _make_dated_feature(
            tmp_path,
            feature_id="F-2026-06-02-build-review-agent-gate",
            baseline_spec="# Feature\n",
            spec_body="# Feature\n\n- AC-12: Widget normalizer **deferred** to a follow-up.\n",
        )
        result = _run(feature_dir)
        # The baseline tag IS found → the new marker line is the scan surface
        # → the uncovered finding fires (exit 2). A legacy-only parser would
        # never build the tag, scan nothing, and pass clean (exit 0).
        assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
        assert "AC-12" in result.stdout

    def test_should_not_fire_when_marker_present_in_date_form_baseline(
        self, tmp_path: Path
    ) -> None:
        """Control: a marker already present in the date-form baseline is not a
        NEW scope change. Proves the baseline diff is real, not a whole-file
        scan that would over-fire."""
        unchanged = "# Feature\n\n- AC-12: rollup metric **deferred** to a follow-up.\n"
        feature_dir = _make_dated_feature(
            tmp_path,
            feature_id="F-2026-06-02-build-review-agent-gate",
            baseline_spec=unchanged,
            spec_body=unchanged + "\n- AC-14: add a new chart (no scope change).\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)


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
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
            spec_body="# Feature\n\n- BR-007: counter has been **removed**.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "BR-007" in result.stdout

    def test_scope_narrowed_with_anchor_triggers(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
            spec_body="# Feature\n\n\n- AC-12: Normalizer **deferred** to F999.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 2
        assert "spec.md:" in result.stdout

    def test_block_report_lists_remediation_options(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
            baseline_design="# Architecture\n",
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
            baseline_spec="# Feature\n",
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
            baseline_spec="# Feature\n",
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


class TestNoBaselinePassesClean:
    """#46 regression: a fresh spec with NO usable git baseline must PASS CLEAN
    instead of over-firing on every marker in the whole file.

    Real-world mechanism (verified): `/spec` writes the LEAF tag
    `etc/feature/F<NNN>/spec` (not `…/spec/done`), and the feature dir is
    gitignored so spec.md is untracked. The detector therefore has no prior
    spec version to diff against — there is nothing to "couple" a scope change
    to. Treating the whole spec as "added" blocked the release tag on every
    fresh build (6th occurrence). With no usable baseline the gate must scan
    nothing and exit 0.
    """

    def test_fresh_spec_with_markers_but_no_baseline_passes_clean(
        self, tmp_path: Path
    ) -> None:
        # Markers galore, anchored — but no baseline tag/commit exists.
        feature_dir = _make_feature(
            tmp_path,
            spec_body=(
                "# Feature\n\n"
                "- AC-12: Widget normalizer **deferred** to a follow-up.\n"
                "- BR-007: legacy counter **removed**.\n"
                "- AC-05: scope narrowed; only uppercase handled.\n"
            ),
        )
        result = _run(feature_dir)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
        assert "COUPLING GATE FAILED" not in result.stdout

    def test_no_baseline_does_not_warn_about_missing_tag(
        self, tmp_path: Path
    ) -> None:
        """The old code emitted a 'tag not found, scanning entire file'
        warning and then over-fired. No usable baseline is the NORMAL state
        for a fresh spec, not a warning condition."""
        feature_dir = _make_feature(
            tmp_path,
            spec_body="# Feature\n\n- AC-12: Normalizer **deferred** to F999.\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 0
        assert "Scanning entire" not in result.stderr


class TestGenuineBaselineStillFires:
    """#46: the legitimate behaviour must survive. When a real prior baseline
    DOES exist (a re-spec) and the new spec gained a scope-change marker that
    was NOT in the baseline, the gate must still fire (exit 2)."""

    def test_new_marker_since_baseline_fires(self, tmp_path: Path) -> None:
        feature_dir = _make_feature(
            tmp_path,
            baseline_spec="# Feature\n\n- AC-12: ship the widget normalizer.\n",
            spec_body=(
                "# Feature\n\n"
                "- AC-12: ship the widget normalizer.\n"
                "- AC-13: rollup metric **deferred** to a follow-up.\n"
            ),
        )
        result = _run(feature_dir)
        assert result.returncode == 2, (result.returncode, result.stdout, result.stderr)
        assert "AC-13" in result.stdout

    def test_marker_present_in_baseline_does_not_fire(self, tmp_path: Path) -> None:
        """A marker that already existed in the baseline is not a NEW scope
        change — it must not re-fire on an unrelated re-spec."""
        unchanged = "# Feature\n\n- AC-12: rollup metric **deferred** to a follow-up.\n"
        feature_dir = _make_feature(
            tmp_path,
            baseline_spec=unchanged,
            spec_body=unchanged + "\n- AC-14: add a new chart (no scope change).\n",
        )
        result = _run(feature_dir)
        assert result.returncode == 0, (result.returncode, result.stdout, result.stderr)
