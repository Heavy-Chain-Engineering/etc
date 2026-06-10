"""Coverage-floor drift tripwire (audit init 5).

standards/testing/testing-standards.md once claimed a 98% coverage gate
"enforced by pyproject (fail_under = 98), Stop hook, CI pipeline" while the
real pyproject floor was 28 and neither a Stop-hook coverage check nor a CI
pipeline existed. A MANDATORY standard citing phantom enforcement trains
agents to assume a backstop that is not there.

These tests pin the standard's stated number to pyproject's actual
``fail_under`` so the document and the gate cannot drift apart again, and
assert the phantom-enforcer claim never returns.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
TESTING_STANDARDS = REPO_ROOT / "standards" / "testing" / "testing-standards.md"


def _pyproject_fail_under() -> int:
    with PYPROJECT.open("rb") as fh:
        data = tomllib.load(fh)
    return int(data["tool"]["coverage"]["report"]["fail_under"])


def test_testing_standards_floor_matches_pyproject() -> None:
    """The number the standard cites must equal pyproject's fail_under."""
    text = TESTING_STANDARDS.read_text(encoding="utf-8")
    match = re.search(r"`fail_under = (\d+)`", text)
    assert match, (
        "testing-standards.md must cite the coverage floor as a literal "
        "`fail_under = <N>` so this tripwire can pin it to pyproject"
    )
    assert int(match.group(1)) == _pyproject_fail_under(), (
        f"testing-standards.md cites fail_under = {match.group(1)} but "
        f"pyproject.toml enforces {_pyproject_fail_under()}. Update BOTH "
        "together — a standard citing a number the gate does not enforce "
        "is the phantom-enforcement defect this test exists to prevent."
    )


def test_testing_standards_names_no_phantom_enforcers() -> None:
    """The standard must not claim Stop-hook or CI enforcement that does
    not exist. If a real CI coverage gate is ever added, update the
    standard's Enforced-by line and this assertion together."""
    text = TESTING_STANDARDS.read_text(encoding="utf-8")
    enforced_lines = [
        line for line in text.splitlines() if line.lstrip().startswith("- Enforced by:")
    ]
    assert enforced_lines, "testing-standards.md must keep an 'Enforced by:' line"
    for line in enforced_lines:
        assert "CI pipeline" not in line or "no CI pipeline" in text, (
            "testing-standards.md claims CI-pipeline coverage enforcement; "
            "no CI pipeline exists. Name only real mechanisms."
        )
