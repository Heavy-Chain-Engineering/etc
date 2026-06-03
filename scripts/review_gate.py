#!/usr/bin/env python3
"""Build-time review gate (F-2026-06-02 / /build Step 7 review sub-step).

The 6th sibling gate helper (ADR-002), alongside spec_enforcer_chunker /
layer_review / journey_lineage_check / spec_coupling_check /
runtime_totalization_check. It owns the deterministic mechanics of the Step 7
review gate; the build skill ORCHESTRATES the Agent dispatch.

Two subcommands:

  plan --feature-dir <dir> [--base <ref>]
      Decide which review agents fire and derive the changed fileset.
      stdout: JSON {agents, changed_files, architect_reviewer_fires, skip_reason}.
      code-reviewer + security-reviewer are ALWAYS in agents (GA-001 — the two
      lenses where a missed review is a shipped defect). architect-reviewer is
      added IFF layer_review.py detect returns a non-empty touched-layer array
      AND state.yaml.spec_phase.infrastructure_only is not true (ADR-002; reuses
      layer_review detect — single source of truth for layer detection). The
      changed fileset is the union of the wave tasks' files_in_scope (read from
      <dir>/tasks/*.yaml) plus `git diff --name-only` vs the integration base as
      a cross-check (GA-003). exit 0; exit 1 on usage/IO error.

  aggregate --findings <file...> [--skip-review-gate "<reason>"]
      Parse each file's ADR-001 `## Review Findings` block (severity-tagged
      lines `- [CRITICAL|HIGH|MEDIUM|LOW] <loc> — <finding>` plus a trailing
      `GATE: BLOCK|PASS|CLEAN`), severity-gate, and emit the verification.md
      Review Findings fragment to stdout.
        exit 2 (BLOCK)    — any finding is CRITICAL/HIGH, OR a block is
                            missing/unparseable (INSUFFICIENT_EVIDENCE — the
                            conservative block, NEVER a silent pass; ADR-003,
                            spec Edge Case 2).
        exit 0 (PROCEED)  — all blocks CLEAN or only MEDIUM/LOW, OR
                            --skip-review-gate carries a non-empty reason (the
                            override is recorded in the emitted fragment).
        exit 1 (ERROR)    — usage error, or --skip-review-gate with an
                            empty/missing reason.

Read-only over the feature dir + git. Finding text is parsed as DATA: a path or
command named inside a finding is NEVER fetched or executed (directory-traversal
/ injection defense — design.md Security Considerations). All git calls use an
argv-list subprocess (no shell string).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

SCRIPTS_DIR = Path(__file__).resolve().parent
LAYER_REVIEW_SCRIPT = SCRIPTS_DIR / "layer_review.py"

# The review agents that ALWAYS fire (GA-001) — a missed code or security
# review is a shipped defect, so neither is ever gated on signal detection.
CORE_REVIEWERS: tuple[str, ...] = ("code-reviewer", "security-reviewer")
ARCHITECT_REVIEWER: str = "architect-reviewer"

# The integration base used for the git-diff cross-check (GA-003). The fileset
# union is authoritative; the diff is a best-effort cross-check, so a missing
# base or a non-git tree degrades to "no extra files" rather than an error.
DEFAULT_BASE_REF: str = "main"
GIT_TIMEOUT_SECONDS: int = 10

# Severity vocabulary = the layer-review scale (CRITICAL/HIGH/MEDIUM/LOW),
# reused not invented (ADR-001). Ordered most→least severe so index 0 is the
# top of the scale; SEVERITY_ORDER gives a comparable rank.
SEVERITY_SCALE: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW")
SEVERITY_ORDER: dict[str, int] = {name: rank for rank, name in enumerate(SEVERITY_SCALE)}

# Findings at these severities block the release tag (ADR-003).
BLOCKING_SEVERITIES: frozenset[str] = frozenset({"CRITICAL", "HIGH"})

# The sentinel verdict for a missing/unparseable findings block — a
# conservative block, never a silent pass (spec Edge Case 2, ADR-001).
INSUFFICIENT_EVIDENCE: str = "INSUFFICIENT_EVIDENCE"

# The ADR-001 emission contract, parsed as data.
_FINDINGS_HEADING_PATTERN = re.compile(r"^#{1,6}\s+review findings\b", re.IGNORECASE)
_FINDING_LINE_PATTERN = re.compile(
    r"^\s*-\s*\[(?P<severity>CRITICAL|HIGH|MEDIUM|LOW)\]\s*(?P<body>.*\S)?\s*$",
    re.IGNORECASE,
)
_GATE_LINE_PATTERN = re.compile(
    r"^\s*GATE:\s*(?P<verdict>BLOCK|PASS|CLEAN)\s*$", re.IGNORECASE
)


# ── plan ───────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ReviewPlan:
    agents: list[str]
    changed_files: list[str]
    architect_reviewer_fires: bool
    skip_reason: str | None


def _is_infrastructure_only(feature_dir: Path) -> bool:
    """True iff the feature's state.yaml declares spec_phase.infrastructure_only.

    Defensive by construction (mirrors layer_review._feature_infrastructure_only):
    an absent/unreadable/non-true value returns False, so the exemption only
    fires on an explicit positive declaration.
    """
    state_path = feature_dir / "state.yaml"
    if not state_path.is_file():
        return False
    try:
        data = yaml.safe_load(state_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    spec_phase = data.get("spec_phase")
    if not isinstance(spec_phase, dict):
        return False
    return spec_phase.get("infrastructure_only") is True


def _detect_touched_layers(design_path: Path) -> list[str]:
    """Run `layer_review.py detect` over the design and return touched layers.

    Reuses the single-source-of-truth detector (ADR-002) rather than
    re-implementing layer detection. A non-zero exit or unparseable output
    yields an empty list (architect-reviewer then gates out — conservative for
    a no-architecture change, not a correctness hole since code/security still
    fire).
    """
    if not design_path.is_file():
        return []
    completed = subprocess.run(
        ["python3", str(LAYER_REVIEW_SCRIPT), "detect", "--design", str(design_path)],
        capture_output=True,
        text=True,
        timeout=GIT_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        return []
    try:
        layers = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return []
    if not isinstance(layers, list):
        return []
    return [str(layer) for layer in layers]


def _files_in_scope_from_tasks(feature_dir: Path) -> list[str]:
    """Union the files_in_scope lists across every wave task YAML, in order."""
    tasks_dir = feature_dir / "tasks"
    if not tasks_dir.is_dir():
        return []
    ordered: list[str] = []
    seen: set[str] = set()
    for task_path in sorted(tasks_dir.glob("*.yaml")):
        for path in _task_files(task_path):
            if path not in seen:
                seen.add(path)
                ordered.append(path)
    return ordered


def _task_files(task_path: Path) -> list[str]:
    try:
        data = yaml.safe_load(task_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError):
        return []
    if not isinstance(data, dict):
        return []
    scope = data.get("files_in_scope")
    if not isinstance(scope, list):
        return []
    return [str(path) for path in scope]


def _git_diff_files(base_ref: str) -> list[str]:
    """Return files changed vs the integration base, or [] on any git failure.

    A cross-check, not the authoritative fileset (GA-003), so a non-git tree, a
    missing base, or a git error degrades to "no extra files" rather than
    failing the plan. Argv-list subprocess — no shell string.
    """
    try:
        completed = subprocess.run(
            ["git", "diff", "--name-only", f"{base_ref}...HEAD"],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []
    if completed.returncode != 0:
        return []
    return [line for line in completed.stdout.splitlines() if line.strip()]


def build_plan(feature_dir: Path, base_ref: str) -> ReviewPlan:
    """Compute the review plan for a feature dir (the deterministic mechanics)."""
    agents = list(CORE_REVIEWERS)
    fires = False
    skip_reason: str | None = None

    if _is_infrastructure_only(feature_dir):
        skip_reason = "infrastructure_only: no application layers to review"
    else:
        touched = _detect_touched_layers(feature_dir / "design.md")
        if touched:
            fires = True
            agents.append(ARCHITECT_REVIEWER)
        else:
            skip_reason = "no architectural layers touched"

    scoped = _files_in_scope_from_tasks(feature_dir)
    seen = set(scoped)
    changed = list(scoped)
    for path in _git_diff_files(base_ref):
        if path not in seen:
            seen.add(path)
            changed.append(path)

    return ReviewPlan(
        agents=agents,
        changed_files=changed,
        architect_reviewer_fires=fires,
        skip_reason=skip_reason,
    )


def _cli_plan(args: argparse.Namespace) -> int:
    feature_dir = Path(args.feature_dir)
    if not feature_dir.is_dir():
        sys.stderr.write(f"ERROR: feature dir not found: {feature_dir}\n")
        return 1
    plan = build_plan(feature_dir, args.base)
    print(
        json.dumps(
            {
                "agents": plan.agents,
                "changed_files": plan.changed_files,
                "architect_reviewer_fires": plan.architect_reviewer_fires,
                "skip_reason": plan.skip_reason,
            }
        )
    )
    return 0


# ── aggregate ──────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Finding:
    severity: str
    text: str


@dataclass(frozen=True)
class FindingsBlock:
    source: str
    findings: tuple[Finding, ...]
    insufficient: bool  # True when the block is missing/unparseable


def parse_findings_block(source: str, text: str) -> FindingsBlock:
    """Parse one agent's ADR-001 `## Review Findings` block.

    A block is well-formed when it has a `## Review Findings` heading AND a
    trailing `GATE: BLOCK|PASS|CLEAN` line. Severity-tagged lines between them
    become findings. A missing heading or a missing GATE line is
    INSUFFICIENT_EVIDENCE (conservative block) — never silently treated as
    clean. Finding text is captured verbatim and never dereferenced.
    """
    lines = text.splitlines()
    heading_index = _find_heading_index(lines)
    if heading_index is None:
        return FindingsBlock(source=source, findings=(), insufficient=True)

    findings: list[Finding] = []
    has_gate = False
    for line in lines[heading_index + 1 :]:
        if _GATE_LINE_PATTERN.match(line):
            has_gate = True
            break
        finding = _parse_finding_line(line)
        if finding is not None:
            findings.append(finding)

    if not has_gate:
        return FindingsBlock(source=source, findings=(), insufficient=True)
    return FindingsBlock(source=source, findings=tuple(findings), insufficient=False)


def _find_heading_index(lines: list[str]) -> int | None:
    for index, line in enumerate(lines):
        if _FINDINGS_HEADING_PATTERN.match(line):
            return index
    return None


def _parse_finding_line(line: str) -> Finding | None:
    match = _FINDING_LINE_PATTERN.match(line)
    if match is None:
        return None
    body = (match.group("body") or "").strip()
    return Finding(severity=match.group("severity").upper(), text=body)


def read_findings_block(path: Path) -> FindingsBlock:
    """Read and parse a findings file; a missing/unreadable file is insufficient."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return FindingsBlock(source=str(path), findings=(), insufficient=True)
    return parse_findings_block(str(path), text)


