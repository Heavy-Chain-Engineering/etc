"""Contract tests for skills/roadmap/SKILL.md (audit init 3 + 9).

This skill shipped to dist/ via the compiler's blanket skill glob while
UNTRACKED in git — an unreviewed, untested skill graduating into installs.
Committing it required (per the audit's coupled rule) pinning its
load-bearing prose contracts in the same change, so "tracked and untested"
is not the outcome. House grep-contract idiom: prose IS the artifact;
these assertions pin the invariants that make the skill what it is.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "roadmap" / "SKILL.md"


def _text() -> str:
    assert SKILL.exists(), f"missing skill body: {SKILL}"
    return SKILL.read_text(encoding="utf-8")


def test_frontmatter_names_the_skill() -> None:
    text = _text()
    assert text.startswith("---\n"), "skill body must open with YAML frontmatter"
    assert "name: roadmap" in text


def test_hard_rule_no_target_no_roadmap() -> None:
    """The skill's entire identity: it is a gatekeeper, not a generator."""
    text = _text()
    assert "No clear target state = No roadmap" in text, (
        "the Hard Rule is the skill's load-bearing contract; without it the "
        "skill degrades into a generic planner that plans toward fuzz"
    )


def test_refusal_behavior_is_specified() -> None:
    text = _text()
    assert "Refuses to Proceed" in text or "refuses to proceed" in text, (
        "the gatekeeper refusal behavior must be specified, not implied"
    )
    assert "Target state is not clear enough" in text, (
        "the refusal must name its reason so the operator knows what to fix"
    )


def test_readiness_checklist_present_with_blocking_tier() -> None:
    text = _text()
    assert "Target State Readiness Checklist" in text
    assert "Must Have (Blocking)" in text, (
        "the checklist must distinguish blocking from advisory items — a "
        "flat list lets vague targets through"
    )


def test_interrogation_protocol_elicits_rather_than_guesses() -> None:
    text = _text()
    assert "Interrogation Protocol" in text, (
        "on unclear targets the skill must ELICIT requirements, not guess — "
        "refuse-or-ask, never fabricate (the harness's anti-fabrication rule)"
    )


def test_pairs_with_discovery_skill() -> None:
    text = _text()
    assert "Discovery" in text, (
        "the skill's frontmatter promises Discovery-skill pairing; the body "
        "must keep that reference"
    )
