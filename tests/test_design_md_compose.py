"""Tests for scripts/design_md_compose.py (F018).

Compose pipeline: impeccable's freeform DESIGN.md + PRODUCT.md →
Google-spec DESIGN.md. The freeform output is preserved at
DESIGN-impeccable.md as an intermediate artifact.

Lint via `npx @google/design.md lint` is best-effort: if npx isn't
available in the test environment, the compose still succeeds (lint
is informational, not blocking).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

SCRIPT = Path(__file__).parent.parent / "scripts" / "design_md_compose.py"


def _run(
    impeccable_design: Path,
    product_md: Path,
    output: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "python3", str(SCRIPT),
            str(impeccable_design),
            str(product_md),
            "--out", str(output),
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )


def _make_fixtures(
    tmp_path: Path,
    impeccable_body: str = (
        "# Brand voice\n"
        "A clean, minimal aesthetic with a confident voice.\n"
        "Primary color is #3B82F6.\n"
        "Body font should be Inter; headings use Source Serif Pro.\n"
        "\n"
        "# Don'ts\n"
        "Don't use saturated reds.\n"
    ),
    product_body: str = (
        "# Acme Platform\n"
        "A workflow automation tool for small teams.\n"
    ),
) -> tuple[Path, Path, Path]:
    """Create synthetic impeccable + product fixtures plus an output path."""
    impeccable_path = tmp_path / "impeccable-DESIGN.md"
    impeccable_path.write_text(impeccable_body, encoding="utf-8")
    product_path = tmp_path / "PRODUCT.md"
    product_path.write_text(product_body, encoding="utf-8")
    output_path = tmp_path / "DESIGN.md"
    return impeccable_path, product_path, output_path


def _parse_compose_output(output_path: Path) -> tuple[dict, str]:
    """Split a DESIGN.md into (frontmatter_dict, body_str)."""
    text = output_path.read_text(encoding="utf-8")
    assert text.startswith("---\n"), f"output missing YAML frontmatter at {output_path}"
    _, fm_yaml, body = text.split("---\n", 2)
    return yaml.safe_load(fm_yaml), body


class TestCLIShape:
    """AC-01: CLI accepts <impeccable_design> <product_md> --out <output>."""

    def test_happy_path_exits_zero(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        result = _run(imp, prod, out)
        assert result.returncode == 0, result.stderr
        assert out.exists()

    def test_missing_impeccable_path_exits_one(self, tmp_path: Path) -> None:
        prod_path = tmp_path / "PRODUCT.md"
        prod_path.write_text("# X\n")
        result = _run(tmp_path / "nonexistent.md", prod_path, tmp_path / "DESIGN.md")
        assert result.returncode == 1


class TestRequiredFrontmatterFields:
    """AC-03: frontmatter includes version, name, and description when available."""

    def test_version_alpha_in_frontmatter(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        assert fm.get("version") == "alpha"

    def test_name_extracted_from_product_md_h1(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        assert fm.get("name") == "Acme Platform"

    def test_description_extracted_when_present(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        assert "description" in fm
        assert "workflow automation" in fm["description"]

    def test_description_omitted_when_product_md_has_no_paragraph(
        self, tmp_path: Path
    ) -> None:
        imp, prod, out = _make_fixtures(
            tmp_path, product_body="# Bare Project\n"
        )
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        assert fm.get("name") == "Bare Project"
        assert "description" not in fm


class TestTokenExtraction:
    """AC-04: colors and typography populated when impeccable mentions them;
    omitted otherwise."""

    def test_hex_color_with_primary_role_extracted(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        assert "colors" in fm
        # Lowercase form is canonical
        assert fm["colors"].get("primary", "").lower() == "#3b82f6"

    def test_duplicate_hex_values_deduplicated(self, tmp_path: Path) -> None:
        """The same hex (case-insensitive) MUST NOT appear under two names."""
        imp_body = (
            "Primary color is #3B82F6. The accent color is also #3b82f6 (lowercase)."
        )
        imp, prod, out = _make_fixtures(tmp_path, impeccable_body=imp_body)
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        # All values must be unique (case-insensitive)
        values_lower = [v.lower() for v in fm.get("colors", {}).values()]
        assert len(values_lower) == len(set(values_lower)), (
            f"duplicate hex values in output: {fm['colors']}"
        )

    def test_typography_extracted_body_and_heading(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        assert "typography" in fm
        assert fm["typography"].get("body", {}).get("fontFamily") == "Inter"
        assert fm["typography"].get("heading", {}).get("fontFamily") == "Source Serif Pro"

    def test_colors_omitted_when_no_hex_in_input(self, tmp_path: Path) -> None:
        imp_body = "# Brand\nA minimal aesthetic. No specific colors yet.\n"
        imp, prod, out = _make_fixtures(tmp_path, impeccable_body=imp_body)
        _run(imp, prod, out)
        fm, _ = _parse_compose_output(out)
        assert "colors" not in fm


class TestCanonicalSectionOrder:
    """AC-05: Markdown sections appear in Google's canonical order. Sections
    without content are omitted."""

    def test_overview_appears_before_colors(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        _, body = _parse_compose_output(out)
        overview_idx = body.find("## Overview")
        colors_idx = body.find("## Colors")
        assert overview_idx != -1
        assert colors_idx != -1
        assert overview_idx < colors_idx

    def test_colors_appears_before_typography(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        _, body = _parse_compose_output(out)
        colors_idx = body.find("## Colors")
        typography_idx = body.find("## Typography")
        assert colors_idx < typography_idx

    def test_dos_and_donts_appears_last(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        _, body = _parse_compose_output(out)
        dos_idx = body.find("## Do's and Don'ts")
        assert dos_idx != -1
        # Nothing else after it
        after_dos = body[dos_idx + len("## Do's and Don'ts"):]
        assert "## " not in after_dos

    def test_empty_sections_are_omitted(self, tmp_path: Path) -> None:
        """No mention of fonts → no Typography section at all."""
        imp_body = "# Brand\nA minimalist look. Primary color is #FF0000.\n"
        imp, prod, out = _make_fixtures(tmp_path, impeccable_body=imp_body)
        _run(imp, prod, out)
        _, body = _parse_compose_output(out)
        assert "## Typography" not in body


class TestImpeccablePreserved:
    """AC-06: impeccable's freeform DESIGN.md preserved at DESIGN-impeccable.md."""

    def test_impeccable_copy_written_to_output_dir(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        preserved = out.parent / "DESIGN-impeccable.md"
        assert preserved.exists()

    def test_impeccable_copy_matches_original(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        original = imp.read_text(encoding="utf-8")
        _run(imp, prod, out)
        preserved = out.parent / "DESIGN-impeccable.md"
        assert preserved.read_text(encoding="utf-8") == original


class TestOverviewAndDonts:
    """Body content from impeccable maps into Overview + Do's and Don'ts."""

    def test_overview_contains_impeccable_brand_voice(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        _, body = _parse_compose_output(out)
        assert "minimal aesthetic" in body
        assert "confident voice" in body

    def test_donts_contains_impeccable_anti_references(self, tmp_path: Path) -> None:
        imp, prod, out = _make_fixtures(tmp_path)
        _run(imp, prod, out)
        _, body = _parse_compose_output(out)
        dos_idx = body.find("## Do's and Don'ts")
        donts_section = body[dos_idx:]
        assert "saturated reds" in donts_section
