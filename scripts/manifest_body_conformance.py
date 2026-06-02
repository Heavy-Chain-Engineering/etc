#!/usr/bin/env python3
"""Manifest body-conformance scan (F-2026-06-01 Profile-Driven Agent Bodies).

A sibling of ``scripts/layer_review.py`` (ADR-002). A *profile-aware* agent
manifest — one carrying the ``${profiles}`` marker (ADR-003,
``standards/process/agent-manifest-profile-awareness.md``) — must not name a
language-specific operative tool or path in its body. Naming a Python tool
(``pytest``, ``ruff``, ``mypy``, ``uv run`` …) as an operative instruction
re-hardcodes the body to one stack; substituting a different language's tokens
would be the same bug relocated (BR-004). The body must instead defer to the
active profile's injected bindings.

The over-fire foil (the #54/#46 family) is load-bearing: a token mentioned
inside a fenced code block, in clearly-illustrative/example prose, or on a line
that references the bindings is NOT an operative instruction and is not flagged.
This reuses ``layer_review.py``'s fenced/section-exclusion scannable-text idiom.

One subcommand, exit-code contract:
  check <manifest.md...>
      exit 0 when every checked profile-aware manifest body is clean;
      exit 2 when a body names an operative language-tool token outside a
      fenced / illustrative / bindings-referenced context (stdout lists each
      violation as ``<manifest>:<line>: <token>``);
      exit 1 on usage / IO error (no paths given, unreadable file).

Forward-only (AC-8): a manifest WITHOUT the ``${profiles}`` marker is a legacy
manifest and is skipped — not flagged, not required to change.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

# The profile-aware marker (ADR-003). Only manifests whose text contains this
# literal string are scanned; legacy manifests without it are skipped (AC-8).
PROFILE_AWARE_MARKER: str = "${profiles}"

# Language-specific operative tokens. Module-level + tunable (not inlined at the
# check site) so the deny-list can grow without touching scan logic. Each is
# matched as a bounded literal (never compiled as user-supplied regex —
# ReDoS-safe, mirroring layer_review._signal_present). `uv run` and `pip audit`
# are multi-word; `@router.` and `src/` carry symbols — boundary anchors fall
# back to substring containment for those, which is the intended behavior.
DENY_TOKENS: tuple[str, ...] = (
    "pytest",
    "ruff",
    "mypy",
    "uv run",
    "@router.",
    "pip audit",
    "pyproject",
    "src/",
)

# A line that references the per-profile bindings is an escape hatch: the body
# is pointing the agent AT the bindings, not issuing a language-specific
# instruction. Such a line is excluded from the deny-list scan.
_BINDINGS_REFERENCE_PATTERN = re.compile(r"\bbindings?\b", re.IGNORECASE)

# A clearly-illustrative / example line marks its token mentions as
# non-operative (e.g. "the configured test command (e.g. pytest)"). These
# markers are matched case-insensitively anywhere on the line.
_ILLUSTRATIVE_PATTERN = re.compile(
    r"\b(e\.g\.|i\.e\.|for example|such as|illustrative|example:)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Violation:
    manifest: Path
    line: int
    token: str


@dataclass(frozen=True)
class ConformanceResult:
    complete: bool
    violations: list[Violation]


def is_profile_aware(manifest_text: str) -> bool:
    """True iff the manifest carries the ``${profiles}`` marker (ADR-003)."""
    return PROFILE_AWARE_MARKER in manifest_text


def scannable_lines(manifest_text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, text)`` pairs eligible for the deny-list scan.

    Excluded (the over-fire foil, mirroring ``layer_review.scannable_text``):
      - fenced code blocks (```...```) — wholesale,
      - clearly-illustrative / example lines (``e.g.``, ``such as`` …),
      - lines that reference the bindings.

    Line numbers are 1-based and refer to the original manifest text so that
    violations report the operator's real line.
    """
    kept: list[tuple[int, str]] = []
    in_code = False
    for number, line in enumerate(manifest_text.splitlines(), start=1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        if _ILLUSTRATIVE_PATTERN.search(line):
            continue
        if _BINDINGS_REFERENCE_PATTERN.search(line):
            continue
        kept.append((number, line))
    return kept


def _token_present(token: str, haystack_lower: str) -> bool:
    """Bounded, case-insensitive literal match of a deny-list token.

    The token is escaped (never interpreted as regex — ReDoS-safe). A word
    boundary is anchored only on an edge that is alphanumeric, so ``ruff`` does
    not match a longer word, while a token whose edge is a symbol (``@router.``,
    ``src/``) falls back to substring containment on that edge — the intended
    behavior for symbol/multi-word tokens.
    """
    lead = r"(?<![a-z0-9])" if token[:1].isalnum() else ""
    trail = r"(?![a-z0-9])" if token[-1:].isalnum() else ""
    pattern = re.compile(rf"{lead}{re.escape(token)}{trail}")
    return pattern.search(haystack_lower) is not None


def find_violations(manifest: Path, manifest_text: str) -> list[Violation]:
    """Deny-list violations in a profile-aware manifest body.

    Returns an empty list for a non-profile-aware (legacy) manifest (AC-8) and
    for a clean profile-aware body.
    """
    if not is_profile_aware(manifest_text):
        return []
    violations: list[Violation] = []
    for number, line in scannable_lines(manifest_text):
        lowered = line.lower()
        violations.extend(
            Violation(manifest=manifest, line=number, token=token)
            for token in DENY_TOKENS
            if _token_present(token, lowered)
        )
    return violations


class ManifestReadError(Exception):
    """A manifest path is absent or unreadable (exit 1)."""


def check_manifest(manifest: Path) -> ConformanceResult:
    """Scan one manifest file for body-conformance violations.

    Raises:
        ManifestReadError: if the path is absent or unreadable.
    """
    if not manifest.is_file():
        msg = f"manifest not found: {manifest}"
        raise ManifestReadError(msg)
    try:
        text = manifest.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"cannot read manifest {manifest}: {exc}"
        raise ManifestReadError(msg) from exc
    violations = find_violations(manifest, text)
    return ConformanceResult(complete=not violations, violations=violations)


def _cli_check(args: argparse.Namespace) -> int:
    if not args.manifests:
        sys.stderr.write("ERROR: no manifest paths given\n")
        return 1

    all_violations: list[Violation] = []
    for raw in args.manifests:
        try:
            result = check_manifest(Path(raw))
        except ManifestReadError as exc:
            sys.stderr.write(f"ERROR: {exc}\n")
            return 1
        all_violations.extend(result.violations)

    if not all_violations:
        return 0
    for violation in all_violations:
        print(f"{violation.manifest}:{violation.line}: {violation.token}")
    return 2


class _UsageErrorParser(argparse.ArgumentParser):
    """ArgumentParser that exits 1 (not argparse's default 2) on a usage error.

    The exit-code contract reserves 2 for the conformance failure (a body names
    an operative token) and 1 for any usage / IO error — so an argparse usage
    error (no subcommand, unknown flag) must surface as 1, not collide with 2.
    """

    def error(self, message: str) -> None:  # type: ignore[override]
        self.print_usage(sys.stderr)
        self.exit(1, f"{self.prog}: error: {message}\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = _UsageErrorParser(
        prog="manifest_body_conformance.py",
        description=(
            "Scan profile-aware agent manifest bodies for language-specific "
            "operative tool/path tokens used outside a fenced / illustrative / "
            "bindings-referenced context. Sibling of layer_review.py."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)
    p_check = sub.add_parser(
        "check",
        help="Fail any profile-aware manifest body that names an operative language tool.",
    )
    p_check.add_argument(
        "manifests",
        nargs="*",
        help="Manifest .md paths to check.",
    )
    p_check.set_defaults(func=_cli_check)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. argparse exits with code 2 on usage error."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - entrypoint guard exercised by
    # test_should_run_as_script_module_entrypoint (subprocess), which the
    # in-process coverage run cannot trace; behavior is verified, not the line.
    sys.exit(main())
