#!/usr/bin/env python3
"""Behavioral/runtime totalization core for /build Step 7.6 (Gap A).

Reads <feature_dir>/state.yaml, consumes Gap B's liveness producer interface
(``spec_phase.contract_completeness.liveness[]``), re-runs every declared-live
user-outcome AC against the assembled app via the runtime-verify dispatcher
(``hooks/runtime-verify.sh``), totalizes the per-AC verdicts, and persists the
aggregated results merge-preserve to ``state.yaml.build.runtime_verification``.

This module is the TOTALIZATION CORE (task 005.001): re-run + totalize + exempt
+ schema-tolerant + persist. It deliberately leaves a clean seam — the
``TotalizationResult`` object — for the sibling task 005.002, which wires the
terminal-tag routing (clean release vs milestone) and the exit-code mapping
onto that result. ``terminal_tag`` is written ``null`` here; 005.002 sets it.

Declaration-gating + opt-out hatches (per
``standards/process/behavioral-runtime-dod.md`` and ADR-003):

- ``spec_phase.infrastructure_only: true`` exempts the whole feature; no
  dispatch (AC-9).
- A liveness ``schema_version`` higher than this script knows (1) triggers
  warn-and-skip — never a crash (AC-10, Gap B ADR-002 forward-compat).
- A feature with no liveness block is ungated (forward-only, BR-010).
- Each user-outcome AC is classified verified-live (dispatcher ``pass``),
  deferred (``live_at == "deferred"`` with a non-empty reason), or live-failure
  (declared-live but ``fail`` / ``no-test``).

Exit codes (terminal routing wired by task 005.002):
  0 = clean release allowed (all_verified / exempt / schema_skipped / ungated)
      OR done-as-milestone (deferred_present — a milestone tag is written and
      ``terminal_tag`` is set; a milestone is a legal terminal, not a failure).
  1 = usage / IO error.
  2 = hard block: >=1 declared-live AC failed / had no runtime test.

Task-006 routing contract (carried by
``state.yaml.build.runtime_verification.terminal_tag``):
  - null / absent  => /build Step 7c writes the clean ``etc/feature/<id>/release``
    tag (the normal path; this script does NOT write it).
  - ``.../milestone/<NNN>`` => Step 7c SKIPS the clean release tag — the
    milestone tag is already written here and is the feature's terminal tag.
  Exit 0 = proceed (clean or milestone); exit 2 = block.

Usage:
  runtime_totalization_check.py <feature_dir>
"""

from __future__ import annotations

import contextlib
import importlib.util
import json
import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Literal

import yaml

# Highest liveness producer-interface schema_version this consumer understands.
KNOWN_LIVENESS_SCHEMA_VERSION = 1

# schema_version of the build.runtime_verification block this script writes.
RUNTIME_VERIFICATION_SCHEMA_VERSION = 1

# The firing point this core represents (the authoritative release re-run).
STAGE_RELEASE = "release"

# The sentinel liveness value meaning "intentionally not live yet".
DEFERRED = "deferred"

# Tag-namespace constants for milestone routing (ADR-002).
ETC_TAG_REFGLOB = "refs/tags/etc/feature"
MILESTONE_SEGMENT = "milestone"
MILESTONE_SEQUENCE_START = 1
MILESTONE_SEQUENCE_WIDTH = 3

# Process exit codes for the terminal routing (task 005.002).
EXIT_PROCEED = 0  # clean release allowed, or done-as-milestone
EXIT_USAGE_ERROR = 1
EXIT_HARD_BLOCK = 2

# Closed enum of per-AC runtime statuses (mirrors the profile wire contract).
ACStatus = Literal["pass", "fail", "no-test", "deferred"]

# Overall totalization classifications. 005.002 maps these to terminal tags +
# exit codes; this core only computes them.
Classification = Literal[
    "all_verified",       # every live AC verified, none deferred
    "deferred_present",   # >=1 declared-deferred AC, no live failures
    "live_failure",       # >=1 declared-live AC failed / had no test
    "exempt",             # infrastructure_only: true
    "schema_skipped",     # liveness schema_version higher than known
    "ungated",            # no liveness block (forward-only)
]


