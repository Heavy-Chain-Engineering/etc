#!/usr/bin/env python3
"""Compose a Google-spec DESIGN.md from impeccable's freeform output (F018).

Takes impeccable's freeform DESIGN.md plus PRODUCT.md as input and emits a
DESIGN.md that conforms to Google Labs Code's official spec
(https://github.com/google-labs-code/design.md). The freeform input is
preserved at `<output_dir>/DESIGN-impeccable.md` as an intermediate
artifact so operators can still see the WHY behind the structured tokens.

The compose is intentionally conservative: when impeccable's prose doesn't
contain extractable token values (hex colors, font names, px sizes), the
corresponding YAML frontmatter field is OMITTED rather than fabricated.
Google's `missing-primary` and `missing-typography` lint rules surface as
warnings — operators decide whether to refine via `/design --refresh`.

Usage:
  design_md_compose.py <impeccable_design_md> <product_md> --out <output_path>
  design_md_compose.py --help

Exit codes:
  0 = success (output written; lint passed or was unavailable)
  1 = usage / IO error
  2 = compose failed lint (errors only; warnings don't block)
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

# Canonical Markdown section order per Google's spec
CANONICAL_SECTIONS = [
    "Overview",
    "Colors",
    "Typography",
    "Layout",
    "Elevation & Depth",
    "Shapes",
    "Components",
    "Do's and Don'ts",
]

# Hex color pattern: #RGB or #RRGGBB
HEX_COLOR_PATTERN = re.compile(r"#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b")

# Font-name heuristic: common font-family conventions in prose
COMMON_FONT_NAMES = [
    "Inter", "Roboto", "Helvetica", "Helvetica Neue", "Arial",
    "Georgia", "Times New Roman", "Courier", "Courier New",
    "SF Pro", "SF Pro Text", "SF Pro Display",
    "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace",
    "Avenir", "Lato", "Montserrat", "Open Sans", "Poppins",
    "Source Sans Pro", "Source Serif Pro", "Source Code Pro",
    "Fira Sans", "Fira Code", "IBM Plex Sans", "IBM Plex Mono",
]


def extract_name(product_md: str) -> str | None:
    """Extract a project name from PRODUCT.md's first h1 heading."""
    for line in product_md.splitlines():
        stripped = line.strip()
        if stripped.startswith("# ") and len(stripped) > 2:
            return stripped[2:].strip()
    return None


def extract_description(product_md: str) -> str | None:
    """Extract a single-line description: the first non-empty paragraph
    after the h1 heading, capped at 200 chars."""
    lines = product_md.splitlines()
    past_h1 = False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            past_h1 = True
            continue
        if not past_h1:
            continue
        if stripped.startswith("#"):
            break  # next heading, no description found
        if stripped:
            desc = stripped[:200].rstrip(",.;:")
            return desc
    return None


def extract_colors(impeccable_design: str) -> dict[str, str]:
    """Extract hex color values from impeccable's prose. Heuristic — if the
    text mentions `#3B82F6` near words like "primary", "accent", "background",
    we map them. Otherwise the unmapped hex values get sequential names."""
    colors: dict[str, str] = {}
    text = impeccable_design.lower()

    role_patterns = {
        "primary": r"(?:primary|main|brand)\s+(?:colou?rs?|accent|hue)?[\s:]*",
        "accent": r"(?:accent|secondary|highlight)\s+(?:colou?rs?|hue)?[\s:]*",
        "background": r"(?:background|bg|surface)\s+(?:colou?rs?|hue)?[\s:]*",
        "text": r"(?:text|foreground|copy)\s+(?:colou?rs?|hue)?[\s:]*",
    }

    seen_hex_values: set[str] = set()
    for role, pat in role_patterns.items():
        # Look for ROLE followed by hex within 80 chars
        full_pat = pat + r"[^#\n]{0,80}#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\b"
        match = re.search(full_pat, text)
        if match:
            hex_val = "#" + match.group(1).lower()
            # Skip if another role already claimed this hex; use a token
            # reference in your design docs instead of duplicating the value.
            if hex_val in seen_hex_values:
                continue
            colors[role] = hex_val
            seen_hex_values.add(hex_val)

    # Any leftover hex values get sequential names. Compare case-insensitive
    # so #3B82F6 and #3b82f6 don't both land as separate entries.
    seen_values_lower = {v.lower() for v in colors.values()}
    leftover_idx = 1
    for match in HEX_COLOR_PATTERN.finditer(impeccable_design):
        hex_val = "#" + match.group(1).lower()
        if hex_val in seen_values_lower:
            continue
        seen_values_lower.add(hex_val)
        # Don't clobber an explicit role assignment
        name = f"color{leftover_idx}"
        while name in colors:
            leftover_idx += 1
            name = f"color{leftover_idx}"
        colors[name] = hex_val
        leftover_idx += 1

    return colors


