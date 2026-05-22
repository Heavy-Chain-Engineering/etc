"""profiles — F020 profile detection invocation + profiles.lock parsing.

Mirrors install.sh:472-492 (the F020 profile-detection block). Shells
out to `scripts/detect_profiles.py --repo-root <repo> --write-lock`
via subprocess.run with argv-list form (never shell string). Returns
a `ProfileDetectionResult` describing whether detection succeeded and
which profiles were activated, so the caller can emit the matching
✓/⚠ status line in install_steps (task 005).

Low-layer module. Per `standards/architecture/layer-boundaries.md`,
this module MUST NOT import from cli or install_steps.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

_LOCK_RELATIVE_PATH = Path(".etc_sdlc") / "profiles.lock"


@dataclass(frozen=True, slots=True)
class ProfileDetectionResult:
    """Outcome of the F020 detection invocation.

    Attributes:
        ok: True if the detection script exited zero and the lock was
            written. False on any failure mode.
        detected: List of profile names activated (one per non-empty
            line of profiles.lock). Empty list when no profile signals
            present in the repo.
        message: Human-readable detail. Empty on success; non-empty on
            failure (stderr capture or explanatory note).
    """

    ok: bool
    detected: list[str] = field(default_factory=list)
    message: str = ""


def detect_and_write_lock(
    *,
    detect_script: Path,
    repo_root: Path,
) -> ProfileDetectionResult:
    """Run F020 profile detection against `repo_root` and read the lock.

    Mirrors install.sh:472-492. Creates `<repo_root>/.etc_sdlc/` if
    absent (matches the bash `mkdir -p "$LOCK_DIR"`). Invokes the
    `detect_profiles.py` script via subprocess.run with argv list. On
    success, reads the resulting `profiles.lock` and returns the
    sorted profile names (one per line per F020-005). On any failure,
    returns `ok=False` with the stderr text in `message`.

    Args:
        detect_script: Path to `scripts/detect_profiles.py` to invoke.
        repo_root: Repo root passed via `--repo-root` and used to
            locate the resulting `.etc_sdlc/profiles.lock`.

    Returns:
        A `ProfileDetectionResult`.
    """
    lock_dir = repo_root / ".etc_sdlc"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = repo_root / _LOCK_RELATIVE_PATH

    completed = subprocess.run(
        [
            sys.executable,
            str(detect_script),
            "--repo-root",
            str(repo_root),
            "--write-lock",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.returncode != 0:
        message = completed.stderr.strip() or "profile detection failed"
        return ProfileDetectionResult(ok=False, detected=[], message=message)

    detected = _read_lock(lock_path)
    return ProfileDetectionResult(ok=True, detected=detected, message="")


def _read_lock(lock_path: Path) -> list[str]:
    """Read profiles.lock, returning the list of profile names.

    Per F020-005, the lock is plaintext with one profile per line.
    Empty / missing lock => empty list.
    """
    if not lock_path.is_file():
        return []
    text = lock_path.read_text(encoding="utf-8")
    return [line.strip() for line in text.splitlines() if line.strip()]
