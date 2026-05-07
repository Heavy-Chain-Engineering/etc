"""Tests for scripts/value_hypothesis.py.

Covers BR-005 (mandatory fields), BR-006 (schema versioning),
BR-011 (status state machine), AC-004, AC-005, AC-006, AC-014.

Module under test exposes:
    - load(path: Path) -> dict | None
    - dump(path: Path, hypothesis: dict) -> None
    - validate_schema(d: dict) -> None
    - transition_status(d: dict, new_status: str, evidence: dict | None = None) -> dict
    - SCHEMA_VERSION (int)
    - REQUIRED_FIELDS (tuple[str, ...])

`load` returns None when schema_version is greater than the supported
version (warn-and-skip per BR-006/AC-006). All other malformed input
raises ValueError with a descriptive message.
"""

from __future__ import annotations

import importlib.util
import json
import logging
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "value_hypothesis.py"


def _load_module() -> ModuleType:
    """Import scripts/value_hypothesis.py as a module.

    `scripts/` is not a Python package, so we load the file directly via
    importlib. Mirrors the pattern used elsewhere in this test suite
    when importing from `scripts/`.
    """
    spec = importlib.util.spec_from_file_location("value_hypothesis", MODULE_PATH)
    if spec is None or spec.loader is None:
        msg = f"Cannot load module at {MODULE_PATH}"
        raise RuntimeError(msg)
    module = importlib.util.module_from_spec(spec)
    sys.modules["value_hypothesis"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def vh() -> ModuleType:
    """Module under test, imported once per test module."""
    return _load_module()


def _valid_hypothesis() -> dict:
    """Construct a fully-populated v1 hypothesis dict."""
    return {
        "schema_version": 1,
        "feature_id": "F042",
        "author_role": "SME",
        "who": "Compliance reviewers handling DRNSG export filings.",
        "current_cost": "Average 4 hours per filing review.",
        "predicted": {
            "metric": "review_minutes",
            "direction": "decrease",
            "threshold": 60,
            "window_days": 30,
        },
        "how_we_know": "Time-and-motion sample of 20 filings post-ship.",
        "status": "pending",
        "validation": {
            "measured_at": None,
            "measured_value": None,
            "evidence": None,
        },
    }


# load / dump


class TestLoadAndDump:
    """Round-trip and error handling for load() and dump()."""

    def test_should_round_trip_when_hypothesis_is_well_formed(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _valid_hypothesis()

        vh.dump(path, hypothesis)
        loaded = vh.load(path)

        assert loaded == hypothesis

    def test_should_raise_value_error_when_yaml_is_malformed(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        # Deliberately broken YAML: unmatched bracket inside a flow mapping.
        path.write_text("schema_version: 1\nfeature_id: [F042\n", encoding="utf-8")

        with pytest.raises(ValueError, match="malformed YAML"):
            vh.load(path)

    def test_should_raise_value_error_when_top_level_is_not_a_mapping(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        path.write_text("- one\n- two\n", encoding="utf-8")

        with pytest.raises(ValueError, match="mapping"):
            vh.load(path)

    def test_should_raise_value_error_when_file_is_missing(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "does-not-exist.yaml"

        with pytest.raises(ValueError, match="not found"):
            vh.load(path)

    def test_should_return_none_and_warn_when_schema_version_is_unknown_future(
        self, vh: ModuleType, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """AC-006/BR-006: unknown future schema versions are skipped, not crashed."""
        path = tmp_path / "value-hypothesis.yaml"
        future = _valid_hypothesis()
        future["schema_version"] = 99
        vh.dump(path, future)

        with caplog.at_level(logging.WARNING):
            result = vh.load(path)

        assert result is None
        assert any(
            "schema_version" in record.message and "99" in record.message
            for record in caplog.records
        ), f"expected warning citing schema_version=99, got: {[r.message for r in caplog.records]}"

    def test_should_raise_value_error_when_schema_version_is_not_an_integer(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        bad = _valid_hypothesis()
        bad["schema_version"] = "1"  # string, not int
        vh.dump(path, bad)

        with pytest.raises(ValueError, match="schema_version"):
            vh.load(path)

    def test_should_use_safe_loader_when_parsing_yaml(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        """Reject Python-object YAML tags that the safe loader forbids.

        If the implementation slipped to yaml.load, the constructor below
        would deserialize and this test would not raise.
        """
        path = tmp_path / "value-hypothesis.yaml"
        # Build the unsafe tag fragment by concatenation so this source
        # file does not contain the literal pattern (a sibling hook scans
        # for shell-eval tokens in literal strings).
        unsafe_tag = "!!python/object/apply:" + "subprocess.getoutput"
        path.write_text(
            "schema_version: 1\n"
            f"feature_id: {unsafe_tag} ['echo hi']\n",
            encoding="utf-8",
        )

        with pytest.raises(ValueError):
            vh.load(path)


# validate_schema


class TestValidateSchema:
    """BR-005: required fields enforced."""

    def test_should_pass_when_all_required_fields_present(self, vh: ModuleType) -> None:
        # Should not raise.
        vh.validate_schema(_valid_hypothesis())

    @pytest.mark.parametrize(
        "missing_field",
        [
            "schema_version",
            "feature_id",
            "author_role",
            "who",
            "current_cost",
            "predicted",
            "how_we_know",
            "status",
            "validation",
        ],
    )
    def test_should_raise_value_error_when_required_field_is_missing(
        self, vh: ModuleType, missing_field: str
    ) -> None:
        hypothesis = _valid_hypothesis()
        del hypothesis[missing_field]

        with pytest.raises(ValueError, match=missing_field):
            vh.validate_schema(hypothesis)

    def test_should_raise_value_error_when_input_is_not_a_mapping(
        self, vh: ModuleType
    ) -> None:
        with pytest.raises(ValueError, match="mapping"):
            vh.validate_schema(["not", "a", "dict"])  # type: ignore[arg-type]

    def test_should_raise_value_error_when_status_is_not_a_legal_value(
        self, vh: ModuleType
    ) -> None:
        hypothesis = _valid_hypothesis()
        hypothesis["status"] = "in_orbit"

        with pytest.raises(ValueError, match="status"):
            vh.validate_schema(hypothesis)


class TestPredictedWindowDays:
    """BR-005 / AC-004: predicted.window_days is required and type-checked.

    The /metrics skill (skills/metrics/SKILL.md, Step 1) reads
    ``hypothesis["predicted"]["window_days"]`` unconditionally to compute
    the pending → unmeasured auto-transition. A hypothesis that passes
    schema validation with a missing or non-positive-int window_days
    would crash /metrics at runtime. The validator must reject these
    cases up front with a clear ValueError that names the field.
    """

    def test_should_raise_value_error_when_window_days_is_missing(
        self, vh: ModuleType
    ) -> None:
        hypothesis = _valid_hypothesis()
        del hypothesis["predicted"]["window_days"]

        with pytest.raises(ValueError, match="window_days"):
            vh.validate_schema(hypothesis)

    def test_should_raise_value_error_when_predicted_is_not_a_mapping(
        self, vh: ModuleType
    ) -> None:
        """A non-mapping predicted block cannot expose window_days at all."""
        hypothesis = _valid_hypothesis()
        hypothesis["predicted"] = "not a mapping"

        with pytest.raises(ValueError, match="predicted"):
            vh.validate_schema(hypothesis)

    @pytest.mark.parametrize(
        "bad_value",
        [
            "30",  # string that looks like a number
            30.0,  # float, even if integral
            True,  # bool is a subclass of int in Python — must be rejected
            None,  # explicit null
            [30],  # list
        ],
    )
    def test_should_raise_value_error_when_window_days_is_not_an_int(
        self, vh: ModuleType, bad_value: object
    ) -> None:
        hypothesis = _valid_hypothesis()
        hypothesis["predicted"]["window_days"] = bad_value

        with pytest.raises(ValueError, match="window_days"):
            vh.validate_schema(hypothesis)

    @pytest.mark.parametrize("bad_value", [0, -1, -30])
    def test_should_raise_value_error_when_window_days_is_not_positive(
        self, vh: ModuleType, bad_value: int
    ) -> None:
        hypothesis = _valid_hypothesis()
        hypothesis["predicted"]["window_days"] = bad_value

        with pytest.raises(ValueError, match="window_days"):
            vh.validate_schema(hypothesis)

    def test_should_pass_when_window_days_is_a_positive_int(
        self, vh: ModuleType
    ) -> None:
        # Sanity check: the canonical fixture (window_days=30) validates.
        # If this fails, the fixture and the validator have drifted apart.
        vh.validate_schema(_valid_hypothesis())


# transition_status


class TestTransitionStatus:
    """BR-011 / AC-014: pending -> {validated, invalidated, unmeasured}."""

    @pytest.mark.parametrize(
        "new_status",
        ["validated", "invalidated", "unmeasured"],
    )
    def test_should_transition_when_moving_from_pending_to_terminal_state(
        self, vh: ModuleType, new_status: str
    ) -> None:
        hypothesis = _valid_hypothesis()

        result = vh.transition_status(hypothesis, new_status)

        assert result["status"] == new_status

    def test_should_return_a_new_dict_and_not_mutate_input(self, vh: ModuleType) -> None:
        hypothesis = _valid_hypothesis()
        original = dict(hypothesis)

        result = vh.transition_status(hypothesis, "validated")

        assert hypothesis == original, "transition_status must not mutate its input"
        assert result is not hypothesis

    def test_should_attach_evidence_when_provided(self, vh: ModuleType) -> None:
        hypothesis = _valid_hypothesis()
        evidence = {
            "measured_at": "2026-05-01T12:00:00Z",
            "measured_value": 45,
            "evidence": "https://example.com/report.pdf",
        }

        result = vh.transition_status(hypothesis, "validated", evidence)

        assert result["validation"] == evidence

    @pytest.mark.parametrize(
        ("from_status", "to_status"),
        [
            ("validated", "invalidated"),
            ("validated", "pending"),
            ("validated", "unmeasured"),
            ("invalidated", "validated"),
            ("invalidated", "pending"),
            ("invalidated", "unmeasured"),
            ("unmeasured", "validated"),
            ("unmeasured", "invalidated"),
            ("unmeasured", "pending"),
            ("pending", "pending"),
        ],
    )
    def test_should_raise_value_error_when_transition_is_illegal(
        self, vh: ModuleType, from_status: str, to_status: str
    ) -> None:
        hypothesis = _valid_hypothesis()
        hypothesis["status"] = from_status

        with pytest.raises(ValueError, match="transition"):
            vh.transition_status(hypothesis, to_status)

    def test_should_raise_value_error_when_new_status_is_unknown(
        self, vh: ModuleType
    ) -> None:
        hypothesis = _valid_hypothesis()

        with pytest.raises(ValueError, match="status"):
            vh.transition_status(hypothesis, "in_orbit")


# CLI smoke tests — F1.4: skills (/spec, /metrics) need to invoke
# value_hypothesis from arbitrary working directories. The CLI must work
# without `cd`-ing into etc-system-engineering and without making
# `scripts/` an importable package.


class TestCommandLineInterface:
    """End-to-end subprocess tests of the value_hypothesis.py CLI.

    These tests run the script as `python value_hypothesis.py <subcmd>`
    from a tmp_path cwd to mirror how skills will invoke it at runtime.
    They guard the contract that no Python import path tricks are
    required by callers.
    """

    def test_should_validate_via_subprocess_from_unrelated_cwd(
        self, tmp_path: Path
    ) -> None:
        yaml_path = tmp_path / "value-hypothesis.yaml"
        yaml_path.write_text(
            yaml.safe_dump(_valid_hypothesis(), sort_keys=False),
            encoding="utf-8",
        )

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "validate", str(yaml_path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"expected exit 0; got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

    def test_should_exit_nonzero_when_validation_fails_via_subprocess(
        self, tmp_path: Path
    ) -> None:
        yaml_path = tmp_path / "value-hypothesis.yaml"
        bad = _valid_hypothesis()
        # Drop a required field — validate_schema must reject and the CLI
        # must surface the field name on stderr.
        del bad["how_we_know"]
        yaml_path.write_text(
            yaml.safe_dump(bad, sort_keys=False), encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "validate", str(yaml_path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1, (
            f"expected exit 1 on validation failure; got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        assert "how_we_know" in result.stderr, (
            f"stderr should name the missing field; got {result.stderr!r}"
        )

    def test_should_load_and_print_json_via_subprocess(
        self, tmp_path: Path
    ) -> None:
        yaml_path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _valid_hypothesis()
        yaml_path.write_text(
            yaml.safe_dump(hypothesis, sort_keys=False), encoding="utf-8"
        )

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "load", str(yaml_path)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"expected exit 0; got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        parsed = json.loads(result.stdout)
        assert parsed == hypothesis
        # Stable, sorted-key output — first non-whitespace key in the
        # printed JSON should be the alphabetically smallest field.
        first_key_line = next(
            line for line in result.stdout.splitlines() if ":" in line
        )
        assert first_key_line.lstrip().startswith('"author_role"'), (
            f"expected sorted keys; first key line was {first_key_line!r}"
        )

    def test_should_transition_atomically_via_subprocess(
        self, tmp_path: Path
    ) -> None:
        yaml_path = tmp_path / "value-hypothesis.yaml"
        yaml_path.write_text(
            yaml.safe_dump(_valid_hypothesis(), sort_keys=False),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "transition",
                str(yaml_path),
                "validated",
                "--measured-value",
                "45",
                "--evidence",
                "https://example.com/report.pdf",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 0, (
            f"expected exit 0; got {result.returncode}; "
            f"stdout={result.stdout!r} stderr={result.stderr!r}"
        )

        # File should now have status: validated and the supplied
        # validation block.
        on_disk = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        assert on_disk["status"] == "validated"
        assert on_disk["validation"]["measured_value"] == 45
        assert (
            on_disk["validation"]["evidence"]
            == "https://example.com/report.pdf"
        )

        # No leftover .tmp files in the target directory.
        leftovers = [p.name for p in tmp_path.iterdir() if p.name != yaml_path.name]
        assert not leftovers, (
            f"atomic write must leave no temp files behind; found {leftovers}"
        )

    def test_should_exit_nonzero_when_transition_is_illegal_via_subprocess(
        self, tmp_path: Path
    ) -> None:
        """Illegal transitions must be rejected with non-zero exit and a
        diagnostic on stderr — guards BR-011 at the CLI boundary."""
        yaml_path = tmp_path / "value-hypothesis.yaml"
        already_validated = _valid_hypothesis()
        already_validated["status"] = "validated"
        yaml_path.write_text(
            yaml.safe_dump(already_validated, sort_keys=False),
            encoding="utf-8",
        )

        result = subprocess.run(
            [
                sys.executable,
                str(MODULE_PATH),
                "transition",
                str(yaml_path),
                "invalidated",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode != 0
        assert "transition" in result.stderr.lower()

    def test_should_exit_nonzero_when_yaml_file_missing_via_subprocess(
        self, tmp_path: Path
    ) -> None:
        missing = tmp_path / "nope.yaml"

        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "validate", str(missing)],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode == 1
        assert "not found" in result.stderr.lower()

    def test_should_exit_nonzero_when_subcommand_unknown_via_subprocess(
        self, tmp_path: Path
    ) -> None:
        result = subprocess.run(
            [sys.executable, str(MODULE_PATH), "frobnicate"],
            cwd=tmp_path,
            capture_output=True,
            text=True,
            check=False,
        )

        assert result.returncode != 0
        assert result.stderr.strip(), "expected a diagnostic on stderr"


# F006 BR-007: dual-author-role schema extension.
#
# /spec → /spec + /architect phase split (F006) extends the
# value-hypothesis.yaml schema. Legacy F001-F009 features carry a single
# top-level `author_role`. New (F010+) features carry per-phase
# `spec_author_role` and (optionally) `architect_author_role`. The
# validator must accept BOTH shapes, reject unknown fields, and apply
# the same sanitization contract (cap 64 chars, strip control chars
# matching [\x00-\x1f\x7f]) to all three author-role variants.


def _new_shape_hypothesis() -> dict:
    """Construct a fully-populated v1 hypothesis using the F006 dual-role schema.

    Has `spec_author_role` and `architect_author_role` instead of the
    legacy single `author_role` field.
    """
    base = _valid_hypothesis()
    del base["author_role"]
    base["spec_author_role"] = "PM"
    base["architect_author_role"] = "Engineer"
    return base


class TestF006DualAuthorRoleSchema:
    """BR-007 / AC-10: validator accepts both legacy and new author-role shapes."""

    def test_should_pass_when_legacy_author_role_present(self, vh: ModuleType) -> None:
        """Legacy single-author_role shape (F001-F009) must continue to validate."""
        # Should not raise.
        vh.validate_schema(_valid_hypothesis())

    def test_should_pass_when_new_dual_author_role_shape_present(
        self, vh: ModuleType
    ) -> None:
        """New shape: spec_author_role + architect_author_role, no author_role."""
        # Should not raise.
        vh.validate_schema(_new_shape_hypothesis())

    def test_should_pass_when_only_spec_author_role_present(self, vh: ModuleType) -> None:
        """architect_author_role is independently optional; spec_author_role alone is valid."""
        hypothesis = _new_shape_hypothesis()
        del hypothesis["architect_author_role"]

        # Should not raise.
        vh.validate_schema(hypothesis)

    def test_should_raise_value_error_when_neither_author_role_nor_spec_author_role_present(
        self, vh: ModuleType
    ) -> None:
        """Schema rule: at least ONE of {author_role, spec_author_role} must be present."""
        hypothesis = _valid_hypothesis()
        del hypothesis["author_role"]
        # No spec_author_role added either.

        with pytest.raises(ValueError, match="author_role"):
            vh.validate_schema(hypothesis)

    def test_should_raise_value_error_when_unknown_field_present_legacy_shape(
        self, vh: ModuleType
    ) -> None:
        """Validator rejects unknown fields outside the documented field set."""
        hypothesis = _valid_hypothesis()
        hypothesis["surprise_field"] = "unexpected"

        with pytest.raises(ValueError, match="surprise_field"):
            vh.validate_schema(hypothesis)

    def test_should_raise_value_error_when_unknown_field_present_new_shape(
        self, vh: ModuleType
    ) -> None:
        """Unknown-field rejection applies to the new dual-role shape too."""
        hypothesis = _new_shape_hypothesis()
        hypothesis["random_extra"] = "nope"

        with pytest.raises(ValueError, match="random_extra"):
            vh.validate_schema(hypothesis)

    def test_should_pass_when_architect_author_role_present_with_legacy_author_role(
        self, vh: ModuleType
    ) -> None:
        """architect_author_role can coexist with legacy author_role (mixed case)."""
        hypothesis = _valid_hypothesis()
        hypothesis["architect_author_role"] = "Engineer"

        # Should not raise.
        vh.validate_schema(hypothesis)


class TestF006AuthorRoleSanitization:
    """BR-007 + F001 sanitization contract: cap 64 chars, strip control chars."""

    def test_should_strip_control_characters_from_legacy_author_role_when_loading(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _valid_hypothesis()
        # Inject a control char and a DEL character.
        hypothesis["author_role"] = "Other:\x01rogue\x7frole"
        vh.dump(path, hypothesis)

        loaded = vh.load(path)

        assert loaded is not None
        assert loaded["author_role"] == "Other:roguerole"

    def test_should_cap_legacy_author_role_at_64_chars_when_loading(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _valid_hypothesis()
        hypothesis["author_role"] = "A" * 100
        vh.dump(path, hypothesis)

        loaded = vh.load(path)

        assert loaded is not None
        assert loaded["author_role"] == "A" * 64

    def test_should_strip_control_characters_from_spec_author_role_when_loading(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _new_shape_hypothesis()
        hypothesis["spec_author_role"] = "PM\x02clean"
        vh.dump(path, hypothesis)

        loaded = vh.load(path)

        assert loaded is not None
        assert loaded["spec_author_role"] == "PMclean"

    def test_should_cap_spec_author_role_at_64_chars_when_loading(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _new_shape_hypothesis()
        hypothesis["spec_author_role"] = "B" * 100
        vh.dump(path, hypothesis)

        loaded = vh.load(path)

        assert loaded is not None
        assert loaded["spec_author_role"] == "B" * 64

    def test_should_strip_control_characters_from_architect_author_role_when_loading(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _new_shape_hypothesis()
        hypothesis["architect_author_role"] = "Engineer\x1fclean"
        vh.dump(path, hypothesis)

        loaded = vh.load(path)

        assert loaded is not None
        assert loaded["architect_author_role"] == "Engineerclean"

    def test_should_cap_architect_author_role_at_64_chars_when_loading(
        self, vh: ModuleType, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _new_shape_hypothesis()
        hypothesis["architect_author_role"] = "C" * 100
        vh.dump(path, hypothesis)

        loaded = vh.load(path)

        assert loaded is not None
        assert loaded["architect_author_role"] == "C" * 64