def extract_typography(impeccable_design: str) -> dict[str, dict[str, str]]:
    """Detect font-family mentions and emit minimal typography tokens.
    Only `fontFamily` is reliably extractable from prose; size/weight need
    more context than impeccable's freeform usually provides."""
    typography: dict[str, dict[str, str]] = {}

    # Tier 1: explicit "[Use] X" patterns
    role_patterns = {
        "body": r"(?:body|copy|paragraph)s?\s*(?:text|font|typography)?[\s:]*",
        "heading": r"(?:heading|display|title)s?\s*(?:text|font|typography)?[\s:]*",
        "mono": r"(?:mono|code|monospace)\s*(?:text|font|typography)?[\s:]*",
    }
    text = impeccable_design

    for role, pat_prefix in role_patterns.items():
        for font in COMMON_FONT_NAMES:
            # Pattern: ROLE-prefix … FONT (within 80 chars)
            full_pat = pat_prefix + r"[^\n]{0,80}\b" + re.escape(font) + r"\b"
            if re.search(full_pat, text, flags=re.IGNORECASE):
                typography[role] = {"fontFamily": font}
                break

    # If we got nothing from roles, try any font mentioned at all and call
    # it 'body' as a sensible default.
    if not typography:
        for font in COMMON_FONT_NAMES:
            if re.search(r"\b" + re.escape(font) + r"\b", text):
                typography["body"] = {"fontFamily": font}
                break

    return typography


def extract_overview(impeccable_design: str) -> str:
    """The Overview is impeccable's brand-voice / aesthetic-direction prose.
    Heuristic: take everything between the first h1 and the next h1 OR up
    to a "don't" / "anti-reference" section, whichever comes first."""
    lines = impeccable_design.splitlines()
    in_body = False
    overview_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("# "):
            if in_body:
                break  # next h1 — stop
            in_body = True
            continue
        if not in_body:
            continue
        # Stop at any section heading that looks like don'ts / anti-references
        if re.match(r"^#{1,6}\s+(don'?t|anti.?references?|avoid|never)", line, re.IGNORECASE):
            break
        overview_lines.append(line)
    return "\n".join(overview_lines).strip()


def extract_dos_donts(impeccable_design: str) -> str:
    """Extract the don'ts / anti-references section if present."""
    lines = impeccable_design.splitlines()
    in_section = False
    section_lines: list[str] = []
    for line in lines:
        if re.match(r"^#{1,6}\s+(don'?t|anti.?references?|avoid|never)", line, re.IGNORECASE):
            in_section = True
            continue
        if in_section and re.match(r"^#{1,6}\s+", line):
            break  # next heading
        if in_section:
            section_lines.append(line)
    return "\n".join(section_lines).strip()


def render_frontmatter(data: dict[str, Any]) -> str:
    """Emit YAML frontmatter delimited by `---` lines."""
    yaml_body = yaml.safe_dump(data, sort_keys=False, default_flow_style=False)
    return f"---\n{yaml_body}---\n"


