"""Tests for scripts/baseline.py — architecture-baseline core.

Covers the three task-001 acceptance criteria for the brownfield
architecture-baseline feature (F-2026-06-10):

  AC-1  validate enforces SCHEMA_VERSION/REQUIRED_FIELDS, rejects unknown
        top-level fields, warn-and-skips a future schema_version, and pins
        the closed enums for status / claim classification / confidence
        score (per design.md Data Model).
  AC-2  `status <repo_root>` prints exactly one token from
        {missing, unratified, ratified, malformed} with exit 0 when
        evaluable, 1 on IO error; a subprocess test runs from an unrelated
        cwd; unknown stored values are reported as `malformed`, never
        truthy/falsy coerced.
  AC-3  all writes are atomic (tempfile + os.replace) and free-form strings
        are sanitized at the capture site (control chars stripped, length
        capped); both are pinned.

Module under test exposes (in-process contract used by these tests and by
later-wave subcommands):
    - SCHEMA_VERSION (int)
    - REQUIRED_FIELDS (tuple[str, ...])
    - LEGAL_STATUSES / LEGAL_CLASSIFICATIONS / LEGAL_CONFIDENCE_SCORES (frozenset)
    - BASELINE_RELATIVE_PATH (Path) — `.etc_sdlc/architecture-baseline.yaml`
    - load(path) -> dict | None        (warn-and-skip future schema_version)
    - validate_schema(d) -> None
    - status_token(repo_root) -> str
    - sanitize_freeform(value, *, max_len) -> str
    - atomic_dump(path, data) -> None

`load` returns None when schema_version is greater than the supported
version (warn-and-skip). All other malformed input raises ValueError with a
descriptive message. The CLI is the runtime contract exercised by the
subprocess tests; the in-process helpers are the contract for tests and for
later waves (init / ratify / append-rule / render-doc / sync-seams) that
compose load + validate + atomic_dump.
"""

from __future__ import annotations

import importlib.util
import logging
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "baseline.py"


