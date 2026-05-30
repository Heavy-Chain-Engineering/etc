"""Contract tests for Codex harness operator documentation."""

from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
GUIDE = REPO_ROOT / "docs" / "guides" / "codex-harness.md"


def test_codex_guide_documents_current_ci_states_without_stale_gap() -> None:
    content = GUIDE.read_text(encoding="utf-8")

    assert "`enabled`" in content
    assert "`available-but-not-wired`" in content
    assert "`unsupported`" in content
    assert "richer `enabled` / `available-but-not-wired` / `unsupported` CI states" not in content


def test_codex_guide_documents_user_scope_safety_reason_and_docs_baseline() -> None:
    content = GUIDE.read_text(encoding="utf-8")

    assert "User/global Codex install is not enabled" in content
    assert "affect every repository" in content
    assert "config merge, trust review, and uninstall semantics" in content
    assert "Codex Docs Baseline" in content
    assert "developers.openai.com/codex/hooks" in content
    assert "developers.openai.com/codex/plugins/build" in content


def test_codex_guide_records_release_dogfood_evidence() -> None:
    content = GUIDE.read_text(encoding="utf-8")

    assert "Dogfood Evidence" in content
    assert "Private application repo temp clone" in content
    assert "Private platform repo temp clone" in content
    assert "tests/test_codex_dogfood.py" in content
    assert ".codex/expected/" in content
