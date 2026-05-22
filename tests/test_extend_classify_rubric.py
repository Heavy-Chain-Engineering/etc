"""Tests for ``scripts/extend_resolver.py::classify`` triage rubric.

Coverage targets:
- AC-002+BR-002: 12 parametrized cases (4 light + 4 medium + 4 heavy)
  exercise the rule-based, deterministic classifier.

Triage rubric per spec BR-002:
- **Light:** Problem text names <=3 specific file paths (regex: paths
  ending in ``.py|.ts|.tsx|.md|.sh|.yaml|.yml``) AND contains no
  architectural keywords.
- **Heavy:** Problem text contains >=1 architectural keyword
  (``redesign``, ``rearchitect``, ``swap framework``, ``migrate to``,
  ``replace with``, ``restructure``) OR explicit ADR-amendment language.
- **Medium:** Everything else.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Literal

import pytest

_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import extend_resolver  # pyright: ignore[reportMissingImports]  # noqa: E402, I001 — sys.path inserted above


@pytest.fixture()
def target_dir(tmp_path: Path) -> Path:
    """Return a dummy target dir; classify reads no files from it today."""
    feature_dir = tmp_path / "F042-target"
    feature_dir.mkdir()
    return feature_dir


_LIGHT_CASES: list[tuple[str, str]] = [
    (
        "light-single-py",
        "the SettingsPage uses shadcn but the rest uses radix; "
        "swap it in frontend/src/SettingsPage.tsx",
    ),
    (
        "light-two-paths",
        "remove the unused import in scripts/extend_resolver.py and "
        "scripts/feature_id.py",
    ),
    (
        "light-three-files",
        "update scripts/release_notes.py, docs/adrs/F025-001-foo.md "
        "and standards/process/build-extend.md to mention the new flag",
    ),
    (
        "light-md-only",
        "fix the typo in docs/adrs/F025-002-lifecycle.md",
    ),
]

_HEAVY_CASES: list[tuple[str, str]] = [
    (
        "heavy-redesign",
        "redesign the auth flow to use OAuth2 instead of JWT",
    ),
    (
        "heavy-rearchitect",
        "rearchitect the dispatch layer to support remote agents",
    ),
    (
        "heavy-swap-framework",
        "swap framework from FastAPI to Litestar across the API surface",
    ),
    (
        "heavy-migrate-to",
        "migrate to PostgreSQL from SQLite for the audit log surface",
    ),
]

_MEDIUM_CASES: list[tuple[str, str]] = [
    (
        "medium-etl-dedup",
        "the ETL step that copies rows from source to target needs a "
        "deduplication pass",
    ),
    (
        "medium-no-paths",
        "the validation error message is confusing when the user enters "
        "an empty value",
    ),
    (
        "medium-four-files",
        "rewire the test scaffolding across scripts/a.py, scripts/b.py, "
        "scripts/c.py, and scripts/d.py to share a fixture",
    ),
    (
        "medium-vague-component",
        "the dashboard component needs a loading spinner when the API "
        "call is in flight",
    ),
]


@pytest.mark.parametrize(
    "label,problem",
    _LIGHT_CASES,
    ids=[label for label, _ in _LIGHT_CASES],
)
def test_should_classify_as_light_when_path_named_no_architectural_keywords(
    label: str, problem: str, target_dir: Path
) -> None:
    result: Literal["light", "medium", "heavy"] = extend_resolver.classify(
        problem, target_dir
    )

    assert result == "light", (
        f"case {label!r}: expected 'light', got {result!r} for problem: {problem!r}"
    )


@pytest.mark.parametrize(
    "label,problem",
    _HEAVY_CASES,
    ids=[label for label, _ in _HEAVY_CASES],
)
def test_should_classify_as_heavy_when_architectural_keyword_present(
    label: str, problem: str, target_dir: Path
) -> None:
    result: Literal["light", "medium", "heavy"] = extend_resolver.classify(
        problem, target_dir
    )

    assert result == "heavy", (
        f"case {label!r}: expected 'heavy', got {result!r} for problem: {problem!r}"
    )


@pytest.mark.parametrize(
    "label,problem",
    _MEDIUM_CASES,
    ids=[label for label, _ in _MEDIUM_CASES],
)
def test_should_classify_as_medium_when_neither_light_nor_heavy(
    label: str, problem: str, target_dir: Path
) -> None:
    result: Literal["light", "medium", "heavy"] = extend_resolver.classify(
        problem, target_dir
    )

    assert result == "medium", (
        f"case {label!r}: expected 'medium', got {result!r} for problem: {problem!r}"
    )
