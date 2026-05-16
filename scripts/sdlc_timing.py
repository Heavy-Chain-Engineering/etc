#!/usr/bin/env python3
"""SDLC feature-ship timing — derive wall-clock velocity from git history.

Reads each `feat(F<NNN>):` shipping commit in the current repo and uses
its commit date as the feature's ship timestamp. Computes inter-feature
gaps (how long between consecutive ships) and rolls them up into
velocity metrics: median, p90, ships-per-week.

Why not phase-tag timestamps:
  The etc harness currently writes every phase tag (spec/done,
  build/phase-N/start, build/phase-N/done, release) at the END of /build
  in a single batch, so all tags for a given feature point to the same
  commit. Phase-tag dates therefore carry zero phase-level signal until
  the harness is changed to write tags progressively (queued as a
  follow-up: phase-progressive tagging).

What IS reliable today: the `feat(F<NNN>):` commit date, which records
the moment the feature actually shipped. From that we get feature
velocity over time — the operator-facing metric that matters most for
the "am I shipping?" question.

Wall-clock only. Operator's active-engagement time (subtracting sleep
gaps) is a separate concern — that's the Chief Efficiency Officer's
data shape, requiring turn-event timestamps, not git history.

Usage:
  sdlc_timing.py                          # all features, summary table
  sdlc_timing.py --feature F017           # one feature, detail
  sdlc_timing.py --since 7d               # features released within last N days/weeks
  sdlc_timing.py --by week                # weekly velocity rollup
  sdlc_timing.py --baseline               # operator's median/p90 inter-ship gap
  sdlc_timing.py --json                   # JSON output for downstream tools

Exit codes:
  0 = success
  1 = usage / IO error / not a git repo
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

FEATURE_TAG_PATTERN = re.compile(r"^etc/feature/(F\d+)/(.+)$")
# Match `feat(F017):` or `feat(F017-slug):` or `fix(F012):` at start of line.
FEAT_COMMIT_PATTERN = re.compile(r"^(?:feat|fix)\((F\d+)[^)]*\)", re.MULTILINE)
# Parse `git show --shortstat` output:
#   " 5 files changed, 100 insertions(+), 20 deletions(-)"
#   " 1 file changed, 3 insertions(+)"        (no deletions case)
#   " 2 files changed, 10 deletions(-)"        (no insertions case)
SHORTSTAT_FILES_PATTERN = re.compile(r"(\d+) files? changed")
SHORTSTAT_INSERTIONS_PATTERN = re.compile(r"(\d+) insertions?\(\+\)")
SHORTSTAT_DELETIONS_PATTERN = re.compile(r"(\d+) deletions?\(-\)")


def git(repo: Path, *args: str) -> str:
    """Run `git -C <repo> <args>` and return stdout (stripped). Raises on
    non-zero exit."""
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed: {result.stderr.strip() or result.stdout.strip()}"
        )
    return result.stdout.strip()


def get_commit_loc(repo: Path, sha: str) -> dict[str, int]:
    """Return {files_changed, insertions, deletions, churn} for a single commit.

    Runs `git show --shortstat --format= <sha>` and parses the shortstat
    output. Returns zeros for any field not present in the output (e.g.,
    a docs-only commit may have no insertions(+) line in some edge cases).

    `churn = insertions + deletions` — the "amount of work done" measure
    that doesn't undercount refactoring (pure insertions does) or ignore
    new code (pure deletions does).
    """
    try:
        output = git(repo, "show", "--shortstat", "--format=", sha)
    except RuntimeError:
        return {"files_changed": 0, "insertions": 0, "deletions": 0, "churn": 0}
    files = SHORTSTAT_FILES_PATTERN.search(output)
    ins = SHORTSTAT_INSERTIONS_PATTERN.search(output)
    dels = SHORTSTAT_DELETIONS_PATTERN.search(output)
    files_n = int(files.group(1)) if files else 0
    ins_n = int(ins.group(1)) if ins else 0
    dels_n = int(dels.group(1)) if dels else 0
    return {
        "files_changed": files_n,
        "insertions": ins_n,
        "deletions": dels_n,
        "churn": ins_n + dels_n,
    }


def list_feature_ships(repo: Path) -> list[dict[str, Any]]:
    """Return a chronologically-sorted list of feature ships.

    Each entry: {feature_id, commit_sha, commit_date, subject,
                 files_changed, insertions, deletions, churn}.

    A ship is detected by a commit whose subject line starts with
    `feat(F<NNN>):` or `fix(F<NNN>):` — the canonical etc shipping-commit
    prefix. We dedupe by feature_id: if a feature has multiple commits
    (e.g., F012 had a fix-up `32cd749`), we keep the EARLIEST as the
    "initial ship" timestamp. Fix-ups don't reset the ship clock.

    LOC fields are populated from `git show --shortstat` per ship commit.
    These represent the INITIAL ship's churn; subsequent fix-up commits
    on the same F<NNN> are NOT included in v1 (would inflate the number
    in a way that conflates initial-ship work vs. follow-up maintenance).
    """
    log_output = git(
        repo,
        "log",
        "--all",
        "--no-merges",
        "--format=%H%x09%cI%x09%s",
    )
    if not log_output:
        return []

    ships_by_id: dict[str, dict[str, Any]] = {}
    for line in log_output.splitlines():
        if not line.strip():
            continue
        try:
            sha, date_str, subject = line.split("\t", 2)
        except ValueError:
            continue
        match = FEAT_COMMIT_PATTERN.match(subject)
        if not match:
            continue
        fid = match.group(1)
        try:
            dt = datetime.fromisoformat(date_str)
        except ValueError:
            continue
        existing = ships_by_id.get(fid)
        # Keep the EARLIEST ship commit for each feature
        if existing is None or dt < existing["commit_date_dt"]:
            ships_by_id[fid] = {
                "feature_id": fid,
                "commit_sha": sha[:7],
                "commit_date": date_str,
                "commit_date_dt": dt,
                "subject": subject,
                # LOC fields populated below after dedupe — one git call per
                # winning ship rather than one per matched commit.
            }

    # Populate LOC for each winning ship (one `git show` per feature)
    for fid, ship in ships_by_id.items():
        # Resolve full sha from the truncated 7-char form
        try:
            full_sha = git(repo, "rev-parse", ship["commit_sha"])
        except RuntimeError:
            full_sha = ship["commit_sha"]
        ship.update(get_commit_loc(repo, full_sha))

    return sorted(ships_by_id.values(), key=lambda s: s["commit_date_dt"])


def list_feature_tags(repo: Path) -> dict[str, list[tuple[str, datetime]]]:
    """Return {feature_id: [(tag_suffix, tag_datetime), ...]}.

    Prefers the annotated tag's `taggerdate` when present, falls back to
    the commit's `committerdate` for legacy lightweight tags. Per-phase
    deltas are measurable when /build creates annotated phase tags at
    wave boundaries (each tag carries its own creation timestamp even if
    multiple phases share one squash commit).
    """
    # Format mirrors scripts/git_tags.py — taggerdate when present, else
    # committerdate. Lightweight tags (pre-progressive-phase-timing) yield
    # an empty taggerdate and fall through to the commit's committerdate.
    fmt = (
        "%(refname:short)\t"
        "%(if)%(taggerdate)%(then)%(taggerdate:iso8601-strict)"
        "%(else)%(committerdate:iso8601-strict)%(end)"
    )
    try:
        raw = git(repo, "for-each-ref", f"--format={fmt}", "refs/tags/etc/feature/")
    except RuntimeError:
        return {}
    if not raw:
        return {}

    out: dict[str, list[tuple[str, datetime]]] = {}
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        tag, date_str = parts
        match = FEATURE_TAG_PATTERN.match(tag)
        if not match:
            continue
        fid, suffix = match.group(1), match.group(2)
        try:
            dt = datetime.fromisoformat(date_str)
        except ValueError:
            continue
        out.setdefault(fid, []).append((suffix, dt))
    return out


def attach_intervals(ships: list[dict[str, Any]]) -> None:
    """Mutate each ship dict to add `interval_from_prev_s` — the gap
    between this ship and the previous one in chronological order. The
    first ship has `interval_from_prev_s = None`."""
    prev_dt: datetime | None = None
    for s in ships:
        cur = s["commit_date_dt"]
        if prev_dt is None:
            s["interval_from_prev_s"] = None
        else:
            s["interval_from_prev_s"] = (cur - prev_dt).total_seconds()
        prev_dt = cur


def feature_title_from_dir(repo: Path, fid: str) -> str:
    """Best-effort feature slug → title from filesystem directories."""
    parents = [
        repo / ".etc_sdlc" / "features",
        repo / ".etc_sdlc" / "features" / "active",
        repo / ".etc_sdlc" / "features" / "shipped",
    ]
    for parent in parents:
        if not parent.is_dir():
            continue
        for child in parent.iterdir():
            if child.is_dir() and child.name.startswith(f"{fid}-"):
                slug = child.name[len(fid) + 1 :]
                return slug.replace("-", " ")
    return ""


def format_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    days = seconds // 86400
    remaining = seconds % 86400
    h = remaining // 3600
    m = (remaining % 3600) // 60
    if days > 0:
        return f"{days}d {h}h" if h else f"{days}d"
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m"


def render_table(ships: list[dict[str, Any]]) -> None:
    """Default summary table: feature ships chronologically + inter-ship gap + LOC."""
    if not ships:
        print("No feat(F<NNN>) shipping commits found in this repo.")
        return

    header = (
        f"{'Feature':<8} {'Title':<40} {'Shipped':<20} {'Gap':<12} "
        f"{'Files':<7} {'+LOC':<7} {'-LOC':<7} {'Churn':<7}"
    )
    print(header)
    print("-" * len(header))
    for s in ships:
        title = s.get("title", "")[:38]
        shipped = s["commit_date"][:19].replace("T", " ")
        gap = format_duration(s["interval_from_prev_s"])
        files = s.get("files_changed", 0)
        ins = s.get("insertions", 0)
        dels = s.get("deletions", 0)
        churn = s.get("churn", 0)
        print(
            f"{s['feature_id']:<8} {title:<40} {shipped:<20} {gap:<12} "
            f"{files:<7} {ins:<7} {dels:<7} {churn:<7}"
        )

    # Aggregates
    intervals = [s["interval_from_prev_s"] for s in ships if s["interval_from_prev_s"]]
    churns = [s.get("churn", 0) for s in ships if s.get("churn", 0) > 0]
    print()
    print(f"Features shipped:        {len(ships)}")
    if intervals:
        print(f"Median inter-ship gap:   {format_duration(statistics.median(intervals))}")
        print(f"p90 inter-ship gap:      {format_duration(_percentile(intervals, 90))}")
    if churns:
        print(f"Median churn per ship:   {int(statistics.median(churns))} LOC")
        print(f"p90 churn per ship:      {int(_percentile(churns, 90))} LOC")
        print(f"Total churn (sum):       {sum(churns)} LOC")
    if len(ships) >= 2:
        first_dt = ships[0]["commit_date_dt"]
        last_dt = ships[-1]["commit_date_dt"]
        span_s = (last_dt - first_dt).total_seconds()
        if span_s > 0:
            ships_per_day = len(ships) / (span_s / 86400)
            ships_per_week = len(ships) / (span_s / 604800)
            print(f"Span:                    {format_duration(span_s)}")
            print(f"Ships per day:           {ships_per_day:.2f}")
            print(f"Ships per week:          {ships_per_week:.2f}")
            if churns:
                churn_per_hour = sum(churns) / (span_s / 3600)
                print(f"Churn per active hour:   {churn_per_hour:.1f} LOC/h (wall-clock)")


def render_detail(s: dict[str, Any], tags: list[tuple[str, datetime]]) -> None:
    """Single-feature detail: ship commit + tag census (with the caveat
    that current harness batches tag-writing so the timestamps collide)."""
    title = s.get("title", "")
    print(f"{s['feature_id']} {title}".rstrip())
    print()
    print(f"  Ship commit:    {s['commit_sha']}")
    print(f"  Ship subject:   {s['subject']}")
    print(f"  Shipped at:     {s['commit_date']}")
    print(f"  Gap from prev:  {format_duration(s.get('interval_from_prev_s'))}")
    print(f"  Files changed:  {s.get('files_changed', 0)}")
    print(f"  Insertions:     +{s.get('insertions', 0)} LOC")
    print(f"  Deletions:      -{s.get('deletions', 0)} LOC")
    print(f"  Churn (total):  {s.get('churn', 0)} LOC")
    print()
    if tags:
        print(f"  Phase tags ({len(tags)} found):")
        for suffix, dt in sorted(tags, key=lambda x: (x[0], x[1])):
            print(f"    {suffix:<28} {dt.isoformat()}")
        # Diagnose collapsed timestamps
        unique_dates = {dt for _, dt in tags}
        if len(unique_dates) == 1 and len(tags) > 1:
            print()
            print(
                "  NOTE: all phase tags share one commit timestamp. The harness"
            )
            print(
                "  currently batches tag-writing at end of /build, so phase-level"
            )
            print(
                "  deltas are unmeasurable from tags alone. Inter-ship gap above"
            )
            print(
                "  is reliable; phase breakdown needs progressive tagging (queued)."
            )


def render_weekly_rollup(ships: list[dict[str, Any]]) -> None:
    """Group ships by ISO week, count per week + total span."""
    if not ships:
        print("No ships.")
        return
    weeks: dict[str, list[dict[str, Any]]] = {}
    for s in ships:
        iso = s["commit_date_dt"].isocalendar()
        key = f"{iso.year}-W{iso.week:02d}"
        weeks.setdefault(key, []).append(s)
    print(f"{'Week':<10} {'Count':<7} {'Features':<60}")
    print("-" * 80)
    for wk in sorted(weeks):
        items = weeks[wk]
        fids = " ".join(s["feature_id"] for s in items)
        print(f"{wk:<10} {len(items):<7} {fids[:58]:<60}")


def render_baseline(ships: list[dict[str, Any]]) -> None:
    """Operator velocity baseline: inter-ship gap percentiles + cadence + LOC."""
    intervals = [s["interval_from_prev_s"] for s in ships if s["interval_from_prev_s"]]
    if not intervals:
        print("Need at least 2 shipped features to compute baseline.")
        return
    print("Operator velocity baseline")
    print()
    print(f"  Features shipped:  {len(ships)}")
    print("  Inter-ship gap:")
    print(f"    median:  {format_duration(statistics.median(intervals))}")
    print(f"    p10:     {format_duration(_percentile(intervals, 10))}")
    print(f"    p50:     {format_duration(_percentile(intervals, 50))}")
    print(f"    p90:     {format_duration(_percentile(intervals, 90))}")
    print(f"    min:     {format_duration(min(intervals))}")
    print(f"    max:     {format_duration(max(intervals))}")

    churns = [s.get("churn", 0) for s in ships if s.get("churn", 0) > 0]
    if churns:
        print()
        print("  Churn per ship (LOC, insertions + deletions):")
        print(f"    median:  {int(statistics.median(churns))} LOC")
        print(f"    p10:     {int(_percentile(churns, 10))} LOC")
        print(f"    p50:     {int(_percentile(churns, 50))} LOC")
        print(f"    p90:     {int(_percentile(churns, 90))} LOC")
        print(f"    min:     {min(churns)} LOC")
        print(f"    max:     {max(churns)} LOC")
        print(f"    sum:     {sum(churns)} LOC (total work shipped)")

    if len(ships) >= 2:
        span = (ships[-1]["commit_date_dt"] - ships[0]["commit_date_dt"]).total_seconds()
        if span > 0:
            print()
            print(f"  Total span:           {format_duration(span)}")
            print(f"  Ships per day:        {len(ships) / (span / 86400):.2f}")
            print(f"  Ships per week:       {len(ships) / (span / 604800):.2f}")
            if churns:
                churn_per_hour = sum(churns) / (span / 3600)
                print(f"  Churn per hour:       {churn_per_hour:.1f} LOC/h (wall-clock)")


def compute_phase_intervals(
    tags_by_feature: dict[str, list[tuple[str, datetime]]],
) -> dict[str, dict[str, float | None]]:
    """For each feature, return {phase_name: seconds_in_phase | None}.

    Phase pairing rules:
      - spec        ← span between earliest 'spec*' tag and earliest tag
                       AFTER it (architect/start or build/phase-0/start).
                       If no later tag exists, returns None.
      - architect   ← architect/done - architect/start (if both present)
      - build/N     ← build/phase-N/done - build/phase-N/start

    Phases with only one of (start, done) are skipped (return None).
    Legacy lightweight tags collapse to the same timestamp and yield 0.0;
    that's correct (the harness wrote them at the same moment) and is what
    the operator will use to identify which features have observable
    phase deltas going forward.
    """
    out: dict[str, dict[str, float | None]] = {}
    for fid, raw_tags in tags_by_feature.items():
        # Index by suffix for direct lookup.
        by_suffix: dict[str, datetime] = {suf: dt for suf, dt in raw_tags}

        phases: dict[str, float | None] = {}

        # ── architect ──
        arch_start = by_suffix.get("architect/start")
        arch_done = by_suffix.get("architect/done")
        if arch_start and arch_done:
            phases["architect"] = (arch_done - arch_start).total_seconds()

        # ── build/phase-N ──
        # Find every "build/phase-K/start" suffix and pair with its done.
        build_phase_pattern = re.compile(r"^build/phase-(\d+)/start$")
        for suffix, dt in raw_tags:
            m = build_phase_pattern.match(suffix)
            if not m:
                continue
            n = m.group(1)
            done = by_suffix.get(f"build/phase-{n}/done")
            if done:
                phases[f"build/phase-{n}"] = (done - dt).total_seconds()

        # ── spec ── (single-point in the legacy shape; span until next phase)
        spec_tag = by_suffix.get("spec") or by_suffix.get("spec/done")
        if spec_tag:
            # The phase boundary AFTER spec is the earliest architect/start
            # or build/phase-0/start, whichever comes first.
            later_candidates = [
                by_suffix.get("architect/start"),
                by_suffix.get("build/phase-0/start"),
            ]
            later = [c for c in later_candidates if c is not None and c > spec_tag]
            if later:
                phases["spec"] = (min(later) - spec_tag).total_seconds()

        out[fid] = phases

    return out


def render_phases(
    ships: list[dict[str, Any]],
    phase_intervals: dict[str, dict[str, float | None]],
) -> None:
    """Per-feature × per-phase elapsed-time table."""
    # Collect every phase name that appears across features (sorted).
    all_phases: set[str] = set()
    for phases in phase_intervals.values():
        all_phases.update(phases.keys())
    phase_order = sorted(all_phases, key=lambda p: (
        0 if p == "spec" else 1 if p == "architect"
        else 2 if p.startswith("build/phase-") else 3,
        p,
    ))

    if not phase_order:
        print("No phase tags found. Run /build with progressive annotated tags")
        print("(scripts/git_tags.py now creates annotated tags as of 2026-05-15)")
        print("for at least one feature to populate this view.")
        return

    header = f"{'Feature':<8} {'Title':<40}"
    for p in phase_order:
        header += f" {p:<14}"
    print(header)
    print("-" * len(header))

    for s in ships:
        fid = s["feature_id"]
        title = (s.get("title") or "")[:38]
        row = f"{fid:<8} {title:<40}"
        for p in phase_order:
            secs = phase_intervals.get(fid, {}).get(p)
            row += f" {format_duration(secs):<14}"
        print(row)

    # Per-phase percentiles across features (when ≥1 feature has measurable
    # data, ignoring zero-duration entries which indicate collapsed legacy tags).
    print()
    print("Per-phase percentiles (across features with measurable, non-zero deltas):")
    print(f"  {'Phase':<18} {'count':<7} {'median':<14} {'p90':<14}")
    for p in phase_order:
        values = [
            secs for f in phase_intervals.values()
            for ph, secs in f.items() if ph == p and secs is not None and secs > 0
        ]
        if not values:
            print(f"  {p:<18} {0:<7} {'—':<14} {'—':<14}")
            continue
        median = _percentile(values, 50)
        p90 = _percentile(values, 90)
        print(
            f"  {p:<18} {len(values):<7} "
            f"{format_duration(median):<14} {format_duration(p90):<14}"
        )


def _percentile(values: list[float], pct: float) -> float:
    """Simple nearest-rank percentile (no interpolation). Adequate for the
    small datasets this script handles."""
    if not values:
        return 0.0
    s = sorted(values)
    k = max(0, min(len(s) - 1, int(round(pct / 100 * (len(s) - 1)))))
    return s[k]


def parse_since(spec: str) -> timedelta:
    """Parse '7d', '2w', '3m' into a timedelta."""
    match = re.match(r"^(\d+)([dwmDWM])$", spec)
    if not match:
        raise ValueError(f"--since must match Nd|Nw|Nm; got {spec!r}")
    n = int(match.group(1))
    unit = match.group(2).lower()
    if unit == "d":
        return timedelta(days=n)
    if unit == "w":
        return timedelta(weeks=n)
    if unit == "m":
        return timedelta(days=n * 30)  # rough; calendar month is variable
    raise ValueError(f"unknown --since unit {unit!r}")


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="SDLC phase timing — measure feature shipping velocity from git tags.",
    )
    parser.add_argument("--feature", help="show details for one feature (e.g., F017)")
    parser.add_argument(
        "--since",
        help="filter to features released within the last duration (e.g., 7d, 2w, 3m)",
    )
    parser.add_argument(
        "--by",
        choices=["feature", "week"],
        default="feature",
        help="aggregation level (default: feature)",
    )
    parser.add_argument(
        "--baseline",
        action="store_true",
        help="show operator velocity baseline (inter-ship gap percentiles)",
    )
    parser.add_argument(
        "--phases",
        action="store_true",
        help="show per-feature × per-phase elapsed time (requires annotated phase tags)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit JSON instead of table",
    )

    try:
        args = parser.parse_args(argv[1:])
    except SystemExit:
        return 1

    repo = Path.cwd()
    try:
        # Walk up to git root if we're inside a subdirectory.
        git_root = git(repo, "rev-parse", "--show-toplevel")
        repo = Path(git_root)
    except RuntimeError as e:
        sys.stderr.write(f"ERROR: not a git repository: {e}\n")
        return 1

    try:
        ships = list_feature_ships(repo)
    except RuntimeError as e:
        sys.stderr.write(f"ERROR: failed to read git history: {e}\n")
        return 1

    for s in ships:
        s["title"] = feature_title_from_dir(repo, s["feature_id"])
    attach_intervals(ships)

    if args.feature:
        matching = [s for s in ships if s["feature_id"] == args.feature]
        if not matching:
            print(f"No feat({args.feature}) commit found.")
            return 0
        tags = list_feature_tags(repo).get(args.feature, [])
        if args.json:
            payload = dict(matching[0])
            payload.pop("commit_date_dt", None)
            payload["phase_tags"] = [
                {"suffix": suf, "commit_date": dt.isoformat()} for suf, dt in tags
            ]
            print(json.dumps(payload, indent=2))
        else:
            render_detail(matching[0], tags)
        return 0

    if args.since:
        try:
            window = parse_since(args.since)
        except ValueError as e:
            sys.stderr.write(f"ERROR: {e}\n")
            return 1
        cutoff = datetime.now(timezone.utc) - window
        ships = [s for s in ships if s["commit_date_dt"] >= cutoff]
        # Re-attach intervals on the filtered set
        attach_intervals(ships)

    if args.phases:
        tags_by_feature = list_feature_tags(repo)
        phase_intervals = compute_phase_intervals(tags_by_feature)
        if args.json:
            phase_payload = {
                fid: {ph: secs for ph, secs in phases.items()}
                for fid, phases in phase_intervals.items()
            }
            print(json.dumps(phase_payload, indent=2, sort_keys=True))
            return 0
        render_phases(ships, phase_intervals)
        return 0

    if args.json:
        ship_payload: list[dict[str, Any]] = []
        for s in ships:
            entry = dict(s)
            entry.pop("commit_date_dt", None)
            ship_payload.append(entry)
        print(json.dumps(ship_payload, indent=2))
        return 0

    if args.baseline:
        render_baseline(ships)
    elif args.by == "week":
        render_weekly_rollup(ships)
    else:
        render_table(ships)

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
