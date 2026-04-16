#!/usr/bin/env python3
"""check-vocabulary.py — Verify vocabulary consistency across bounded contexts.

Reads a vocabulary table from the nearest INVARIANTS.md, then scans each
context's source directory for usage of terms NOT declared in that context's
vocabulary rows. Non-empty stdout = violation found (per the invariants
convention).

Usage:
    python3 scripts/check-vocabulary.py <vocabulary_name> [--invariants PATH]

Exit codes:
    0 = no violations (or empty vocabulary table)
    1 = violations found
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def find_invariants_file(start: Path | None = None) -> Path | None:
    """Walk up from start (default: cwd) to find INVARIANTS.md."""
    current = start or Path.cwd()
    while True:
        candidate = current / "INVARIANTS.md"
        if candidate.is_file():
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def parse_vocabulary_table(
    invariants_path: Path, vocab_name: str
) -> list[dict[str, str]]:
    """Parse a vocabulary table from INVARIANTS.md.

    Looks for a section matching: ### Vocabulary: <vocab_name>
    Then reads the markdown table rows.

    Returns a list of dicts with keys: context, term, canonical.
    """
    text = invariants_path.read_text()
    # Find the vocabulary section
    pattern = rf"###\s+Vocabulary:\s+{re.escape(vocab_name)}\s*\n"
    match = re.search(pattern, text)
    if not match:
        return []

    rows: list[dict[str, str]] = []
    lines = text[match.end() :].split("\n")

    header_seen = False
    separator_seen = False

    for line in lines:
        stripped = line.strip()

        # Stop at next section heading or empty content
        if stripped.startswith("#") and not stripped.startswith("|"):
            break
        if stripped.startswith("- **"):
            break

        if not stripped.startswith("|"):
            if header_seen and separator_seen:
                # End of table
                break
            continue

        cells = [c.strip() for c in stripped.split("|")]
        # Remove empty first/last from leading/trailing pipes
        cells = [c for c in cells if c]

        if not header_seen:
            header_seen = True
            continue
        if not separator_seen:
            # This is the separator row (|---|---|---|)
            separator_seen = True
            continue

        if len(cells) >= 3:
            # Strip quotes from term
            term = cells[1].strip("\"'")
            rows.append(
                {
                    "context": cells[0],
                    "term": term,
                    "canonical": cells[2],
                }
            )

    return rows


def scan_context_for_violations(
    context_name: str,
    allowed_terms: list[str],
    all_canonical: set[str],
    all_terms: set[str],
    project_root: Path,
    concept_id: str | None = None,
) -> list[str]:
    """Scan a context directory for vocabulary term violations.

    Searches for any term from the full vocabulary that is NOT in this
    context's allowed set. This catches cases where context A uses
    context B's terms instead of its own.

    Returns list of violation descriptions.
    """
    violations: list[str] = []

    # Find the context directory — try common patterns
    context_dir = None
    for candidate in [
        project_root / "src" / context_name.lower().replace(" ", "_"),
        project_root / "src" / context_name.lower().replace(" ", "-"),
        project_root / context_name.lower().replace(" ", "_"),
        project_root / context_name.lower().replace(" ", "-"),
        project_root / context_name,
    ]:
        if candidate.is_dir():
            context_dir = candidate
            break

    if context_dir is None:
        print(
            f"WARNING: Context directory not found for '{context_name}', skipping",
            file=sys.stderr,
        )
        return []

    # Build set of terms to search for (all terms from ALL contexts
    # that are NOT in this context's allowed set)
    disallowed = (all_terms | all_canonical) - set(allowed_terms)
    if not disallowed:
        return []

    # Scan source files
    exempt_pattern = None
    if concept_id:
        exempt_pattern = f"# concept-exempt: {concept_id}"

    for source_file in context_dir.rglob("*.py"):
        try:
            content = source_file.read_text()
        except (OSError, UnicodeDecodeError):
            continue

        for line_num, line in enumerate(content.split("\n"), 1):
            # Skip exempted lines
            if exempt_pattern and exempt_pattern in line:
                continue
            # Skip comments
            stripped = line.strip()
            if stripped.startswith("#"):
                continue

            for term in disallowed:
                # Word-boundary matching to avoid "active" matching "inactive"
                if re.search(rf"\b{re.escape(term)}\b", line):
                    rel_path = source_file.relative_to(project_root)
                    violations.append(
                        f"{rel_path}:{line_num}: term '{term}' not in "
                        f"vocabulary for context '{context_name}'"
                    )

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify vocabulary consistency across bounded contexts"
    )
    parser.add_argument("vocabulary_name", help="Name of the vocabulary to check")
    parser.add_argument(
        "--invariants",
        type=Path,
        default=None,
        help="Path to INVARIANTS.md (default: search upward from cwd)",
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=None,
        help="Project root directory (default: parent of INVARIANTS.md)",
    )
    parser.add_argument(
        "--concept-id",
        type=str,
        default=None,
        help="CONCEPT ID for exemption pattern matching",
    )
    args = parser.parse_args()

    # Find INVARIANTS.md
    invariants_path = args.invariants or find_invariants_file()
    if invariants_path is None or not invariants_path.is_file():
        print("WARNING: No INVARIANTS.md found", file=sys.stderr)
        return 0

    # Parse vocabulary table
    rows = parse_vocabulary_table(invariants_path, args.vocabulary_name)
    if not rows:
        # Empty table = no constraints = pass
        return 0

    # Determine project root
    project_root = args.project_root or invariants_path.parent

    # Group terms by context
    context_terms: dict[str, list[str]] = {}
    all_terms: set[str] = set()
    all_canonical: set[str] = set()

    for row in rows:
        ctx = row["context"]
        if ctx not in context_terms:
            context_terms[ctx] = []
        context_terms[ctx].append(row["term"])
        all_terms.add(row["term"])
        all_canonical.add(row["canonical"])

    # Scan each context
    all_violations: list[str] = []
    for context_name, allowed_terms in context_terms.items():
        violations = scan_context_for_violations(
            context_name=context_name,
            allowed_terms=allowed_terms,
            all_canonical=all_canonical,
            all_terms=all_terms,
            project_root=project_root,
            concept_id=args.concept_id,
        )
        all_violations.extend(violations)

    if all_violations:
        for v in all_violations:
            print(v)
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
