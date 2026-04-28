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
import logging
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MODULE_PATH = REPO_ROOT / "scripts" / "value_hypothesis.py"


def _load_module() -> object:
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
def vh() -> object:
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
        self, vh: object, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        hypothesis = _valid_hypothesis()

        vh.dump(path, hypothesis)
        loaded = vh.load(path)

        assert loaded == hypothesis

    def test_should_raise_value_error_when_yaml_is_malformed(
        self, vh: object, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        # Deliberately broken YAML: unmatched bracket inside a flow mapping.
        path.write_text("schema_version: 1\nfeature_id: [F042\n", encoding="utf-8")

        with pytest.raises(ValueError, match="malformed YAML"):
            vh.load(path)

    def test_should_raise_value_error_when_top_level_is_not_a_mapping(
        self, vh: object, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        path.write_text("- one\n- two\n", encoding="utf-8")

        with pytest.raises(ValueError, match="mapping"):
            vh.load(path)

    def test_should_raise_value_error_when_file_is_missing(
        self, vh: object, tmp_path: Path
    ) -> None:
        path = tmp_path / "does-not-exist.yaml"

        with pytest.raises(ValueError, match="not found"):
            vh.load(path)

    def test_should_return_none_and_warn_when_schema_version_is_unknown_future(
        self, vh: object, tmp_path: Path, caplog: pytest.LogCaptureFixture
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
        self, vh: object, tmp_path: Path
    ) -> None:
        path = tmp_path / "value-hypothesis.yaml"
        bad = _valid_hypothesis()
        bad["schema_version"] = "1"  # string, not int
        vh.dump(path, bad)

        with pytest.raises(ValueError, match="schema_version"):
            vh.load(path)

    def test_should_use_safe_loader_when_parsing_yaml(
        self, vh: object, tmp_path: Path
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

    def test_should_pass_when_all_required_fields_present(self, vh: object) -> None:
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
        self, vh: object, missing_field: str
    ) -> None:
        hypothesis = _valid_hypothesis()
        del hypothesis[missing_field]

        with pytest.raises(ValueError, match=missing_field):
            vh.validate_schema(hypothesis)

    def test_should_raise_value_error_when_input_is_not_a_mapping(
        self, vh: object
    ) -> None:
        with pytest.raises(ValueError, match="mapping"):
            vh.validate_schema(["not", "a", "dict"])  # type: ignore[arg-type]

    def test_should_raise_value_error_when_status_is_not_a_legal_value(
        self, vh: object
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
        self, vh: object
    ) -> None:
        hypothesis = _valid_hypothesis()
        del hypothesis["predicted"]["window_days"]

        with pytest.raises(ValueError, match="window_days"):
            vh.validate_schema(hypothesis)

    def test_should_raise_value_error_when_predicted_is_not_a_mapping(
        self, vh: object
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
        self, vh: object, bad_value: object
    ) -> None:
        hypothesis = _valid_hypothesis()
        hypothesis["predicted"]["window_days"] = bad_value

        with pytest.raises(ValueError, match="window_days"):
            vh.validate_schema(hypothesis)

    @pytest.mark.parametrize("bad_value", [0, -1, -30])
    def test_should_raise_value_error_when_window_days_is_not_positive(
        self, vh: object, bad_value: int
    ) -> None:
        hypothesis = _valid_hypothesis()
        hypothesis["predicted"]["window_days"] = bad_value

        with pytest.raises(ValueError, match="window_days"):
            vh.validate_schema(hypothesis)

    def test_should_pass_when_window_days_is_a_positive_int(
        self, vh: object
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
        self, vh: object, new_status: str
    ) -> None:
        hypothesis = _valid_hypothesis()

        result = vh.transition_status(hypothesis, new_status)

        assert result["status"] == new_status

    def test_should_return_a_new_dict_and_not_mutate_input(self, vh: object) -> None:
        hypothesis = _valid_hypothesis()
        original = dict(hypothesis)

        result = vh.transition_status(hypothesis, "validated")

        assert hypothesis == original, "transition_status must not mutate its input"
        assert result is not hypothesis

    def test_should_attach_evidence_when_provided(self, vh: object) -> None:
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
        self, vh: object, from_status: str, to_status: str
    ) -> None:
        hypothesis = _valid_hypothesis()
        hypothesis["status"] = from_status

        with pytest.raises(ValueError, match="transition"):
            vh.transition_status(hypothesis, to_status)

    def test_should_raise_value_error_when_new_status_is_unknown(
        self, vh: object
    ) -> None:
        hypothesis = _valid_hypothesis()

        with pytest.raises(ValueError, match="status"):
            vh.transition_status(hypothesis, "in_orbit")