@dataclass
class ACVerdict:
    """One totalized per-AC verdict, ready for persistence."""

    ac_id: str
    status: ACStatus
    live_at: str
    evidence: str
    profile: str
    checked_at: str


@dataclass
class TotalizationResult:
    """The seam handed to task 005.002 for tag routing + exit-code mapping.

    ``classification`` is the overall verdict; ``results`` and ``deferred`` are
    the persisted per-AC records; ``persisted_block`` is the exact dict written
    under ``build.runtime_verification`` (with ``terminal_tag`` left ``None``
    for 005.002 to set).
    """

    classification: Classification
    results: list[ACVerdict] = field(default_factory=list)
    deferred: list[dict[str, str]] = field(default_factory=list)
    persisted_block: dict[str, object] = field(default_factory=dict)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def repo_root_from(feature_dir: Path) -> Path:
    """Walk up to the enclosing git repo root; fall back to feature_dir.parent."""
    cur = feature_dir.resolve()
    while cur != cur.parent:
        if (cur / ".git").exists():
            return cur
        cur = cur.parent
    return feature_dir.parent


def read_state(feature_dir: Path) -> dict[str, object]:
    state_path = feature_dir / "state.yaml"
    if not state_path.exists():
        return {}
    try:
        with state_path.open(encoding="utf-8") as handle:
            data = yaml.safe_load(handle) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}


def write_state(feature_dir: Path, state: dict[str, object]) -> None:
    """Write state.yaml back, preserving key order (merge-preserve pattern)."""
    state_path = feature_dir / "state.yaml"
    with state_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(state, handle, sort_keys=False)


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _normalize_status(raw: object) -> ACStatus:
    """Coerce a profile-reported status into the wire-contract enum.

    The profile contract emits only ``pass | fail | no-test``. Any other value
    (including a live AC mislabeled ``deferred``) collapses to ``no-test`` — a
    declared-live AC whose runtime status cannot be read as a pass is unproven.
    """
    candidate = str(raw)
    if candidate in ("pass", "fail", "no-test"):
        # The membership test narrows candidate to the literal set.
        return candidate  # type: ignore[return-value]
    return "no-test"