def _load_module() -> ModuleType:
    """Import scripts/baseline.py as a module.

    `scripts/` is not a Python package, so we load the file directly via
    importlib — mirrors test_value_hypothesis.py and test_layer_review.py.
    """
    spec = importlib.util.spec_from_file_location("baseline", MODULE_PATH)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {MODULE_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["baseline"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def bl() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


def _valid_baseline() -> dict:
    """Construct a fully-populated, schema-valid v1 baseline dict.

    Mirrors the design.md Data Model example for
    `.etc_sdlc/architecture-baseline.yaml` (unratified shape). Later-wave
    tests reuse this builder and flip individual fields.
    """
    return {
        "schema_version": 1,
        "status": "unratified",
        "ratified_by": None,
        "ratified_at": None,
        "confidence": {
            "score": "low",
            "inputs": {
                "competing_pattern_concerns": 4,
                "claims": {
                    "verified": 9,
                    "stale": 2,
                    "aspirational": 1,
                    "contradicted": 1,
                },
                "unresolved_seams": 1,
                "stalled_migration_signals": 3,
            },
        },
        "inventory": [
            {
                "path": "docs/folder-structure.md",
                "type": "convention-doc",
                "last_modified": "2025-11-04",
            }
        ],
        "claims": [
            {
                "id": "CL-001",
                "source": "docs/folder-structure.md",
                "claim": "Data-access libraries live at libs/<scope>/data-access",
                "classification": "VERIFIED",
                "evidence": "libs/people/data-access exists; 2 counterexamples",
                "resolution": None,
            }
        ],
        "exemplars": [],
        "do_not_copy": [],
        "rules": [],
        "seams": [],
    }


def _write_baseline(repo_root: Path, data: dict) -> Path:
    """Write a baseline dict to <repo_root>/.etc_sdlc/architecture-baseline.yaml."""
    path = repo_root / ".etc_sdlc" / "architecture-baseline.yaml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


# ── AC-1: schema constants and closed enums ─────────────────────────────


class TestSchemaConstants:
    """The public schema surface later waves and the schema hook key on."""

    def test_should_pin_schema_version_to_one(self, bl: ModuleType) -> None:
        assert bl.SCHEMA_VERSION == 1

    def test_should_declare_required_top_level_fields(self, bl: ModuleType) -> None:
        assert set(bl.REQUIRED_FIELDS) == {
            "schema_version",
            "status",
            "confidence",
            "inventory",
            "claims",
            "rules",
            "seams",
        }

    def test_should_pin_closed_status_enum(self, bl: ModuleType) -> None:
        assert bl.LEGAL_STATUSES == frozenset({"unratified", "ratified"})

    def test_should_pin_closed_claim_classification_enum(self, bl: ModuleType) -> None:
        assert bl.LEGAL_CLASSIFICATIONS == frozenset(
            {"VERIFIED", "STALE", "ASPIRATIONAL", "CONTRADICTED"}
        )

    def test_should_pin_closed_confidence_score_enum(self, bl: ModuleType) -> None:
        assert bl.LEGAL_CONFIDENCE_SCORES == frozenset({"low", "medium", "high"})


# ── AC-1: validate_schema / load ────────────────────────────────────────


class TestValidateSchema:
    """Schema enforcement per design.md Data Model invariants."""

    def test_should_pass_when_baseline_is_well_formed(self, bl: ModuleType) -> None:
        bl.validate_schema(_valid_baseline())

    def test_should_raise_when_required_field_is_missing(self, bl: ModuleType) -> None:
        bad = _valid_baseline()
        del bad["confidence"]

        with pytest.raises(ValueError, match="confidence"):
            bl.validate_schema(bad)

    def test_should_raise_when_unknown_top_level_field_present(self, bl: ModuleType) -> None:
        bad = _valid_baseline()
        bad["surprise"] = "not in the schema"

        with pytest.raises(ValueError, match="unknown top-level field"):
            bl.validate_schema(bad)

    def test_should_raise_when_input_is_not_a_mapping(self, bl: ModuleType) -> None:
        with pytest.raises(ValueError, match="mapping"):
            bl.validate_schema(["not", "a", "mapping"])  # type: ignore[arg-type]

    def test_should_raise_when_status_is_not_a_legal_value(self, bl: ModuleType) -> None:
        bad = _valid_baseline()
        bad["status"] = "frozen"

        with pytest.raises(ValueError, match="status"):
            bl.validate_schema(bad)

    def test_should_raise_when_confidence_score_is_not_a_legal_value(self, bl: ModuleType) -> None:
        bad = _valid_baseline()
        bad["confidence"]["score"] = "stratospheric"

        with pytest.raises(ValueError, match="confidence"):
            bl.validate_schema(bad)

    def test_should_raise_when_claim_classification_is_not_a_legal_value(
        self, bl: ModuleType
    ) -> None:
        bad = _valid_baseline()
        bad["claims"][0]["classification"] = "MAYBE"

        with pytest.raises(ValueError, match="classification"):
            bl.validate_schema(bad)

    def test_should_raise_when_ratified_without_ratified_by(self, bl: ModuleType) -> None:
        # design invariant: ratified_by/ratified_at non-null iff status ratified
        bad = _valid_baseline()
        bad["status"] = "ratified"

        with pytest.raises(ValueError, match="ratified"):
            bl.validate_schema(bad)

    def test_should_pass_when_ratified_with_attestation(self, bl: ModuleType) -> None:
        good = _valid_baseline()
        good["status"] = "ratified"
        good["ratified_by"] = "jason"
        good["ratified_at"] = "2026-06-11T00:00:00Z"

        bl.validate_schema(good)

    def test_should_raise_when_schema_version_is_not_an_integer(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "architecture-baseline.yaml"
        bad = _valid_baseline()
        bad["schema_version"] = "1"
        path.write_text(yaml.safe_dump(bad, sort_keys=False), encoding="utf-8")

        with pytest.raises(ValueError, match="schema_version"):
            bl.load(path)


class TestLoad:
    """File-level load behaviour: round trip, errors, warn-and-skip."""

    def test_should_round_trip_when_baseline_is_well_formed(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "architecture-baseline.yaml"
        baseline = _valid_baseline()
        path.write_text(yaml.safe_dump(baseline, sort_keys=False), encoding="utf-8")

        assert bl.load(path) == baseline

    def test_should_raise_when_file_is_missing(self, bl: ModuleType, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="not found"):
            bl.load(tmp_path / "nope.yaml")

    def test_should_raise_when_yaml_is_malformed(self, bl: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "architecture-baseline.yaml"
        path.write_text("status: [unratified\n", encoding="utf-8")

        with pytest.raises(ValueError, match="malformed YAML"):
            bl.load(path)

    def test_should_use_safe_loader_when_parsing_yaml(self, bl: ModuleType, tmp_path: Path) -> None:
        # A YAML payload that, under the unsafe loader, would execute code.
        path = tmp_path / "architecture-baseline.yaml"
        unsafe_tag = "!!python/object/apply:" + "subprocess.getoutput"
        path.write_text(f"status: {unsafe_tag} ['echo pwned']\n", encoding="utf-8")

        with pytest.raises(ValueError):
            bl.load(path)

    def test_should_return_none_and_warn_when_schema_version_is_future(
        self, bl: ModuleType, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        path = tmp_path / "architecture-baseline.yaml"
        future = _valid_baseline()
        future["schema_version"] = 99
        path.write_text(yaml.safe_dump(future, sort_keys=False), encoding="utf-8")

        with caplog.at_level(logging.WARNING):
            result = bl.load(path)

        assert result is None
        assert any("99" in record.message for record in caplog.records), (
            f"expected a warning citing schema_version=99; got {[r.message for r in caplog.records]}"
        )


# ── AC-2: status_token (in-process) + status subcommand (subprocess) ─────


class TestStatusToken:
    """The four-token status contract; callers branch on the TOKEN."""

    def test_should_return_missing_when_no_baseline_file(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        assert bl.status_token(tmp_path) == "missing"

    def test_should_return_unratified_when_baseline_unratified(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        _write_baseline(tmp_path, _valid_baseline())

        assert bl.status_token(tmp_path) == "unratified"

    def test_should_return_ratified_when_baseline_ratified(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        ratified = _valid_baseline()
        ratified["status"] = "ratified"
        ratified["ratified_by"] = "jason"
        ratified["ratified_at"] = "2026-06-11T00:00:00Z"
        _write_baseline(tmp_path, ratified)

        assert bl.status_token(tmp_path) == "ratified"

    def test_should_return_malformed_when_required_field_missing(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        bad = _valid_baseline()
        del bad["confidence"]
        _write_baseline(tmp_path, bad)

        assert bl.status_token(tmp_path) == "malformed"

    def test_should_return_malformed_when_yaml_is_unparseable(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / ".etc_sdlc" / "architecture-baseline.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("status: [unratified\n", encoding="utf-8")

        assert bl.status_token(tmp_path) == "malformed"

    def test_should_return_malformed_when_stored_status_is_unknown_value(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        # Unknown stored status must NOT be coerced truthy/falsy — it is a
        # schema violation and therefore `malformed` (AC-2 explicit clause).
        bad = _valid_baseline()
        bad["status"] = "totally-bogus"
        _write_baseline(tmp_path, bad)

        assert bl.status_token(tmp_path) == "malformed"


class TestStatusSubcommand:
    """End-to-end subprocess tests of `baseline.py status`.

    Run from an unrelated tmp cwd to pin the no-import-tricks contract and
    the exit-code semantics skills key on (exit 0 when evaluable, token on
    stdout; exit 1 on IO error).
    """

    def test_should_print_unratified_token_from_unrelated_cwd(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        _write_baseline(repo_root, _valid_baseline())
        alien_cwd = tmp_path / "elsewhere"
        alien_cwd.mkdir()

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "status", str(repo_root)],
            cwd=alien_cwd,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"expected exit 0; got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert result.stdout.strip() == "unratified"

    def test_should_print_missing_token_with_exit_zero_when_no_baseline(
        self, tmp_path: Path
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "status", str(tmp_path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "missing"

    def test_should_print_malformed_token_with_exit_zero_when_schema_broken(
        self, tmp_path: Path
    ) -> None:
        bad = _valid_baseline()
        del bad["confidence"]
        _write_baseline(tmp_path, bad)

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "status", str(tmp_path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0
        assert result.stdout.strip() == "malformed"

    def test_should_exit_one_when_repo_root_is_not_a_directory(self, tmp_path: Path) -> None:
        # An IO error (repo_root points at a file, not a dir) is the exit-1
        # could-not-evaluate path, distinct from the `missing` token.
        not_a_dir = tmp_path / "afile"
        not_a_dir.write_text("x", encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "status", str(not_a_dir)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, (
            f"expected exit 1 on IO error; got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )


# ── AC-1/AC-2: validate subcommand (subprocess) ─────────────────────────


class TestValidateSubcommand:
    """`baseline.py validate <path>` exit-code contract (0/1/2)."""

    def test_should_exit_zero_when_baseline_valid_from_unrelated_cwd(self, tmp_path: Path) -> None:
        repo_root = tmp_path / "repo"
        path = _write_baseline(repo_root, _valid_baseline())
        alien_cwd = tmp_path / "elsewhere"
        alien_cwd.mkdir()

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "validate", str(path)],
            cwd=alien_cwd,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"expected exit 0; got {result.returncode}; stderr={result.stderr!r}"
        )

    def test_should_exit_one_when_baseline_file_missing(self, tmp_path: Path) -> None:
        missing = tmp_path / "architecture-baseline.yaml"

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "validate", str(missing)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1

    def test_should_exit_two_and_name_field_when_schema_violated(self, tmp_path: Path) -> None:
        path = tmp_path / "architecture-baseline.yaml"
        bad = _valid_baseline()
        del bad["confidence"]
        path.write_text(yaml.safe_dump(bad, sort_keys=False), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "validate", str(path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 2, (
            f"expected exit 2 on schema violation; got {result.returncode}; "
            f"stderr={result.stderr!r}"
        )
        assert "confidence" in result.stderr

    def test_should_exit_nonzero_when_subcommand_unknown(self, tmp_path: Path) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "frobnicate"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode != 0


# ── AC-3: sanitization at capture site ──────────────────────────────────


class TestSanitizeFreeform:
    """Free-form strings sanitized at capture: strip control chars, cap len."""

    def test_should_strip_control_characters(self, bl: ModuleType) -> None:
        dirty = "ja\x00so\x1fn\x7f"

        assert bl.sanitize_freeform(dirty, max_len=64) == "jason"

    def test_should_cap_length_to_max_len(self, bl: ModuleType) -> None:
        long_name = "n" * 200

        assert bl.sanitize_freeform(long_name, max_len=64) == "n" * 64

    def test_should_preserve_clean_short_strings(self, bl: ModuleType) -> None:
        assert bl.sanitize_freeform("jason", max_len=64) == "jason"

    def test_should_strip_then_cap_in_that_order(self, bl: ModuleType) -> None:
        # Control chars are removed BEFORE the cap, so they do not consume
        # budget — 64 visible chars survive even when interleaved with junk.
        interleaved = "a\x00" * 100

        assert bl.sanitize_freeform(interleaved, max_len=64) == "a" * 64

    def test_should_apply_name_cap_at_sixty_four_for_attestation(self, bl: ModuleType) -> None:
        # design: names capped at 64; the broader free-form cap is 512.
        assert bl.NAME_MAX_LEN == 64
        assert bl.FREEFORM_MAX_LEN == 512


# ── AC-3: atomic writes ─────────────────────────────────────────────────


class TestAtomicDump:
    """Writes are atomic (tempfile + os.replace) and leave no temp debris."""

    def test_should_write_yaml_that_round_trips(self, bl: ModuleType, tmp_path: Path) -> None:
        path = tmp_path / "nested" / "architecture-baseline.yaml"
        baseline = _valid_baseline()

        bl.atomic_dump(path, baseline)

        assert yaml.safe_load(path.read_text(encoding="utf-8")) == baseline

    def test_should_leave_no_temp_files_behind_on_success(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "architecture-baseline.yaml"

        bl.atomic_dump(path, _valid_baseline())

        leftovers = [p.name for p in tmp_path.iterdir() if p.name != path.name]
        assert leftovers == [], f"temp debris left behind: {leftovers}"

    def test_should_use_os_replace_for_the_final_rename(
        self, bl: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Pin the atomic-write mechanism: the final publish step must go
        # through os.replace (atomic rename), never a plain write_text.
        path = tmp_path / "architecture-baseline.yaml"
        calls: list[tuple[str, str]] = []
        real_replace = bl.os.replace

        def _spy_replace(src: str, dst: str) -> None:
            calls.append((str(src), str(dst)))
            real_replace(src, dst)

        monkeypatch.setattr(bl.os, "replace", _spy_replace)
        bl.atomic_dump(path, _valid_baseline())

        assert len(calls) == 1, "atomic_dump must publish via exactly one os.replace"
        assert calls[0][1] == str(path)

    def test_should_not_clobber_target_when_serialization_fails(
        self, bl: ModuleType, tmp_path: Path
    ) -> None:
        # An un-serializable value must not corrupt a pre-existing file.
        path = tmp_path / "architecture-baseline.yaml"
        bl.atomic_dump(path, _valid_baseline())
        original = path.read_text(encoding="utf-8")

        with pytest.raises((ValueError, TypeError, yaml.YAMLError)):
            bl.atomic_dump(path, {"bad": object()})

        assert path.read_text(encoding="utf-8") == original
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != path.name]
        assert leftovers == [], f"temp debris left behind: {leftovers}"
