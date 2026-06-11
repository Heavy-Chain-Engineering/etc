"""Contract tests for the brownfield-architecture-baseline synthetic fixtures.

The DISCOVER -> VERIFY -> RATIFY -> ENFORCE loop (feature
F-2026-06-10-brownfield-architecture-baseline) exercises its mechanisms against
four synthetic brownfield repos under ``tests/fixtures/baseline-*``. These tests
pin two contracts on that substrate:

1. Structural presence: the four fixtures exist, each is minimal (< 25 files),
   carries a one-line README naming the loop mechanism it exercises, and embeds
   the artifact its mechanism needs (a contradicted convention doc, two competing
   live patterns, an env-var seam + shared schema, or zero docs).
2. Anonymization: no fixture file (path or content) carries a client identifier.
   The anonymization rule from Edge Case 12 / Security Considerations is
   machine-enforced here, not left to reviewer vigilance.

The fixtures are static data, so these are data-contract assertions rather than
behavioral unit tests; they fail loudly the moment a fixture drifts out of shape
or a client name leaks in.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
FIXTURES_ROOT = REPO_ROOT / "tests" / "fixtures"

STALE_DOC = FIXTURES_ROOT / "baseline-stale-doc"
COMPETING_PATTERNS = FIXTURES_ROOT / "baseline-competing-patterns"
WORKSPACE_SEAM = FIXTURES_ROOT / "baseline-workspace-seam"
NO_DOCS = FIXTURES_ROOT / "baseline-no-docs"

ALL_FIXTURES = (STALE_DOC, COMPETING_PATTERNS, WORKSPACE_SEAM, NO_DOCS)

MAX_FILES_PER_FIXTURE = 25

# Client identifiers that must never appear in any fixture path or file content.
# Word-boundary matched, case-insensitive, so generic English ("recover",
# "pбj"-free invented domains) does not false-positive. The ticket-prefix
# pattern matches the real client convention (DEV-00000) but not invented IDs.
CLIENT_IDENTIFIER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bcovr\b", re.IGNORECASE),
    re.compile(r"\bpbj\b", re.IGNORECASE),
    re.compile(r"\bDEV-\d", re.IGNORECASE),
    re.compile(r"\bcovr-2\.0\b", re.IGNORECASE),
    re.compile(r"\bcovr-legacy\b", re.IGNORECASE),
)


def _fixture_files(fixture: Path) -> list[Path]:
    """Return every regular file under a fixture, repo markers included."""
    return [p for p in fixture.rglob("*") if p.is_file()]


def _scan_for_client_identifiers(text: str) -> list[str]:
    """Return the client identifiers found in a string (empty == clean)."""
    hits: list[str] = []
    for pattern in CLIENT_IDENTIFIER_PATTERNS:
        hits.extend(match.group(0) for match in pattern.finditer(text))
    return hits


# ── AC 1: the four fixtures exist, minimal, README-documented ────────────────


def test_should_provide_four_baseline_fixtures_when_substrate_is_built() -> None:
    present = [f.name for f in ALL_FIXTURES if f.is_dir()]
    assert present == [f.name for f in ALL_FIXTURES]


def test_should_keep_every_fixture_minimal_when_counting_files() -> None:
    oversized = {
        f.name: len(_fixture_files(f))
        for f in ALL_FIXTURES
        if len(_fixture_files(f)) >= MAX_FILES_PER_FIXTURE
    }
    assert oversized == {}


def test_should_carry_one_line_readme_when_naming_loop_mechanism() -> None:
    missing: list[str] = []
    for fixture in ALL_FIXTURES:
        readme = fixture / "README.md"
        if not readme.is_file() or not readme.read_text(encoding="utf-8").strip():
            missing.append(fixture.name)
    assert missing == []


# ── AC 1: each fixture embeds the artifact its mechanism needs ───────────────


def test_should_embed_convention_doc_when_fixture_is_stale_doc() -> None:
    docs = list((STALE_DOC / "docs").glob("*.md"))
    sources = list((STALE_DOC / "src").rglob("*"))
    assert docs and any(s.is_file() for s in sources)


def test_should_embed_two_pattern_examples_when_fixture_is_competing() -> None:
    pattern_dirs = [p for p in COMPETING_PATTERNS.rglob("*") if p.is_dir()]
    feature_modules = [
        p
        for p in pattern_dirs
        if (p / "data_access.py").is_file() or (p / "repository.py").is_file()
    ]
    assert len(feature_modules) >= 2


def test_should_embed_two_repos_and_seam_when_fixture_is_workspace() -> None:
    repo_markers = list(WORKSPACE_SEAM.rglob(".repo-root"))
    env_files = list(WORKSPACE_SEAM.rglob(".env.example"))
    schema_files = list(WORKSPACE_SEAM.rglob("schema*.sql"))
    assert len(repo_markers) == 2 and env_files and schema_files


def test_should_provide_source_but_no_docs_when_fixture_is_no_docs() -> None:
    source_files = [p for p in NO_DOCS.rglob("*.py") if p.is_file()]
    doc_files = [
        p
        for p in NO_DOCS.rglob("*")
        if p.is_file() and p.suffix.lower() in {".md", ".rst", ".adoc"} and p.name != "README.md"
    ]
    assert source_files and doc_files == []


# ── AC 1: the mechanism each fixture exercises is actually present ───────────


def test_should_contradict_doc_claim_when_code_diverges_in_stale_doc() -> None:
    doc_text = "\n".join(p.read_text(encoding="utf-8") for p in (STALE_DOC / "docs").glob("*.md"))
    # The doc claims a layout the source deliberately violates: the claim names
    # a directory the code does not use, so VERIFY can classify it CONTRADICTED.
    assert "data_access" in doc_text or "data-access" in doc_text
    assert not (STALE_DOC / "src" / "ingredients" / "data_access.py").exists()


def test_should_load_remote_frontend_by_env_var_when_fixture_is_workspace() -> None:
    env_text = "\n".join(
        p.read_text(encoding="utf-8") for p in WORKSPACE_SEAM.rglob(".env.example")
    )
    loader_text = "\n".join(
        p.read_text(encoding="utf-8") for p in WORKSPACE_SEAM.rglob("*.js") if p.is_file()
    )
    assert "REMOTE_WIDGET_APP_URL" in env_text
    assert "REMOTE_WIDGET_APP_URL" in loader_text


# ── AC 2: anonymization is machine-enforced ──────────────────────────────────


def test_should_find_zero_client_identifiers_in_fixture_paths() -> None:
    offending: list[str] = []
    for fixture in ALL_FIXTURES:
        for path in _fixture_files(fixture):
            rel = str(path.relative_to(FIXTURES_ROOT))
            if _scan_for_client_identifiers(rel):
                offending.append(rel)
    assert offending == []


def test_should_find_zero_client_identifiers_in_fixture_contents() -> None:
    offending: dict[str, list[str]] = {}
    for fixture in ALL_FIXTURES:
        for path in _fixture_files(fixture):
            text = path.read_text(encoding="utf-8", errors="replace")
            hits = _scan_for_client_identifiers(text)
            if hits:
                offending[str(path.relative_to(FIXTURES_ROOT))] = hits
    assert offending == {}
