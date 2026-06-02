"""Static portability guard for `stat` mtime probes in shell hooks.

HARNESS-FEEDBACK-002: a `stat -f %m … || stat -c %Y …` (BSD-first) probe
silently breaks on GNU/Linux. `-f` is GNU's VALID `--file-system` flag, so on
Linux `stat -f %m` emits filesystem text and does NOT fail cleanly into the
`||` fallback — the GNU `-c %Y` branch is never reached and the captured mtime
is garbage. The reverse order is correct on BOTH platforms because GNU `stat
-c` fails cleanly on macOS (illegal option -> exit 1), falling through to BSD
`-f %m`.

The behavioral hook tests (test_auto_checkpoint_hook,
test_chief_efficiency_officer) pass on macOS regardless of order because macOS
takes the working BSD branch — so they cannot catch a BSD-first reversal on
the dev platform. This static test is platform-independent: it asserts the
ORDER directly, so a regression fails everywhere.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / "hooks"

# The two stat forms that appear in the portable-mtime `||` fallback chain.
_BSD_FORM = re.compile(r"stat\s+-f\s+%m")
_GNU_FORM = re.compile(r"stat\s+-c\s+%Y")


def _probe_lines() -> list[tuple[Path, int, str]]:
    """Every hook line that names BOTH stat forms (the portable-mtime probe)."""
    found: list[tuple[Path, int, str]] = []
    for sh in sorted(HOOKS_DIR.rglob("*.sh")):
        for i, line in enumerate(sh.read_text(encoding="utf-8").splitlines(), 1):
            if _BSD_FORM.search(line) and _GNU_FORM.search(line):
                found.append((sh, i, line))
    return found


def test_should_find_the_known_mtime_probes() -> None:
    """Guard the guard: the three known probe sites must be discoverable.

    If this drops to zero, either the probes were refactored away (update this
    test) or the rglob is broken (fix it) — silence here must not mask a
    regression in the order assertion below.
    """
    probes = _probe_lines()
    assert len(probes) >= 3, (
        f"expected >=3 stat mtime probes in hooks/, found {len(probes)}: "
        f"{[(str(p.relative_to(REPO_ROOT)), n) for p, n, _ in probes]}"
    )


def test_should_put_gnu_stat_form_before_bsd_form_in_every_probe() -> None:
    """GNU `-c %Y` MUST precede BSD `-f %m` in every mtime probe (HF-002).

    The cleanly-failing probe must come first. GNU `stat -c` errors out on
    macOS (exit 1 -> `||` fallthrough); BSD `stat -f` does NOT error on Linux
    (`-f` is `--file-system`), so it must never be first.
    """
    offenders: list[str] = []
    for path, lineno, line in _probe_lines():
        gnu_at = _GNU_FORM.search(line).start()  # type: ignore[union-attr]
        bsd_at = _BSD_FORM.search(line).start()  # type: ignore[union-attr]
        if bsd_at < gnu_at:
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "BSD-first `stat -f %m` probe(s) found — these silently break on "
        "GNU/Linux (HARNESS-FEEDBACK-002). Put `stat -c %Y` first:\n  "
        + "\n  ".join(offenders)
    )
