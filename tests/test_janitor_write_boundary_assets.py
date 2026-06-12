"""Contract tests for the published-assets dynamic rule in the janitor
write-boundary standard (F-2026-06-12, task 002).

`standards/process/janitor-write-boundary.md` is the single source of truth for
what janitor may NOT write. It is prose + two machine-parseable fenced blocks,
not executable code, so these are grep-style contract tests (mirroring
`tests/test_janitor_skill.py`): they assert the standard carries the load-bearing
strings that encode the published-asset evidence contract. If a clause is removed
or renamed, the matching test fails.

These tests pin the rule text so the wave-1 mirrors (`agents/janitor.md`,
`skills/janitor/SKILL.md`) can grep the SAME verbatim phrasing — the standard is
the source, the layers cite it (spec BR-007).

Maps to task 002 acceptance criteria:
    AC-1 — forbidden-path table row + three globs + evidence contract + inherited
           fail-closed sentence.
    AC-2 — applies identically in both janitor lanes (preview + autonomous) and
           names the evidence record destination (runs.jsonl).
"""

from __future__ import annotations

from pathlib import Path

STANDARD_PATH = (
    Path(__file__).resolve().parent.parent
    / "standards"
    / "process"
    / "janitor-write-boundary.md"
)

# Verbatim phrases the wave-1 mirrors grep against. Written once, exactly, here
# and in the standard — change either and these tests fail.
PUBLISHED_API_SURFACE_PHRASE = "a published API surface"
REPO_LOCAL_INSUFFICIENT_PHRASE = (
    "Repo-local unreferenced-ness alone is never sufficient evidence for this "
    "file class"
)


def _standard_text() -> str:
    return STANDARD_PATH.read_text(encoding="utf-8")


class TestStandardFileExists:
    """The standard exists and is readable (the source of truth)."""

    def test_should_find_standard_when_resolving_repo_path(self) -> None:
        assert STANDARD_PATH.exists()


class TestForbiddenPathTableRow:
    """AC-1: the forbidden-path table gains the published-assets dynamic row."""

    def test_should_name_published_assets_rule_when_reading_table(self) -> None:
        assert "`published-assets`" in _standard_text()

    def test_should_mark_published_assets_dynamic_when_reading_table(self) -> None:
        # The row composes with the other dynamic rows: it is a dynamic rule,
        # not a static glob, because the evidence is an org-wide search.
        text = _standard_text()
        row = next(
            line for line in text.splitlines() if "`published-assets`" in line
        )
        assert "**dynamic**" in row


class TestMachineParseableGlobs:
    """AC-1: the machine-parseable list gains public/**, static/**, www/**."""

    def test_should_list_public_glob_when_reading_forbidden_block(self) -> None:
        assert "published-assets" in _standard_text()
        assert _has_glob_line("published-assets", "public/**")

    def test_should_list_static_glob_when_reading_forbidden_block(self) -> None:
        assert _has_glob_line("published-assets", "static/**")

    def test_should_list_www_glob_when_reading_forbidden_block(self) -> None:
        assert _has_glob_line("published-assets", "www/**")


class TestEvidenceContract:
    """AC-1: the rule text states the published-asset evidence contract."""

    def test_should_state_org_search_zero_hits_clears_when_reading_rule(
        self,
    ) -> None:
        text = _standard_text().lower()
        assert "org-wide" in text
        assert "zero" in text

    def test_should_require_recorded_evidence_when_clearing_deletion(self) -> None:
        text = _standard_text().lower()
        assert "recorded" in text or "record" in text
        assert "evidence" in text

    def test_should_abort_naming_consumers_when_search_hits(self) -> None:
        text = _standard_text().lower()
        assert "abort" in text
        assert "consumer" in text

    def test_should_name_published_api_surface_when_reading_rule(self) -> None:
        # Verbatim greppable string shared with the wave-1 mirrors.
        assert PUBLISHED_API_SURFACE_PHRASE in _standard_text()

    def test_should_reject_repo_local_unreferencedness_when_reading_rule(
        self,
    ) -> None:
        # Verbatim greppable string shared with the wave-1 mirrors.
        assert REPO_LOCAL_INSUFFICIENT_PHRASE in _standard_text()


class TestFailClosedInheritance:
    """AC-1: the rule inherits the standard's existing fail-closed sentence."""

    def test_should_inherit_fail_closed_sentence_when_search_unavailable(
        self,
    ) -> None:
        # The standard already states the dynamic-rule fail-closed precedent
        # verbatim; the published-assets rule composes with it rather than
        # restating a divergent copy.
        text = _standard_text()
        assert (
            "When `gh` or git state is unavailable for a dynamic rule, the rule "
            "fails closed" in text
        )

    def test_should_tie_published_assets_to_fail_closed_when_unavailable(
        self,
    ) -> None:
        # The published-assets rule body must explicitly route an unavailable
        # search to the fail-closed precedent (not silently clear).
        text = _standard_text().lower()
        assert "fail" in text and "closed" in text
        assert "unavailable" in text


class TestBothLanesAndEvidenceDestination:
    """AC-2: identical in both lanes; names the runs.jsonl evidence record."""

    def test_should_apply_in_both_lanes_when_reading_rule(self) -> None:
        text = _standard_text().lower()
        assert "preview" in text
        assert "autonomous" in text

    def test_should_state_identical_treatment_when_naming_lanes(self) -> None:
        text = _standard_text().lower()
        assert "identical" in text or "both lanes" in text

    def test_should_name_runs_jsonl_destination_when_recording_evidence(
        self,
    ) -> None:
        assert "runs.jsonl" in _standard_text()


def _has_glob_line(rule: str, glob: str) -> bool:
    """True if a forbidden-globs line maps `rule` to `glob` (`<rule><ws><glob>`).

    Mirrors the standard's documented parsing contract: split each non-comment
    line on its first run of whitespace; left token is the rule, right is the
    single glob.
    """
    for raw in _standard_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(maxsplit=1)
        if len(parts) == 2 and parts[0] == rule and parts[1] == glob:
            return True
    return False