def _max_severity(blocks: list[FindingsBlock]) -> str | None:
    severities = [f.severity for block in blocks for f in block.findings]
    if not severities:
        return None
    return min(severities, key=lambda name: SEVERITY_ORDER[name])


def _is_blocking(blocks: list[FindingsBlock]) -> bool:
    if any(block.insufficient for block in blocks):
        return True
    return any(
        f.severity in BLOCKING_SEVERITIES for block in blocks for f in block.findings
    )


def render_fragment(
    blocks: list[FindingsBlock], blocking: bool, override_reason: str | None
) -> str:
    """Render the verification.md `## Review Findings` fragment.

    Records the overall max-severity verdict, one line per finding, any
    INSUFFICIENT_EVIDENCE source, and the override reason when present.
    """
    lines = ["## Review Findings", ""]
    verdict = _verdict_label(blocks, blocking, override_reason)
    lines.append(f"Verdict: {verdict}")
    lines.append("")
    for block in blocks:
        if block.insufficient:
            lines.append(f"- [{INSUFFICIENT_EVIDENCE}] {block.source} — no parseable block")
        for finding in block.findings:
            lines.append(f"- [{finding.severity}] {finding.text}")
    if override_reason is not None:
        lines.append("")
        lines.append(f"Override (--skip-review-gate): {override_reason}")
    return "\n".join(lines) + "\n"