def render_body(
    overview: str,
    colors: dict[str, str],
    typography: dict[str, dict[str, str]],
    dos_donts: str,
) -> str:
    """Render canonical-order Markdown sections. Skip sections with no
    content (Google's `missing-sections` rule is info-level)."""
    sections: list[str] = []

    if overview:
        sections.append(f"## Overview\n\n{overview}")

    if colors:
        token_lines = "\n".join(f"- `{name}`: `{val}`" for name, val in colors.items())
        sections.append(
            f"## Colors\n\n"
            f"Color tokens are defined in the YAML frontmatter above. "
            f"Reference via `{{colors.<name>}}` syntax in component definitions.\n\n"
            f"{token_lines}"
        )

    if typography:
        font_lines = "\n".join(
            f"- `{name}`: {spec.get('fontFamily', 'unspecified')}"
            for name, spec in typography.items()
        )
        sections.append(
            f"## Typography\n\n"
            f"Typography tokens defined in YAML frontmatter. Reference via "
            f"`{{typography.<name>}}`.\n\n"
            f"{font_lines}"
        )

    if dos_donts:
        sections.append(f"## Do's and Don'ts\n\n{dos_donts}")

    return "\n\n".join(sections) + "\n"


def try_lint(output_path: Path) -> tuple[bool, str]:
    """Best-effort lint via `npx @google/design.md lint`. Returns
    (has_errors, message). If npx or the package isn't available, returns
    (False, 'lint skipped') — non-blocking."""
    if shutil.which("npx") is None:
        return False, "lint skipped: npx not available"
    try:
        result = subprocess.run(
            ["npx", "--yes", "@google/design.md", "lint", str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return False, f"lint skipped: {e}"
    if result.returncode == 0:
        return False, "lint: clean"
    # Exit code 1 = errors per Google's spec
    return True, result.stdout + result.stderr


def compose(
    impeccable_design_path: Path,
    product_md_path: Path,
    output_path: Path,
) -> int:
    """Run the full compose pipeline. Returns the exit code."""
    if not impeccable_design_path.exists():
        sys.stderr.write(
            f"ERROR: impeccable DESIGN.md not found: {impeccable_design_path}\n"
        )
        return 1

    impeccable_design = impeccable_design_path.read_text(encoding="utf-8")
    product_md = (
        product_md_path.read_text(encoding="utf-8") if product_md_path.exists() else ""
    )

    name = extract_name(product_md) or "Untitled Project"
    description = extract_description(product_md)
    colors = extract_colors(impeccable_design)
    typography = extract_typography(impeccable_design)
    overview = extract_overview(impeccable_design)
    dos_donts = extract_dos_donts(impeccable_design)

    frontmatter: dict[str, Any] = {
        "version": "alpha",
        "name": name,
    }
    if description:
        frontmatter["description"] = description
    if colors:
        frontmatter["colors"] = colors
    if typography:
        frontmatter["typography"] = typography

    output_text = (
        render_frontmatter(frontmatter)
        + f"\n# {name}\n\n"
        + render_body(overview, colors, typography, dos_donts)
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(output_text, encoding="utf-8")

    # Preserve impeccable's freeform output (only if it's NOT the same file
    # as the output, and only if it differs from any existing copy).
    impeccable_preserve_path = output_path.parent / "DESIGN-impeccable.md"
    if impeccable_design_path.resolve() != impeccable_preserve_path.resolve():
        impeccable_preserve_path.write_text(impeccable_design, encoding="utf-8")

    has_errors, lint_msg = try_lint(output_path)
    sys.stdout.write(f"compose: wrote {output_path}\n")
    sys.stdout.write(f"{lint_msg}\n")

    return 2 if has_errors else 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Compose Google-spec DESIGN.md from impeccable freeform output.",
    )
    parser.add_argument(
        "impeccable_design",
        type=Path,
        help="Path to impeccable's freeform DESIGN.md",
    )
    parser.add_argument(
        "product_md",
        type=Path,
        help="Path to PRODUCT.md (for name + description)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        required=True,
        help="Output path for the Google-spec DESIGN.md",
    )
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit:
        return 1

    return compose(args.impeccable_design, args.product_md, args.out)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
