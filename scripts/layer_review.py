#!/usr/bin/env python3
"""Layer Impact Analysis engine (F-2026-05-26 Layered Architecture Review).

Single source of truth (BR-009) for both layer *detection* and Layer
Impact Analysis *completeness checking*. Reads the declarative rubric
registry (standards/architecture/layer-rubrics.yaml, ADR-001) plus a
design.md file; writes nothing. /architect and /build both invoke the
CLI form — neither reimplements detection or checking inline.

Two subcommands, exit-code contract:
  detect --design <path> [--registry <path>]
      stdout: JSON array of touched layer ids (e.g. ["data-access"]).
      Empty array when no layer touched (EC-001). exit 0 on success.
  check --design <path> [--registry <path>]
      exit 0 when every touched layer's rubric items each have an answer
      or reasoned N/A in the design's `## Layer Impact Analysis` table;
      exit 2 when one or more cells are unfilled (stdout lists each as
      `<layer>/<item-id>: <severity>`).
  exit 1 on usage / IO / registry error (both subcommands).

Detection is ReDoS-safe: detection_signals are matched as case-insensitive
whole-word literal tokens, never compiled as user-supplied regex. Markdown
scanning excludes fenced code blocks and "Out of Scope"/"Future" sections
(F015 spec_coupling_check.py precedent; EC-006).

Layer Impact Analysis table format (the contract `check` parses, authored
by /architect per BR-008):

    ## Layer Impact Analysis

    ### data-access
    | Item | Criterion | Answer / N/A | Severity |
    |------|-----------|--------------|----------|
    | da-index-coverage | ... | Yes, index added | CRITICAL |
    | da-row-estimates  | ... | N/A: read-only   | HIGH     |

Each touched layer is a `### <layer-id>` subsection containing a GitHub-
flavored markdown table whose FIRST column is the rubric item id and THIRD
column is the answer-or-N/A. A cell is "filled" when that third column,
stripped, is non-empty; a reasoned N/A counts as filled (AC-008).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY: Path = REPO_ROOT / "standards" / "architecture" / "layer-rubrics.yaml"

# ISO/IEC 25010 product-quality characteristics — the closed vocabulary for
# every rubric item's quality_attribute (BR-005 / AC-005).
ISO_25010: frozenset[str] = frozenset(
    {
        "functional_suitability",
        "performance_efficiency",
        "compatibility",
        "usability",
        "reliability",
        "security",
        "maintainability",
        "portability",
    }
)

SEVERITIES: frozenset[str] = frozenset({"CRITICAL", "HIGH", "MEDIUM", "LOW"})

_REQUIRED_ITEM_FIELDS: tuple[str, ...] = (
    "id",
    "criterion",
    "quality_attribute",
    "severity_if_missed",
    "mechanizable",
)

# A markdown header line for a section whose detection signals must be
# ignored (EC-006). Matches "## Out of Scope", "### Future", etc.
_EXCLUDED_SECTION_PATTERN = re.compile(
    r"^#{1,6}\s+(out of scope|out-of-scope|not in scope|future)\b",
    re.IGNORECASE,
)

# The Layer Impact Analysis top-level heading (BR-008).
_ANALYSIS_HEADING_PATTERN = re.compile(
    r"^#{1,6}\s+layer impact analysis\b",
    re.IGNORECASE,
)

# A per-layer subsection heading inside the analysis: `### <layer-id>`.
_SUBSECTION_HEADING_PATTERN = re.compile(r"^#{1,6}\s+(?P<id>[A-Za-z0-9][\w-]*)\s*$")

# A markdown table row: leading/trailing pipes, cells split on `|`.
_TABLE_ROW_PATTERN = re.compile(r"^\s*\|.*\|\s*$")

# A table separator row (e.g. `|------|-----|`) — skipped, not a data row.
_TABLE_SEPARATOR_PATTERN = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


class RegistryError(Exception):
    """The rubric registry is absent, unreadable, malformed, or invalid (EC-003)."""


@dataclass(frozen=True)
class RubricItem:
    id: str
    criterion: str
    quality_attribute: str
    severity_if_missed: str
    mechanizable: bool


@dataclass(frozen=True)
class Layer:
    id: str
    name: str
    detection_signals: tuple[str, ...]
    rubric: tuple[RubricItem, ...]


@dataclass(frozen=True)
class Registry:
    layers: tuple[Layer, ...]
    cross_cutting_concerns: tuple[Layer, ...]


@dataclass(frozen=True)
class Cell:
    layer: str
    item_id: str
    severity: str


@dataclass(frozen=True)
class CheckResult:
    complete: bool
    unfilled: list[Cell]


# ── Registry loading + schema validation (EC-003) ───────────────────────


def load_registry(path: Path = DEFAULT_REGISTRY) -> Registry:
    """Parse and schema-validate the rubric registry.

    Raises:
        RegistryError: if the file is absent, unreadable, not valid YAML,
            not a mapping, or violates the rubric-item schema (missing
            field, out-of-vocabulary quality_attribute / severity,
            non-boolean mechanizable).
    """
    if not path.exists():
        msg = f"registry not found: {path}"
        raise RegistryError(msg)

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        msg = f"registry read error: {exc}"
        raise RegistryError(msg) from exc

    try:
        parsed = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        msg = f"registry parse error: {exc}"
        raise RegistryError(msg) from exc

    if not isinstance(parsed, dict):
        msg = f"registry must be a YAML mapping; got {type(parsed).__name__}"
        raise RegistryError(msg)

    layers = _parse_layer_list(parsed.get("layers"), "layers")
    concerns = _parse_layer_list(
        parsed.get("cross_cutting_concerns"), "cross_cutting_concerns"
    )
    return Registry(layers=layers, cross_cutting_concerns=concerns)


def _parse_layer_list(value: Any, key: str) -> tuple[Layer, ...]:
    if not isinstance(value, list):
        msg = f"registry '{key}' must be a list; got {type(value).__name__}"
        raise RegistryError(msg)
    return tuple(_parse_layer(entry, key) for entry in value)


def _parse_layer(entry: Any, key: str) -> Layer:
    if not isinstance(entry, dict):
        msg = f"each entry in '{key}' must be a mapping; got {type(entry).__name__}"
        raise RegistryError(msg)

    layer_id = entry.get("id")
    name = entry.get("name")
    signals = entry.get("detection_signals")
    rubric = entry.get("rubric")

    if not isinstance(layer_id, str) or not layer_id:
        msg = f"layer in '{key}' missing a non-empty 'id'"
        raise RegistryError(msg)
    if not isinstance(name, str) or not name:
        msg = f"layer '{layer_id}' missing a non-empty 'name'"
        raise RegistryError(msg)
    if not isinstance(signals, list) or not signals:
        msg = f"layer '{layer_id}' missing a non-empty 'detection_signals' list"
        raise RegistryError(msg)
    if not isinstance(rubric, list) or not rubric:
        msg = f"layer '{layer_id}' missing a non-empty 'rubric' list"
        raise RegistryError(msg)

    return Layer(
        id=layer_id,
        name=name,
        detection_signals=tuple(str(token) for token in signals),
        rubric=tuple(_parse_item(item, layer_id) for item in rubric),
    )


def _parse_item(item: Any, layer_id: str) -> RubricItem:
    if not isinstance(item, dict):
        msg = f"rubric item in layer '{layer_id}' must be a mapping"
        raise RegistryError(msg)

    missing = [field for field in _REQUIRED_ITEM_FIELDS if field not in item]
    if missing:
        msg = (
            f"rubric item {item.get('id', '<no-id>')!r} in layer "
            f"'{layer_id}' missing field(s): {', '.join(missing)}"
        )
        raise RegistryError(msg)

    quality_attribute = item["quality_attribute"]
    if quality_attribute not in ISO_25010:
        msg = (
            f"rubric item {item['id']!r}: quality_attribute "
            f"{quality_attribute!r} is not an ISO 25010 characteristic "
            f"(allowed: {sorted(ISO_25010)})"
        )
        raise RegistryError(msg)

    severity = item["severity_if_missed"]
    if severity not in SEVERITIES:
        msg = (
            f"rubric item {item['id']!r}: severity_if_missed {severity!r} "
            f"is not one of {sorted(SEVERITIES)}"
        )
        raise RegistryError(msg)

    mechanizable = item["mechanizable"]
    if not isinstance(mechanizable, bool):
        msg = (
            f"rubric item {item['id']!r}: mechanizable must be a boolean; "
            f"got {mechanizable!r} ({type(mechanizable).__name__})"
        )
        raise RegistryError(msg)

    criterion = item["criterion"]
    if not isinstance(criterion, str) or not criterion.strip():
        msg = f"rubric item {item['id']!r}: criterion must be a non-empty string"
        raise RegistryError(msg)

    return RubricItem(
        id=str(item["id"]),
        criterion=criterion,
        quality_attribute=quality_attribute,
        severity_if_missed=severity,
        mechanizable=mechanizable,
    )


# ── Markdown region exclusion (EC-006) ──────────────────────────────────


def scannable_text(design_text: str) -> str:
    """Return the design text with fenced code blocks and Out-of-Scope /
    Future sections removed, for detection-signal matching (EC-006).

    A section is excluded from its heading line up to (but not including)
    the next heading at the same-or-shallower level. Fenced code blocks
    (```...```) are excluded wholesale.
    """
    lines = design_text.splitlines()
    kept: list[str] = []
    in_code = False
    excluded_until_level: int | None = None

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue

        heading_level = _heading_level(line)
        if heading_level is not None:
            if excluded_until_level is not None and heading_level <= excluded_until_level:
                excluded_until_level = None  # left the excluded section
            if excluded_until_level is None and _EXCLUDED_SECTION_PATTERN.match(line):
                excluded_until_level = heading_level
                continue

        if excluded_until_level is not None:
            continue
        kept.append(line)

    return "\n".join(kept)


def _heading_level(line: str) -> int | None:
    match = re.match(r"^(#{1,6})\s+\S", line)
    return len(match.group(1)) if match else None


# ── Detection (BR-006, AC-006) ──────────────────────────────────────────


def detect_layers(design_text: str, registry: Registry) -> list[str]:
    """Return the ids of layers whose detection signals appear in the design.

    Only the layer rows are returned (cross-cutting concerns are walked
    separately by /architect). Matching is case-insensitive whole-word /
    bounded-substring against literal tokens — no user-supplied regex.
    """
    haystack = scannable_text(design_text).lower()
    return [
        layer.id
        for layer in registry.layers
        if _any_signal_present(layer.detection_signals, haystack)
    ]


def _any_signal_present(signals: tuple[str, ...], haystack_lower: str) -> bool:
    return any(_signal_present(signal, haystack_lower) for signal in signals)


def _signal_present(signal: str, haystack_lower: str) -> bool:
    """Whole-word, case-insensitive match of a literal token.

    The token is escaped (never interpreted as regex — ReDoS-safe). Word
    boundaries are applied so "table" does not match "comfortable"; for
    multi-word / symbol-bearing tokens the boundary anchors fall back to
    substring containment, which is the intended behavior.
    """
    token = signal.strip().lower()
    if not token:
        return False
    pattern = re.compile(rf"(?<![a-z0-9]){re.escape(token)}(?![a-z0-9])")
    return pattern.search(haystack_lower) is not None


# ── Completeness check (AC-007, AC-008) ─────────────────────────────────


def check_completeness(design_text: str, registry: Registry) -> CheckResult:
    """Verify every touched layer's rubric items are answered in the design.

    Parses the `## Layer Impact Analysis` section's per-layer tables and
    confirms each rubric item of each touched layer has a non-empty
    answer-or-N/A cell. A reasoned N/A counts as filled; an empty or
    whitespace-only cell does not (AC-008).
    """
    touched = detect_layers(design_text, registry)
    if not touched:
        return CheckResult(complete=True, unfilled=[])

    answers = _parse_analysis_answers(design_text)
    rubric_by_layer = {layer.id: layer.rubric for layer in registry.layers}

    unfilled: list[Cell] = []
    for layer_id in touched:
        layer_answers = answers.get(layer_id, {})
        for item in rubric_by_layer[layer_id]:
            answer = layer_answers.get(item.id, "")
            if not answer.strip():
                unfilled.append(
                    Cell(
                        layer=layer_id,
                        item_id=item.id,
                        severity=item.severity_if_missed,
                    )
                )
    return CheckResult(complete=not unfilled, unfilled=unfilled)


def _parse_analysis_answers(design_text: str) -> dict[str, dict[str, str]]:
    """Parse the Layer Impact Analysis section into {layer_id: {item_id: answer}}.

    Walks from the `## Layer Impact Analysis` heading; each `### <layer-id>`
    subsection's table rows map the first column (item id) to the third
    column (answer-or-N/A).
    """
    lines = design_text.splitlines()
    answers: dict[str, dict[str, str]] = {}
    in_analysis = False
    analysis_level = 0
    current_layer: str | None = None

    for line in lines:
        level = _heading_level(line)
        if level is not None:
            if not in_analysis:
                if _ANALYSIS_HEADING_PATTERN.match(line):
                    in_analysis = True
                    analysis_level = level
                continue
            if level <= analysis_level:
                break  # left the analysis section
            sub = _SUBSECTION_HEADING_PATTERN.match(line)
            current_layer = sub.group("id") if sub else None
            continue

        if in_analysis and current_layer is not None:
            cells = _parse_table_row(line)
            if cells is not None and len(cells) >= 3:
                answers.setdefault(current_layer, {})[cells[0]] = cells[2]

    return answers


def _parse_table_row(line: str) -> list[str] | None:
    """Split a markdown table row into stripped cell values, or None.

    Returns None for non-table lines, the header row, and the separator
    row. Header/separator detection: a separator matches the dash pattern;
    a header row is any row whose first cell is the literal "Item" label.
    """
    if not _TABLE_ROW_PATTERN.match(line):
        return None
    if _TABLE_SEPARATOR_PATTERN.match(line):
        return None
    inner = line.strip().strip("|")
    cells = [cell.strip() for cell in inner.split("|")]
    if cells and cells[0].lower() in {"item", "rubric item", "id"}:
        return None  # header row
    return cells


# ── CLI ──────────────────────────────────────────────────────────────────


def _load_for_cli(args: argparse.Namespace) -> tuple[str, Registry] | None:
    """Read the design + registry for a subcommand, or None on error.

    Errors are written to stderr; the caller returns exit code 1.
    """
    design_path = Path(args.design)
    if not design_path.exists():
        sys.stderr.write(f"ERROR: design file not found: {design_path}\n")
        return None
    try:
        design_text = design_path.read_text(encoding="utf-8")
    except OSError as exc:
        sys.stderr.write(f"ERROR: cannot read design file: {exc}\n")
        return None
    try:
        registry = load_registry(Path(args.registry))
    except RegistryError as exc:
        sys.stderr.write(f"ERROR: {exc}\n")
        return None
    return design_text, registry


def _cli_detect(args: argparse.Namespace) -> int:
    loaded = _load_for_cli(args)
    if loaded is None:
        return 1
    design_text, registry = loaded
    print(json.dumps(detect_layers(design_text, registry)))
    return 0


def _cli_check(args: argparse.Namespace) -> int:
    loaded = _load_for_cli(args)
    if loaded is None:
        return 1
    design_text, registry = loaded
    result = check_completeness(design_text, registry)
    if result.complete:
        return 0
    print("Layer Impact Analysis incomplete — unfilled rubric cells:")
    for cell in result.unfilled:
        print(f"  {cell.layer}/{cell.item_id}: {cell.severity}")
    return 2


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="layer_review.py",
        description=(
            "Layer Impact Analysis engine: detect touched architectural "
            "layers and check Layer Impact Analysis completeness against the "
            "rubric registry. Used by /architect and /build at runtime."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_detect = sub.add_parser(
        "detect", help="Emit the JSON array of layers the design touches."
    )
    _add_common_args(p_detect)
    p_detect.set_defaults(func=_cli_detect)

    p_check = sub.add_parser(
        "check",
        help="Verify the design's Layer Impact Analysis is complete.",
    )
    _add_common_args(p_check)
    p_check.set_defaults(func=_cli_check)

    return parser


def _add_common_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--design", required=True, help="Path to the design.md file."
    )
    parser.add_argument(
        "--registry",
        default=str(DEFAULT_REGISTRY),
        help="Path to the rubric registry (defaults to the shipped registry).",
    )


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. argparse exits with code 2 on usage error."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())
