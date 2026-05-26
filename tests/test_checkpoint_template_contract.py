"""Drift contract test for the checkpoint document structure (AC-002).

F-2026-05-26-checkpoint-template-and-gate, wave 2.

The checkpoint document shape is declared in three places:

  1. ``templates/checkpoint.md.tmpl`` — the canonical ``string.Template``.
  2. ``scripts/precompact_checkpoint.py`` — the runtime hook, whose authoritative
     emitted header set is its ``SECTION_HEADINGS`` constant plus the top-level
     ``# Session Checkpoint`` header it renders from the same template / its
     embedded fallback.
  3. ``skills/checkpoint/SKILL.md`` Step 2 — the model-reasoned fill path.

This test asserts all three header sets are EQUAL. If any one drifts (a renamed
section, a dropped header, a new section added to only one source), the test
fails. The hook is the runtime source of truth; the template and the skill
derive from it.

Headers are matched on text, not on ``$token`` literals — the template uses
``${head_sha}`` (a placeholder, not a header), which is excluded by matching
only lines that begin with ``#``.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_PATH = REPO_ROOT / "templates" / "checkpoint.md.tmpl"
HOOK_SCRIPT = REPO_ROOT / "scripts" / "precompact_checkpoint.py"
SKILL_PATH = REPO_ROOT / "skills" / "checkpoint" / "SKILL.md"

TOP_HEADER = "# Session Checkpoint"
_HEADER_LINE = re.compile(r"^#{1,6} .+$")
_FENCE = re.compile(r"^```")


def _markdown_headers(text: str) -> frozenset[str]:
    """Return the set of markdown ATX headers (``#``-prefixed lines) in text."""
    return frozenset(
        line.strip() for line in text.splitlines() if _HEADER_LINE.match(line.strip())
    )


def _template_headers() -> frozenset[str]:
    """Parse the section headers declared in the canonical template."""
    return _markdown_headers(TEMPLATE_PATH.read_text(encoding="utf-8"))


def _hook_section_headings() -> frozenset[str]:
    """The header set the hook declares: SECTION_HEADINGS + the top header.

    SECTION_HEADINGS holds only the four ``##`` section headers; the hook also
    renders the top-level ``# Session Checkpoint`` header (from the template and
    its embedded fallback), so the hook's authoritative emitted set is the union.
    """
    spec = importlib.util.spec_from_file_location("precompact_checkpoint", HOOK_SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    section_headings: tuple[str, ...] = module.SECTION_HEADINGS
    return frozenset(section_headings) | {TOP_HEADER}


def _skill_step2_headers() -> frozenset[str]:
    """Parse the headers documented inside the Step 2 fenced markdown block.

    Step 2 of SKILL.md embeds the checkpoint structure in a single
    ````markdown ... ```` fenced block. The block's ``#`` lines are the skill's
    declaration of the document structure.
    """
    text = SKILL_PATH.read_text(encoding="utf-8")
    block = _extract_step2_markdown_block(text)
    return _markdown_headers(block)


def _extract_step2_markdown_block(text: str) -> str:
    """Return the contents of the first fenced ``markdown`` block after Step 2."""
    lines = text.splitlines()
    step2_index = _find_step2_index(lines)
    return _first_markdown_fence_body(lines, step2_index)


def _find_step2_index(lines: list[str]) -> int:
    """Return the line index of the Step 2 heading, or 0 if absent."""
    for index, line in enumerate(lines):
        if line.strip().startswith("### Step 2"):
            return index
    return 0


def _first_markdown_fence_body(lines: list[str], start: int) -> str:
    """Return the body of the first ```` ```markdown ```` fence at/after start."""
    body: list[str] = []
    inside = False
    for line in lines[start:]:
        if not inside and line.strip().startswith("```markdown"):
            inside = True
            continue
        if inside and _FENCE.match(line.strip()):
            break
        if inside:
            body.append(line)
    return "\n".join(body)


def test_should_match_template_headers_to_hook_when_no_drift() -> None:
    """Template header set must equal the hook's authoritative emitted set."""
    assert _template_headers() == _hook_section_headings()


def test_should_match_skill_step2_headers_to_hook_when_no_drift() -> None:
    """SKILL.md Step 2 header set must equal the hook's authoritative set."""
    assert _skill_step2_headers() == _hook_section_headings()


def test_should_match_all_three_sources_when_no_drift() -> None:
    """All three declarations must agree on the exact section header set."""
    template = _template_headers()
    hook = _hook_section_headings()
    skill = _skill_step2_headers()
    assert template == hook == skill


def test_should_declare_the_five_expected_headers_when_aligned() -> None:
    """The agreed set is the top header plus the four documented sections."""
    expected = frozenset(
        {
            TOP_HEADER,
            "## Task Status",
            "## Decisions Made This Session",
            "## Discovered Context",
            "## Pending Items",
        }
    )
    assert _hook_section_headings() == expected


def test_should_point_skill_step2_at_the_template_when_filling_checkpoint() -> None:
    """BR-007: Step 2 must name the canonical template as the source of truth.

    The skill must instruct the model to FILL templates/checkpoint.md.tmpl
    rather than re-declare the structure inline. Naming the template path is
    the greppable contract that prevents a future agent from reintroducing an
    inline structure that silently drifts from the hook.
    """
    text = SKILL_PATH.read_text(encoding="utf-8")
    assert "templates/checkpoint.md.tmpl" in text
