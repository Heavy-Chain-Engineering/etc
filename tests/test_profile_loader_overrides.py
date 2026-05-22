"""Tests for scripts/profile_loader.py override-merge path (F022 BR-006 / AC-007).

Covers:
    (a) Override file absent             -> behavior unchanged from pre-F022.
    (b) Valid pin: [python]              -> adds python to active set even when
                                            detection missed it.
    (c) Valid exclude: ["vendor/**"]     -> exclude glob propagated to dispatch
                                            context.
    (d) Valid add: [{profile, source}]   -> external profile in active set.
    (e) Unknown top-level key            -> stderr WARN + active set matches
                                            detection-only.
    (f) Malformed YAML                   -> stderr WARN + active set matches
                                            detection-only.

The override-merge path layers on top of the existing active_profiles()
contract. The new public API is load_profiles_with_overrides(cwd) which
returns a structured result (active set + excludes), and is intentionally
additive: pre-F022 callers using active_profiles() are unchanged.

Detection-first invariant (F020-ADR-002): overrides MODIFY detection output,
never REPLACE it. An empty overrides file MUST NOT disable detection.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

SCRIPT_PATH = (
    Path(__file__).resolve().parent.parent / "scripts" / "profile_loader.py"
)


def _load_profile_loader() -> ModuleType:
    """Load scripts/profile_loader.py as the 'profile_loader' module.

    Registers the module in sys.modules before exec because @dataclass
    inspects sys.modules[cls.__module__] for forward-reference resolution
    on Python 3.12+.
    """
    spec = importlib.util.spec_from_file_location("profile_loader", SCRIPT_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["profile_loader"] = module
    spec.loader.exec_module(module)
    return module


def _write_lock(repo: Path, profiles: list[str]) -> Path:
    lock_dir = repo / ".etc_sdlc"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock = lock_dir / "profiles.lock"
    lock.write_text("".join(p + "\n" for p in profiles))
    return lock


def _write_override(repo: Path, content: str) -> Path:
    override_dir = repo / ".etc_sdlc"
    override_dir.mkdir(parents=True, exist_ok=True)
    override = override_dir / "profiles.yaml"
    override.write_text(content)
    return override


class TestPreF022SignaturePreserved:
    """The pre-F022 active_profiles() contract must remain byte-equivalent."""

    def test_should_return_lock_contents_when_no_override_file(
        self, tmp_path: Path
    ) -> None:
        lock = _write_lock(tmp_path, ["python"])
        loader = _load_profile_loader()
        result = loader.active_profiles(lock)
        assert result == ["python"]

    def test_should_return_empty_when_no_lock_and_no_override(
        self, tmp_path: Path
    ) -> None:
        loader = _load_profile_loader()
        result = loader.active_profiles(tmp_path / "missing.lock")
        assert result == []


class TestOverrideAbsent:
    """(a) Override file absent -> behavior unchanged."""

    def test_should_match_detection_when_override_absent(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["python"])
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.active == ["python"]
        assert result.excludes == []

    def test_should_return_empty_active_when_no_lock_and_no_override(
        self, tmp_path: Path
    ) -> None:
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.active == []
        assert result.excludes == []


class TestValidPin:
    """(b) Valid pin: [python] -> python added even if detection missed it."""

    def test_should_pin_profile_not_in_detection(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, [])  # detection empty
        _write_override(tmp_path, "pin:\n  - python\n")
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert "python" in result.active

    def test_should_union_pin_with_detection(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["typescript"])
        _write_override(tmp_path, "pin:\n  - python\n")
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert set(result.active) == {"python", "typescript"}

    def test_should_dedup_pin_overlapping_detection(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, "pin:\n  - python\n")
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.active == ["python"]

    def test_empty_overrides_must_not_disable_detection(
        self, tmp_path: Path
    ) -> None:
        """F020-ADR-002: detection-first invariant. Empty override must not
        replace detection."""
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, "")  # empty file
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.active == ["python"]


class TestValidExclude:
    """(c) Valid exclude: ["vendor/**"] -> propagated to dispatch context."""

    def test_should_propagate_exclude_glob(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, 'exclude:\n  - "vendor/**"\n')
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.excludes == ["vendor/**"]
        # Detection-first: exclude does NOT remove python from active set
        assert result.active == ["python"]

    def test_should_propagate_multiple_excludes(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(
            tmp_path,
            'exclude:\n  - "vendor/**"\n  - "third_party/**"\n',
        )
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.excludes == ["vendor/**", "third_party/**"]


class TestValidAdd:
    """(d) Valid add: [{profile, source}] -> external profile in active set."""

    def test_should_add_external_profile(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["python"])
        (tmp_path / "local-profiles" / "scala").mkdir(parents=True)
        _write_override(
            tmp_path,
            "add:\n  - profile: scala\n    source: ./local-profiles/scala/\n",
        )
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert set(result.active) == {"python", "scala"}

    def test_should_reject_add_with_path_traversal(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Security: path-traversal in add[].source must be rejected."""
        _write_lock(tmp_path, ["python"])
        _write_override(
            tmp_path,
            "add:\n  - profile: evil\n    source: ../../etc/passwd\n",
        )
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        # detection-only fallback for the rejected add entry
        assert "evil" not in result.active
        assert result.active == ["python"]
        captured = capsys.readouterr()
        assert "WARN" in captured.err

    def test_should_reject_add_with_absolute_path(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(
            tmp_path,
            "add:\n  - profile: evil\n    source: /etc/passwd\n",
        )
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert "evil" not in result.active
        captured = capsys.readouterr()
        assert "WARN" in captured.err


class TestUnknownKey:
    """(e) Unknown top-level key -> WARN + fallback to detection-only."""

    def test_should_warn_and_fall_back_on_unknown_key(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, "garbage: value\n")
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        # Detection-only fallback: active set matches the lock.
        assert result.active == ["python"]
        assert result.excludes == []
        captured = capsys.readouterr()
        assert "WARN" in captured.err
        assert "unknown key" in captured.err.lower()

    def test_should_not_raise_on_unknown_key(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, "garbage: value\n")
        loader = _load_profile_loader()
        # MUST NOT raise — graceful degradation per BR-006.
        result = loader.load_profiles_with_overrides(tmp_path)
        assert isinstance(result.active, list)


class TestMalformedYaml:
    """(f) Malformed YAML -> WARN + fallback to detection-only."""

    def test_should_warn_and_fall_back_on_malformed_yaml(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, ":\n  - bad: [unclosed\n")
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.active == ["python"]
        assert result.excludes == []
        captured = capsys.readouterr()
        assert "WARN" in captured.err

    def test_should_not_raise_on_malformed_yaml(
        self, tmp_path: Path
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, ":\n  - bad: [unclosed\n")
        loader = _load_profile_loader()
        # MUST NOT raise — graceful degradation per BR-006.
        result = loader.load_profiles_with_overrides(tmp_path)
        assert isinstance(result.active, list)

    def test_should_warn_when_top_level_is_not_a_mapping(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write_lock(tmp_path, ["python"])
        _write_override(tmp_path, "- just\n- a\n- list\n")
        loader = _load_profile_loader()
        result = loader.load_profiles_with_overrides(tmp_path)
        assert result.active == ["python"]
        captured = capsys.readouterr()
        assert "WARN" in captured.err


class TestTemplateArtifact:
    """The .etc_sdlc/profiles.yaml.template file must document the schema."""

    def test_template_file_exists_and_documents_schema(self) -> None:
        template = (
            Path(__file__).resolve().parent.parent
            / ".etc_sdlc"
            / "profiles.yaml.template"
        )
        assert template.is_file(), (
            f"Expected schema template at {template}"
        )
        body = template.read_text(encoding="utf-8")
        # Schema fields documented
        assert "pin:" in body
        assert "exclude:" in body
        assert "add:" in body
        # Each is annotated as a list (per BR-006 schema definition)
        assert "list[str]" in body or "list of" in body.lower()
        # The template is comments-only (no operator data leaks)
        # — every non-empty, non-comment line should be ignorable YAML.
        # Acceptance: at least one explanatory comment line per key.
        assert "# pin" in body or "#pin" in body
        assert "# exclude" in body or "#exclude" in body
        assert "# add" in body or "#add" in body
