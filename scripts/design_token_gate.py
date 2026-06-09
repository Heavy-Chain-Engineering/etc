#!/usr/bin/env python3
"""Layer-3 design-token conformance gate (#69 / /design Layer 3).

etc's `/design` phase produces a project's **DESIGN.md** (narrative design
intent, Layer 1) and **design-tokens.json** (machine-readable tokens — colors,
spacing, typography, Layer 2). This is the missing Layer 3: a deterministic
gate that checks a project's code actually USES the tokens instead of hardcoding
design values. Same "declare the contract, enforce with a deterministic gate"
family as the build review gate (`standards/process/build-review-gate.md`) — a
read-only helper script + JSON contract that mirrors `scripts/review_gate.py`.

One subcommand:

  scan --tokens <design-tokens.json>
       (--files <f...> | --dir <d> [--include <glob,glob>])
       [--strict] [--skip-design-token-gate "<reason>"]
      Parse the token file into a normalized set of allowed color values, scan
      the provided files (or a directory with include globs) for hardcoded color
      literals, and report every literal whose normalized value is NOT in the
      allowed set as a violation `{file, line, value, kind: "color"}`.
        stdout: JSON {tokens_file, scanned_files, allowed_color_count,
                      violations, verdict} where verdict ∈ {CLEAN, VIOLATIONS}.
        exit 0  — advisory default: even with violations the gate does not block
                  (v1 is conservative — no build is blocked until the operator
                  opts in). Also the path taken under --skip-design-token-gate
                  with a non-empty reason (logged verbatim).
        exit 2  — --strict AND violations present (the opt-in blocking path).
        exit 1  — usage error (no --files/--dir, empty skip reason) OR a
                  missing/unreadable/empty/unparseable tokens file (NEVER a
                  false "clean").

v1 scope (YAGNI; deferrals recorded as ADR decisions): **colors only** (hex
`#rgb`/`#rrggbb`/`#rrggbbaa` and CSS `rgb()/rgba()/hsl()/hsla()`), **advisory by
default**. Spacing / typography / radii enforcement and a blocking/strict default
are documented follow-ups, not v1.

Read-only; never writes; never network. No module-level mutable globals
(CQ-001 — `Final`/tuples/frozensets only).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

# The default include globs for a directory scan: the source surfaces where a
# hardcoded color is a design-token violation. Stylesheets + the JS/TS family.
DEFAULT_INCLUDE_GLOBS: Final[tuple[str, ...]] = (
    "*.css",
    "*.scss",
    "*.less",
    "*.js",
    "*.jsx",
    "*.ts",
    "*.tsx",
)

# Directory names always skipped on a directory scan — vendored, generated, or
# VCS trees are never the project's authored source.
SKIP_DIR_NAMES: Final[frozenset[str]] = frozenset(
    {"node_modules", "dist", "build", ".git"}
)

# The verdict vocabulary (a closed set — no string-typo dispatch).
VERDICT_CLEAN: Final[str] = "CLEAN"
VERDICT_VIOLATIONS: Final[str] = "VIOLATIONS"

# Color-literal grammar. Hex (#rgb / #rrggbb / #rrggbbaa) and the CSS color
# functions rgb()/rgba()/hsl()/hsla(). Matched as DATA — never evaluated.
_HEX_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3})\b"
)
_FUNC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?:rgba?|hsla?)\([^()]*\)", re.IGNORECASE
)


# ── color normalization ──────────────────────────────────────────────────────


def normalize_color(value: str) -> str | None:
    """Return a canonical color key for `value`, or None if it is not a color.

    Hex is lowercased and 3-digit forms are expanded to 6-digit, so `#FFF` and
    `#ffffff` compare equal. CSS color functions are lowercased with all
    internal whitespace stripped, so `rgb(255, 0, 0)` and `rgb(255,0,0)` compare
    equal. Anything that is not a recognized color literal returns None.
    """
    text = value.strip()
    hex_match = _HEX_PATTERN.fullmatch(text)
    if hex_match is not None:
        return _normalize_hex(text)
    if _FUNC_PATTERN.fullmatch(text):
        return re.sub(r"\s+", "", text).lower()
    return None


def _normalize_hex(text: str) -> str:
    digits = text[1:].lower()
    if len(digits) == 3:
        digits = "".join(ch * 2 for ch in digits)
    return f"#{digits}"


def find_color_literals(line: str) -> list[str]:
    """Return every color literal substring in `line`, in order of appearance."""
    found: list[str] = []
    found.extend(_HEX_PATTERN.findall(line))
    found.extend(_FUNC_PATTERN.findall(line))
    return found


# ── token loading ────────────────────────────────────────────────────────────


def collect_allowed_colors(payload: object) -> frozenset[str]:
    """Recursively collect normalized leaf color values from a token payload.

    Tolerates the common token-file shapes: a flat `{name: value}` map, nested
    groups, AND the W3C design-tokens `{ "$value": "...", "$type": "color" }`
    leaf shape. Only leaf strings that normalize to a color are kept; non-color
    leaves (spacing, font names, numbers, booleans) are ignored.
    """
    collected: set[str] = set()
    _walk_tokens(payload, collected)
    return frozenset(collected)


def _walk_tokens(node: object, collected: set[str]) -> None:
    if isinstance(node, str):
        normalized = normalize_color(node)
        if normalized is not None:
            collected.add(normalized)
        return
    if isinstance(node, dict):
        for child in node.values():
            _walk_tokens(child, collected)
        return
    if isinstance(node, list):
        for child in node:
            _walk_tokens(child, collected)


def load_allowed_colors(tokens_path: Path) -> tuple[frozenset[str] | None, str | None]:
    """Load and normalize the allowed color set from a tokens file.

    Returns `(colors, None)` on success or `(None, error_message)` when the file
    is missing, unreadable, empty, or not valid JSON — never a false empty set
    (the caller maps a non-None error to exit 1, never a "clean" pass).
    """
    try:
        raw = tokens_path.read_text(encoding="utf-8")
    except OSError as exc:
        return None, f"cannot read tokens file {tokens_path}: {exc}"
    if not raw.strip():
        return None, f"tokens file is empty: {tokens_path}"
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        return None, f"tokens file is not valid JSON: {tokens_path}: {exc}"
    return collect_allowed_colors(payload), None


# ── file scanning ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Violation:
    file: str
    line: int
    value: str
    kind: str


def scan_files(files: list[Path], allowed: frozenset[str]) -> list[Violation]:
    """Scan each file for hardcoded color literals not present in `allowed`.

    Each file is read as UTF-8 text; an unreadable file (missing, a directory,
    binary that fails decode) is skipped rather than crashing the scan. Every
    color literal whose normalized value is not in the allowed set becomes a
    `{file, line, value, kind: "color"}` violation.
    """
    violations: list[Violation] = []
    for path in files:
        violations.extend(_scan_one_file(path, allowed))
    return violations


def _scan_one_file(path: Path, allowed: frozenset[str]) -> list[Violation]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    found: list[Violation] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        for literal in find_color_literals(line):
            normalized = normalize_color(literal)
            if normalized is not None and normalized not in allowed:
                found.append(
                    Violation(
                        file=str(path), line=line_number, value=literal, kind="color"
                    )
                )
    return found


def collect_dir_files(
    directory: Path, include_globs: tuple[str, ...] | None, tokens_path: Path | None
) -> list[Path]:
    """Collect files under `directory` matching the include globs.

    Always skips any path inside a `SKIP_DIR_NAMES` directory and the tokens
    file itself. Results are sorted for deterministic output.
    """
    globs = include_globs if include_globs is not None else DEFAULT_INCLUDE_GLOBS
    resolved_tokens = tokens_path.resolve() if tokens_path is not None else None
    matched: set[Path] = set()
    for glob in globs:
        for candidate in directory.rglob(glob):
            if not candidate.is_file():
                continue
            if _is_skipped(candidate):
                continue
            if resolved_tokens is not None and candidate.resolve() == resolved_tokens:
                continue
            matched.add(candidate)
    return sorted(matched)


def _is_skipped(path: Path) -> bool:
    return any(part in SKIP_DIR_NAMES for part in path.parts)


# ── verdict + rendering ──────────────────────────────────────────────────────


def _resolve_skip(raw: str | None) -> str | None:
    """Return the sanitized skip reason, or None when absent/empty."""
    if raw is None:
        return None
    reason = raw.strip()
    return reason or None


def _render_payload(
    tokens_path: Path,
    scanned: list[Path],
    allowed: frozenset[str],
    violations: list[Violation],
    skip_reason: str | None,
) -> dict[str, object]:
    verdict = VERDICT_VIOLATIONS if violations else VERDICT_CLEAN
    payload: dict[str, object] = {
        "tokens_file": str(tokens_path),
        "scanned_files": [str(path) for path in scanned],
        "allowed_color_count": len(allowed),
        "violations": [
            {"file": v.file, "line": v.line, "value": v.value, "kind": v.kind}
            for v in violations
        ],
        "verdict": verdict,
    }
    if skip_reason is not None:
        payload["skip_reason"] = skip_reason
    return payload


# ── CLI ──────────────────────────────────────────────────────────────────────


def _resolve_scan_files(args: argparse.Namespace, tokens_path: Path) -> list[Path]:
    if args.files:
        return [Path(f) for f in args.files]
    directory = Path(args.dir)
    include = _parse_include(args.include)
    return collect_dir_files(directory, include, tokens_path)


def _parse_include(raw: str | None) -> tuple[str, ...] | None:
    if raw is None:
        return None
    globs = tuple(part.strip() for part in raw.split(",") if part.strip())
    return globs or None


def _cli_scan(args: argparse.Namespace) -> int:
    skip_reason = _resolve_skip(args.skip_design_token_gate)
    if args.skip_design_token_gate is not None and skip_reason is None:
        sys.stderr.write(
            "ERROR: --skip-design-token-gate requires a non-empty reason\n"
        )
        return 1
    if not args.files and args.dir is None:
        sys.stderr.write("ERROR: provide either --files or --dir\n")
        return 1

    tokens_path = Path(args.tokens)
    allowed, error = load_allowed_colors(tokens_path)
    if error is not None or allowed is None:
        sys.stderr.write(f"ERROR: {error}\n")
        return 1

    scanned = _resolve_scan_files(args, tokens_path)
    violations = scan_files(scanned, allowed)
    payload = _render_payload(tokens_path, scanned, allowed, violations, skip_reason)
    print(json.dumps(payload))

    if skip_reason is not None:
        return 0
    if args.strict and violations:
        return 2
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="design_token_gate.py",
        description=(
            "Layer-3 design-token conformance gate: scan a project's source for "
            "hardcoded color literals not defined in its design-tokens.json. "
            "Advisory by default; --strict makes violations exit non-zero."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser(
        "scan", help="Scan source for hardcoded colors not in design-tokens.json."
    )
    p_scan.add_argument(
        "--tokens", required=True, help="Path to the project's design-tokens.json."
    )
    p_scan.add_argument(
        "--files", nargs="*", default=[], help="Explicit source files to scan."
    )
    p_scan.add_argument(
        "--dir", default=None, help="Directory to scan (with --include globs)."
    )
    p_scan.add_argument(
        "--include",
        default=None,
        help="Comma-separated include globs for --dir (default: source globs).",
    )
    p_scan.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 when violations exist (default: advisory, exit 0).",
    )
    p_scan.add_argument(
        "--skip-design-token-gate",
        dest="skip_design_token_gate",
        default=None,
        help="Skip the gate with a non-empty, logged reason (parity flag).",
    )
    p_scan.set_defaults(func=_cli_scan)
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. argparse exits with code 2 on usage error."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - module entry guard, covered by subprocess CLI tests
    sys.exit(main())