def invoke_dispatcher(
    feature_path: str, live_ac_ids: list[str], cwd: str
) -> dict[str, object]:
    """Invoke hooks/runtime-verify.sh, passing inputs as JSON on stdin.

    Inputs cross to the dispatcher as JSON on stdin — never as shell args
    (metacharacter-injection defense, per the profile wire contract). Returns
    the parsed ``{"results": [...]}`` aggregate, or ``{"results": []}`` on any
    dispatch / parse failure (the dispatcher itself warns-and-skips).
    """
    dispatcher = Path(cwd) / "hooks" / "runtime-verify.sh"
    if not dispatcher.exists():
        sys.stderr.write(
            f"[runtime-totalization] WARN: dispatcher not found at {dispatcher}; "
            "treating as no results.\n"
        )
        return {"results": []}
    payload = json.dumps(
        {"feature_path": feature_path, "live_ac_ids": live_ac_ids, "cwd": cwd}
    )
    try:
        completed = subprocess.run(
            ["bash", str(dispatcher)],
            input=payload,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except (subprocess.TimeoutExpired, OSError) as exc:
        sys.stderr.write(f"[runtime-totalization] WARN: dispatcher failed: {exc}\n")
        return {"results": []}
    try:
        parsed = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        sys.stderr.write(
            "[runtime-totalization] WARN: dispatcher produced no parseable JSON; "
            "treating as no results.\n"
        )
        return {"results": []}
    return parsed if isinstance(parsed, dict) else {"results": []}


def _liveness_block(state: dict[str, object]) -> dict[str, object] | None:
    """Return the contract_completeness block, or None if absent (ungated)."""
    spec_phase = _as_dict(state.get("spec_phase"))
    contract = spec_phase.get("contract_completeness")
    return contract if isinstance(contract, dict) else None


def _split_live_and_deferred(
    liveness: list[object],
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    """Partition liveness entries into (live, deferred) user-outcome ACs."""
    live: list[dict[str, object]] = []
    deferred: list[dict[str, object]] = []
    for raw in liveness:
        entry = _as_dict(raw)
        if str(entry.get("live_at")) == DEFERRED:
            deferred.append(entry)
        else:
            live.append(entry)
    return live, deferred


def _verdicts_for_live_acs(
    live: list[dict[str, object]],
    dispatch_results: list[object],
    checked_at: str,
) -> list[ACVerdict]:
    """Build a verdict per declared-live AC from the dispatcher's results.

    An AC with no matching dispatcher result is recorded ``no-test`` (a
    declared-live outcome with no runtime assertion cannot pass).
    """
    by_id: dict[str, dict[str, object]] = {}
    for raw in dispatch_results:
        parsed = _as_dict(raw)
        parsed_id = str(parsed.get("ac_id", ""))
        if parsed_id:
            by_id[parsed_id] = parsed

    verdicts: list[ACVerdict] = []
    for entry in live:
        ac_id = str(entry.get("ac_id", ""))
        live_at = str(entry.get("live_at", ""))
        result = by_id.get(ac_id)
        if result is None:
            verdicts.append(
                ACVerdict(
                    ac_id=ac_id,
                    status="no-test",
                    live_at=live_at,
                    evidence="no matching runtime test for declared-live AC",
                    profile="",
                    checked_at=checked_at,
                )
            )
            continue
        verdicts.append(
            ACVerdict(
                ac_id=ac_id,
                status=_normalize_status(result.get("status")),
                live_at=live_at,
                evidence=str(result.get("evidence", "")),
                profile=str(result.get("profile", "")),
                checked_at=checked_at,
            )
        )
    return verdicts


def _classify(
    verdicts: list[ACVerdict], deferred: list[dict[str, str]]
) -> Classification:
    """Compute the overall classification from the per-AC verdicts."""
    if any(v.status in ("fail", "no-test") for v in verdicts):
        return "live_failure"
    if deferred:
        return "deferred_present"
    return "all_verified"


def _deferred_records(deferred: list[dict[str, object]]) -> list[dict[str, str]]:
    records: list[dict[str, str]] = []
    for entry in deferred:
        records.append(
            {
                "ac_id": str(entry.get("ac_id", "")),
                "reason": str(entry.get("deferred_reason") or ""),
            }
        )
    return records


def _build_block(
    verdicts: list[ACVerdict], deferred_records: list[dict[str, str]], last_run: str
) -> dict[str, object]:
    """Assemble the build.runtime_verification block (terminal_tag left null)."""
    return {
        "schema_version": RUNTIME_VERIFICATION_SCHEMA_VERSION,
        "last_run": last_run,
        "stage": STAGE_RELEASE,
        "results": [
            {
                "ac_id": v.ac_id,
                "status": v.status,
                "live_at": v.live_at,
                "evidence": v.evidence,
                "profile": v.profile,
                "checked_at": v.checked_at,
            }
            for v in verdicts
        ],
        "deferred": list(deferred_records),
        "terminal_tag": None,  # set by task 005.002 (tag routing)
    }


def _persist(
    feature_dir: Path, state: dict[str, object], block: dict[str, object]
) -> None:
    """Merge-preserve write: mutate build.runtime_verification, keep all else."""
    raw_build = state.get("build")
    build: dict[str, object] = raw_build if isinstance(raw_build, dict) else {}
    build["runtime_verification"] = block
    state["build"] = build
    write_state(feature_dir, state)


def totalize(feature_dir: Path) -> TotalizationResult:
    """Run the totalization core for one feature directory.

    Honors infrastructure_only exemption + schema tolerance + forward-only
    gating, re-runs declared-live ACs via the dispatcher, totalizes, and
    persists the aggregated results merge-preserve. Returns the structured
    result that task 005.002 routes to a terminal tag + exit code.
    """
    state = read_state(feature_dir)
    spec_phase = _as_dict(state.get("spec_phase"))

    # AC-9: infrastructure_only exempts the whole feature — no dispatch.
    if spec_phase.get("infrastructure_only") is True:
        sys.stderr.write(
            "[runtime-totalization] exempt (infrastructure_only): no runtime "
            "verification dispatched.\n"
        )
        return TotalizationResult(classification="exempt")

    contract = _liveness_block(state)
    # Forward-only: no liveness block => legacy/ungated; never gated, never mutated.
    if contract is None:
        sys.stderr.write(
            "[runtime-totalization] no liveness block; feature is ungated "
            "(forward-only).\n"
        )
        return TotalizationResult(classification="ungated")

    # AC-10: warn-and-skip on a higher-than-known liveness schema_version.
    schema_version = contract.get("schema_version", KNOWN_LIVENESS_SCHEMA_VERSION)
    if isinstance(schema_version, int) and schema_version > KNOWN_LIVENESS_SCHEMA_VERSION:
        sys.stderr.write(
            f"[runtime-totalization] WARN: liveness schema_version "
            f"{schema_version} > known {KNOWN_LIVENESS_SCHEMA_VERSION}; "
            "warn-and-skip (nothing checked).\n"
        )
        return TotalizationResult(classification="schema_skipped")

    liveness = _as_list(contract.get("liveness"))
    live, deferred = _split_live_and_deferred(liveness)
    deferred_records = _deferred_records(deferred)
    checked_at = _now_iso()

    # AC-5 (verified path): re-run every declared-live AC against the assembled
    # app via the dispatcher. Skip the dispatch entirely when nothing is live.
    if live:
        repo = repo_root_from(feature_dir)
        dispatch = invoke_dispatcher(
            feature_path=str(feature_dir),
            live_ac_ids=[str(_as_dict(entry).get("ac_id", "")) for entry in live],
            cwd=str(repo),
        )
        dispatch_results = _as_list(_as_dict(dispatch).get("results"))
    else:
        dispatch_results = []

    verdicts = _verdicts_for_live_acs(live, dispatch_results, checked_at)
    classification = _classify(verdicts, deferred_records)
    block = _build_block(verdicts, deferred_records, last_run=checked_at)

    _persist(feature_dir, state, block)

    return TotalizationResult(
        classification=classification,
        results=verdicts,
        deferred=deferred_records,
        persisted_block=block,
    )


def _load_git_tags() -> ModuleType:
    """Load scripts/git_tags.py (the append-only tag helper) as a module.

    The skills invoke git_tags via absolute path, so there is no installable
    package to import from; we load the sibling script by file location, the
    same pattern the tests use.
    """
    script = Path(__file__).resolve().parent / "git_tags.py"
    spec = importlib.util.spec_from_file_location("git_tags", script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load git_tags helper from {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@contextlib.contextmanager
def _chdir(target: Path) -> Iterator[None]:
    """Temporarily change cwd (git_tags writes tags in the process cwd)."""
    previous = Path.cwd()
    os.chdir(target)
    try:
        yield
    finally:
        os.chdir(previous)


def _feature_id(feature_dir: Path, state: dict[str, object]) -> str:
    """Derive the tag-namespace feature id: state feature_id, else dir basename."""
    declared = state.get("feature_id")
    if isinstance(declared, str) and declared.strip():
        return declared.strip()
    return feature_dir.resolve().name


def _existing_milestone_sequences(repo: Path, feature_id: str) -> list[int]:
    """Return the numeric <NNN> sequences already used for this feature."""
    refglob = f"{ETC_TAG_REFGLOB}/{feature_id}/{MILESTONE_SEGMENT}/*"
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo), "for-each-ref", "--format=%(refname:short)", refglob],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (subprocess.TimeoutExpired, OSError):
        return []
    if completed.returncode != 0:
        return []
    sequences: list[int] = []
    for line in completed.stdout.splitlines():
        leaf = line.strip().rsplit("/", 1)[-1]
        if leaf.isdigit():
            sequences.append(int(leaf))
    return sequences


def _next_milestone_tag(repo: Path, feature_id: str) -> str:
    """Compute the next append-only milestone tag name (zero-padded sequence)."""
    used = _existing_milestone_sequences(repo, feature_id)
    nxt = (max(used) + 1) if used else MILESTONE_SEQUENCE_START
    sequence = str(nxt).zfill(MILESTONE_SEQUENCE_WIDTH)
    return f"etc/feature/{feature_id}/{MILESTONE_SEGMENT}/{sequence}"


def _set_terminal_tag(feature_dir: Path, terminal_tag: str) -> None:
    """Merge-preserve write of build.runtime_verification.terminal_tag."""
    state = read_state(feature_dir)
    build = _as_dict(state.get("build"))
    verification = _as_dict(build.get("runtime_verification"))
    verification["terminal_tag"] = terminal_tag
    build["runtime_verification"] = verification
    state["build"] = build
    write_state(feature_dir, state)


def _route_milestone(feature_dir: Path, result: TotalizationResult) -> int:
    """deferred_present: write the milestone tag, set terminal_tag, proceed.

    A deferred outcome is done-as-MILESTONE, not a clean release. We write the
    append-only ``etc/feature/<id>/milestone/<NNN>`` tag and record it as the
    terminal tag so /build Step 7c (task 006) SKIPS the clean release tag.
    Exit 0: a milestone is a legal terminal, not a failure.
    """
    state = read_state(feature_dir)
    feature_id = _feature_id(feature_dir, state)
    repo = repo_root_from(feature_dir)
    milestone_tag = _next_milestone_tag(repo, feature_id)

    git_tags = _load_git_tags()
    with _chdir(repo):
        written = git_tags.write_tag(milestone_tag)
    if not written:
        sys.stderr.write(
            f"[runtime-totalization] WARN: milestone tag {milestone_tag} could not "
            "be written (non-git dir / no HEAD); terminal_tag left unset.\n"
        )
        return EXIT_PROCEED

    _set_terminal_tag(feature_dir, milestone_tag)
    deferred_ids = ", ".join(d["ac_id"] for d in result.deferred) or "(none named)"
    sys.stdout.write(
        f"DONE AS MILESTONE: {milestone_tag}\n"
        f"  Deferred outcomes (non-empty reason, legal): {deferred_ids}\n"
        "  Clean release tag NOT written — a deferred outcome going live later "
        "cuts a new clean release.\n"
    )
    return EXIT_PROCEED


def _report_hard_block(feature_dir: Path, result: TotalizationResult) -> int:
    """live_failure: structured exit-2 report naming the failing ACs + evidence."""
    failing = [v for v in result.results if v.status in ("fail", "no-test")]
    sys.stdout.write("RUNTIME VERIFICATION FAILED\n\n")
    sys.stdout.write(
        "The following declared-live user-outcome ACs did not pass at the "
        "authoritative release re-run:\n"
    )
    for verdict in failing:
        sys.stdout.write(
            f"  {verdict.ac_id}  [{verdict.status}]  {verdict.evidence}\n"
        )
    sys.stdout.write(
        "\nA clean release tag means behavioral completeness. No tag was "
        "written and the feature was NOT moved to shipped/.\n\n"
        "Resolution:\n"
        "  A) Fix the implementation so each live AC's runtime test passes, then "
        "re-run /build Step 7.6.\n"
        "  B) If the outcome is intentionally not live yet, declare it deferred "
        f"(live_at: deferred + a non-empty reason) in\n     {feature_dir}/state.yaml "
        "under spec_phase.contract_completeness.liveness — it then routes to a "
        "milestone tag instead of blocking.\n"
    )
    return EXIT_HARD_BLOCK


def _route(feature_dir: Path, result: TotalizationResult) -> int:
    """Map an overall classification to a terminal tag + process exit code.

    Task-006 contract: a null/absent terminal_tag tells Step 7c to write the
    clean release tag; a ``.../milestone/<NNN>`` value tells it to skip (the
    milestone is already the terminal tag). Exit 0 = proceed, exit 2 = block.
    """
    if result.classification == "live_failure":
        return _report_hard_block(feature_dir, result)
    if result.classification == "deferred_present":
        return _route_milestone(feature_dir, result)
    # all_verified / exempt / schema_skipped / ungated / empty: clean release
    # is allowed; leave terminal_tag null so Step 7c writes the release tag.
    return EXIT_PROCEED


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        sys.stderr.write(__doc__ or "")
        return EXIT_USAGE_ERROR

    feature_dir = Path(argv[1])
    if not feature_dir.is_dir():
        sys.stderr.write(f"ERROR: feature_dir not found: {feature_dir}\n")
        return EXIT_USAGE_ERROR

    result = totalize(feature_dir)
    sys.stderr.write(
        f"[runtime-totalization] classification: {result.classification}\n"
    )
    return _route(feature_dir, result)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