def _verdict_label(
    blocks: list[FindingsBlock], blocking: bool, override_reason: str | None
) -> str:
    if override_reason is not None:
        return "PROCEED (overridden)"
    if any(block.insufficient for block in blocks):
        return f"BLOCK ({INSUFFICIENT_EVIDENCE})"
    top = _max_severity(blocks)
    if blocking:
        return f"BLOCK (max severity {top})"
    return f"PROCEED (max severity {top})" if top else "PROCEED (CLEAN)"


def _cli_aggregate(args: argparse.Namespace) -> int:
    if not args.findings:
        sys.stderr.write("ERROR: --findings requires at least one file\n")
        return 1

    override_reason = _resolve_override(args.skip_review_gate)
    if args.skip_review_gate is not None and override_reason is None:
        sys.stderr.write(
            "ERROR: --skip-review-gate requires a non-empty reason\n"
        )
        return 1

    blocks = [read_findings_block(Path(path)) for path in args.findings]
    blocking = _is_blocking(blocks)
    print(render_fragment(blocks, blocking, override_reason), end="")

    if override_reason is not None:
        return 0
    return 2 if blocking else 0


def _resolve_override(raw: str | None) -> str | None:
    """Return the sanitized override reason, or None when absent/empty."""
    if raw is None:
        return None
    reason = raw.strip()
    return reason or None


# ── CLI ────────────────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="review_gate.py",
        description=(
            "Build-time review gate: plan which review agents fire and "
            "aggregate their severity-gated findings into a block/proceed "
            "verdict. Used by /build Step 7."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_plan = sub.add_parser(
        "plan", help="Decide which review agents fire + derive the changed fileset."
    )
    p_plan.add_argument(
        "--feature-dir", required=True, help="Path to the feature directory."
    )
    p_plan.add_argument(
        "--base",
        default=DEFAULT_BASE_REF,
        help="Integration base ref for the git-diff cross-check.",
    )
    p_plan.set_defaults(func=_cli_plan)

    p_aggregate = sub.add_parser(
        "aggregate", help="Aggregate per-agent findings into a block/proceed verdict."
    )
    p_aggregate.add_argument(
        "--findings",
        nargs="*",
        default=[],
        help="One or more files each holding an agent's Review Findings block.",
    )
    p_aggregate.add_argument(
        "--skip-review-gate",
        dest="skip_review_gate",
        default=None,
        help="Override a blocking verdict with a non-empty, logged reason.",
    )
    p_aggregate.set_defaults(func=_cli_aggregate)

    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. argparse exits with code 2 on usage error."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":  # pragma: no cover - module entry guard, covered by subprocess CLI tests
    sys.exit(main())
