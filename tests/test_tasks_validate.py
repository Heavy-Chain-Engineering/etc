"""Tests for `tasks.py validate` subcommand.

Covers AC-013, BR-011, security considerations 1 and 2 of the
metrics-and-release-notes feature:

- CLI argument validation: ``feature_id`` matches ``^F\\d{3}$``;
  ``--measured`` parses as int or float; ``--evidence`` either an http(s)
  URL or a path that resolves inside the project working tree.
- Status transitions per ``predicted.direction``:
    * ``decrease`` — measured <= threshold => validated, else invalidated
    * ``increase`` — measured >= threshold => validated, else invalidated
- ``validation.measured_at`` set to a current ISO-8601 UTC timestamp,
  ``validation.measured_value`` to the parsed numeric value,
  ``validation.evidence`` to the canonicalized path or URL string.
- Atomic write semantics: a temp file in the same directory is renamed
  over the target. Temp file is cleaned up on success and on simulated
  mid-write failure (the original file is never partially overwritten).
"""

from __future__ import annotations

import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest
import yaml

TASKS_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "tasks.py"


def _run_validate(
    project_root: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    """Invoke ``tasks.py validate ...`` with ``project_root`` as cwd."""
    return subprocess.run(
        ["python3", str(TASKS_SCRIPT), "validate", *args],
        capture_output=True,
        text=True,
        cwd=str(project_root),
        timeout=10,
    )


def _write_hypothesis(
    project_root: Path,
    feature_id: str,
    slug: str,
    direction: str,
    threshold: float | int,
    status: str = "pending",
) -> Path:
    """Create ``.etc_sdlc/features/<F>-<slug>/value-hypothesis.yaml``."""
    feature_dir = project_root / ".etc_sdlc" / "features" / f"{feature_id}-{slug}"
    feature_dir.mkdir(parents=True, exist_ok=True)
    path = feature_dir / "value-hypothesis.yaml"
    body = {
        "schema_version": 1,
        "feature_id": feature_id,
        "author_role": "Engineer",
        "who": "Reviewers handling DRNSG filings.",
        "current_cost": "Average 4 hours per filing review.",
        "predicted": {
            "metric": "review_minutes",
            "direction": direction,
            "threshold": threshold,
            "window_days": 30,
        },
        "how_we_know": "Time-and-motion sample of 20 filings post-ship.",
        "status": status,
        "validation": {
            "measured_at": None,
            "measured_value": None,
            "evidence": None,
        },
    }
    path.write_text(
        yaml.safe_dump(body, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )
    return path


def _read_hypothesis(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ── CLI argument validation ────────────────────────────────────────────


class TestArgumentValidation:
    def test_should_reject_when_feature_id_does_not_match_regex(
        self, tmp_path: Path
    ) -> None:
        result = _run_validate(
            tmp_path,
            "F12",  # too few digits
            "--measured",
            "42",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "feature" in combined.lower() or "F\\d{3}" in combined or "F<NNN>" in combined

    def test_should_reject_when_feature_id_has_extra_characters(
        self, tmp_path: Path
    ) -> None:
        result = _run_validate(
            tmp_path,
            "F042x",
            "--measured",
            "42",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode != 0

    def test_should_reject_when_measured_is_not_numeric(
        self, tmp_path: Path
    ) -> None:
        _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "not-a-number",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "measured" in combined.lower() or "numeric" in combined.lower()

    def test_should_reject_when_evidence_path_escapes_project_tree(
        self, tmp_path: Path
    ) -> None:
        _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        # An absolute path that resolves outside tmp_path.
        outside = tmp_path.parent / "outside-evidence.txt"
        outside.write_text("hi", encoding="utf-8")

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            str(outside),
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert (
            "outside" in combined.lower()
            or "escape" in combined.lower()
            or "project" in combined.lower()
        )

    def test_should_reject_when_evidence_path_traverses_with_dot_dot(
        self, tmp_path: Path
    ) -> None:
        _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            "../outside.txt",
        )

        assert result.returncode != 0

    def test_should_reject_when_no_value_hypothesis_for_feature(
        self, tmp_path: Path
    ) -> None:
        # No feature directory created at all.
        result = _run_validate(
            tmp_path,
            "F999",
            "--measured",
            "42",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode != 0
        combined = result.stdout + result.stderr
        assert "F999" in combined or "not found" in combined.lower()


# ── status transitions ────────────────────────────────────────────────


class TestDecreaseDirection:
    def test_should_set_status_validated_when_measured_at_or_below_threshold(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "55",
            "--evidence",
            "https://example.com/report.pdf",
        )

        assert result.returncode == 0, result.stdout + result.stderr
        loaded = _read_hypothesis(path)
        assert loaded["status"] == "validated"
        assert loaded["validation"]["measured_value"] == 55
        assert loaded["validation"]["evidence"] == "https://example.com/report.pdf"

    def test_should_set_status_validated_when_measured_equals_threshold(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "60",
            "--evidence",
            "https://example.com/report.pdf",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["status"] == "validated"

    def test_should_set_status_invalidated_when_measured_above_threshold(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "75",
            "--evidence",
            "https://example.com/report.pdf",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["status"] == "invalidated"
        assert loaded["validation"]["measured_value"] == 75


class TestIncreaseDirection:
    def test_should_set_status_validated_when_measured_at_or_above_threshold(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F010", "lift", "increase", 0.30)

        result = _run_validate(
            tmp_path,
            "F010",
            "--measured",
            "0.42",
            "--evidence",
            "https://example.com/report.pdf",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["status"] == "validated"
        assert loaded["validation"]["measured_value"] == pytest.approx(0.42)

    def test_should_set_status_invalidated_when_measured_below_threshold(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F010", "lift", "increase", 0.30)

        result = _run_validate(
            tmp_path,
            "F010",
            "--measured",
            "0.15",
            "--evidence",
            "https://example.com/report.pdf",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["status"] == "invalidated"


# ── validation.measured_at and measured_value ─────────────────────────


class TestValidationFields:
    def test_should_set_measured_at_to_current_iso_8601_utc_timestamp(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        before = datetime.now(timezone.utc)
        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            "https://example.com/report",
        )
        after = datetime.now(timezone.utc)

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        measured_at = loaded["validation"]["measured_at"]
        assert isinstance(measured_at, str)
        # ISO-8601 UTC: ends with Z or +00:00
        assert measured_at.endswith("Z") or measured_at.endswith("+00:00")

        normalized = measured_at.replace("Z", "+00:00")
        parsed = datetime.fromisoformat(normalized)
        # Allow a generous 10-second window around the call.
        assert abs((parsed - before).total_seconds()) < 10
        assert abs((parsed - after).total_seconds()) < 10

    def test_should_parse_measured_as_int_when_value_has_no_decimal_point(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["validation"]["measured_value"] == 42
        assert isinstance(loaded["validation"]["measured_value"], int)

    def test_should_parse_measured_as_float_when_value_has_decimal_point(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42.5",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["validation"]["measured_value"] == pytest.approx(42.5)
        assert isinstance(loaded["validation"]["measured_value"], float)


# ── evidence canonicalization ─────────────────────────────────────────


class TestEvidenceCanonicalization:
    def test_should_accept_http_url_as_evidence_unchanged(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            "http://example.com/report.pdf",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["validation"]["evidence"] == "http://example.com/report.pdf"

    def test_should_accept_https_url_as_evidence_unchanged(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            "https://example.com/report.pdf",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        assert loaded["validation"]["evidence"] == "https://example.com/report.pdf"

    def test_should_canonicalize_relative_path_inside_project(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        evidence_file = tmp_path / "evidence" / "report.txt"
        evidence_file.parent.mkdir(parents=True, exist_ok=True)
        evidence_file.write_text("data", encoding="utf-8")

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            "evidence/report.txt",
        )

        assert result.returncode == 0
        loaded = _read_hypothesis(path)
        # Path canonicalized against project root via Path.resolve().
        # tmp_path may itself be a symlink (macOS /var -> /private/var), so
        # we compare against tmp_path.resolve() to mirror the implementation.
        expected = str((tmp_path.resolve() / "evidence" / "report.txt"))
        assert loaded["validation"]["evidence"] == expected


# ── atomic write semantics ────────────────────────────────────────────


class TestAtomicWrite:
    def test_should_clean_up_temp_file_on_success(self, tmp_path: Path) -> None:
        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)

        result = _run_validate(
            tmp_path,
            "F042",
            "--measured",
            "42",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode == 0
        # No leftover temp files in the feature directory.
        leftovers = [
            p
            for p in path.parent.iterdir()
            if p != path
            and (
                p.name.startswith(".value-hypothesis")
                or p.name.startswith("value-hypothesis.yaml.tmp")
                or re.match(r"value-hypothesis.*\.tmp", p.name)
            )
        ]
        assert leftovers == [], f"unexpected temp files: {leftovers}"

    def test_should_preserve_original_file_when_write_fails_mid_stream(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Simulate mid-write failure by importing the module and patching
        ``Path.replace`` to raise. The temp file must be cleaned up and
        the target file must remain at its original contents.
        """
        import importlib.util
        import sys

        repo_root = Path(__file__).resolve().parent.parent
        spec = importlib.util.spec_from_file_location(
            "tasks_for_atomic_test", repo_root / "scripts" / "tasks.py"
        )
        assert spec is not None and spec.loader is not None
        tasks_mod = importlib.util.module_from_spec(spec)
        sys.modules["tasks_for_atomic_test"] = tasks_mod
        spec.loader.exec_module(tasks_mod)

        path = _write_hypothesis(tmp_path, "F042", "demo", "decrease", 60)
        original_bytes = path.read_bytes()

        # Patch Path.replace globally to simulate a rename failure right
        # after the temp file has been written. We restore via monkeypatch.
        def boom(self: Path, target: Path) -> Path:  # noqa: ARG001
            raise OSError("simulated rename failure")

        monkeypatch.setattr(Path, "replace", boom)

        # Drive the validate path in-process so the patched Path.replace
        # actually applies (subprocess wouldn't see the patch).
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit):
            tasks_mod.cmd_validate(
                tmp_path,
                feature_id="F042",
                measured="42",
                evidence="https://example.com/report",
            )

        # Original file is intact.
        assert path.read_bytes() == original_bytes

        # No leftover temp files.
        leftovers = [p for p in path.parent.iterdir() if p != path]
        assert leftovers == [], f"unexpected leftovers after failure: {leftovers}"


# ── feature directory discovery ──────────────────────────────────────


class TestFeatureDirectoryDiscovery:
    def test_should_find_feature_directory_when_slug_is_arbitrary(
        self, tmp_path: Path
    ) -> None:
        path = _write_hypothesis(
            tmp_path, "F123", "metrics-and-release-notes", "decrease", 60
        )

        result = _run_validate(
            tmp_path,
            "F123",
            "--measured",
            "10",
            "--evidence",
            "https://example.com/report",
        )

        assert result.returncode == 0, result.stdout + result.stderr
        loaded = _read_hypothesis(path)
        assert loaded["status"] == "validated"
