"""Tests for scripts/runtime_totalization_check.py (Gap A / /build Step 7.6 core).

This task (005.001) implements the totalization CORE: re-run declared-live
ACs against the assembled app via the runtime-verify dispatcher, totalize the
per-AC verdicts, honor the infrastructure_only exemption + schema_version
tolerance, and persist the aggregated results merge-preserve to
state.yaml.build.runtime_verification. Terminal-tag routing + exit-code mapping
land in the sibling task 005.002 and are NOT exercised here.

The tests import the module directly and monkeypatch the single dispatcher
seam (``invoke_dispatcher``) so no app is ever stood up in unit tests.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import yaml

_SCRIPT = Path(__file__).parent.parent / "scripts" / "runtime_totalization_check.py"
_SPEC = importlib.util.spec_from_file_location("runtime_totalization_check", _SCRIPT)
assert _SPEC is not None and _SPEC.loader is not None
rtc = importlib.util.module_from_spec(_SPEC)
# Register before exec so dataclasses can resolve string annotations (the module
# uses ``from __future__ import annotations``).
sys.modules["runtime_totalization_check"] = rtc
_SPEC.loader.exec_module(rtc)


def _write_state(feature_dir: Path, state: dict[str, Any]) -> None:
    feature_dir.mkdir(parents=True, exist_ok=True)
    (feature_dir / "state.yaml").write_text(
        yaml.safe_dump(state, sort_keys=False), encoding="utf-8"
    )


def _read_state(feature_dir: Path) -> dict[str, Any]:
    with (feature_dir / "state.yaml").open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _liveness_state(live_at: str = "wave-2") -> dict[str, Any]:
    return {
        "spec_phase": {
            "contract_completeness": {
                "schema_version": 1,
                "liveness": [
                    {
                        "ac_id": "AC-3",
                        "outcome": "saving persists and survives reload",
                        "live_at": live_at,
                        "acceptance_statement": "on save a network call persists X",
                        "deferred_reason": None,
                    },
                ],
            },
        },
    }


def test_should_not_dispatch_when_infrastructure_only_true(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    state = _liveness_state()
    state["spec_phase"]["infrastructure_only"] = True
    _write_state(feature_dir, state)

    calls: list[Any] = []
    monkeypatch.setattr(
        rtc, "invoke_dispatcher", lambda *a, **k: calls.append((a, k)) or {"results": []}
    )

    result = rtc.totalize(feature_dir)

    assert calls == []
    assert result.classification == "exempt"


def test_should_warn_and_skip_when_liveness_schema_version_higher_than_known(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    state = _liveness_state()
    state["spec_phase"]["contract_completeness"]["schema_version"] = 2
    _write_state(feature_dir, state)

    calls: list[Any] = []
    monkeypatch.setattr(
        rtc, "invoke_dispatcher", lambda *a, **k: calls.append((a, k)) or {"results": []}
    )

    # Must not crash; must not dispatch (nothing checkable at an unknown version).
    result = rtc.totalize(feature_dir)

    assert calls == []
    assert result.classification == "schema_skipped"


def test_should_dispatch_live_ac_ids_when_liveness_declares_live_acs(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    _write_state(feature_dir, _liveness_state(live_at="wave-2"))

    captured: dict[str, Any] = {}

    def fake_dispatch(feature_path: str, live_ac_ids: list[str], cwd: str) -> dict[str, Any]:
        captured["feature_path"] = feature_path
        captured["live_ac_ids"] = live_ac_ids
        return {
            "results": [
                {"ac_id": "AC-3", "status": "pass", "evidence": "pytest ... PASSED"}
            ]
        }

    monkeypatch.setattr(rtc, "invoke_dispatcher", fake_dispatch)

    result = rtc.totalize(feature_dir)

    assert captured["live_ac_ids"] == ["AC-3"]
    assert result.classification == "all_verified"


def test_should_persist_results_to_build_runtime_verification(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    _write_state(feature_dir, _liveness_state(live_at="wave-2"))

    monkeypatch.setattr(
        rtc,
        "invoke_dispatcher",
        lambda *a, **k: {
            "results": [
                {"ac_id": "AC-3", "status": "pass", "evidence": "PASSED"}
            ]
        },
    )

    rtc.totalize(feature_dir)

    persisted = _read_state(feature_dir)
    block = persisted["build"]["runtime_verification"]
    assert block["schema_version"] == 1
    assert block["stage"] == "release"
    assert block["terminal_tag"] is None
    assert block["results"][0]["ac_id"] == "AC-3"
    assert block["results"][0]["status"] == "pass"
    assert block["results"][0]["live_at"] == "wave-2"


def test_should_merge_preserve_existing_build_and_spec_keys_when_persisting(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    state = _liveness_state(live_at="wave-2")
    state["build"] = {"autonomous": {"max_turns": 40}}
    state["top_level_marker"] = "keep-me"
    _write_state(feature_dir, state)

    monkeypatch.setattr(
        rtc,
        "invoke_dispatcher",
        lambda *a, **k: {
            "results": [{"ac_id": "AC-3", "status": "pass", "evidence": "PASSED"}]
        },
    )

    rtc.totalize(feature_dir)

    persisted = _read_state(feature_dir)
    assert persisted["build"]["autonomous"] == {"max_turns": 40}
    assert persisted["build"]["runtime_verification"]["results"][0]["ac_id"] == "AC-3"
    assert persisted["top_level_marker"] == "keep-me"
    assert persisted["spec_phase"]["contract_completeness"]["schema_version"] == 1


def test_should_classify_deferred_when_live_at_is_deferred_with_reason(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    state = _liveness_state(live_at="deferred")
    entry = state["spec_phase"]["contract_completeness"]["liveness"][0]
    entry["deferred_reason"] = "auth provider not yet provisioned"
    _write_state(feature_dir, state)

    calls: list[Any] = []
    monkeypatch.setattr(
        rtc, "invoke_dispatcher", lambda *a, **k: calls.append(1) or {"results": []}
    )

    result = rtc.totalize(feature_dir)

    # Deferred AC is not re-run; classification flags the deferral.
    assert calls == []
    assert result.classification == "deferred_present"
    persisted = _read_state(feature_dir)
    deferred = persisted["build"]["runtime_verification"]["deferred"]
    assert deferred[0]["ac_id"] == "AC-3"
    assert deferred[0]["reason"] == "auth provider not yet provisioned"


def test_should_classify_live_failure_when_declared_live_ac_fails(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    _write_state(feature_dir, _liveness_state(live_at="wave-2"))

    monkeypatch.setattr(
        rtc,
        "invoke_dispatcher",
        lambda *a, **k: {
            "results": [
                {"ac_id": "AC-3", "status": "fail", "evidence": "0 network calls"}
            ]
        },
    )

    result = rtc.totalize(feature_dir)

    assert result.classification == "live_failure"


def test_should_classify_live_failure_when_declared_live_ac_has_no_test(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    _write_state(feature_dir, _liveness_state(live_at="wave-2"))

    monkeypatch.setattr(
        rtc,
        "invoke_dispatcher",
        lambda *a, **k: {"results": []},  # dispatcher returned nothing for AC-3
    )

    result = rtc.totalize(feature_dir)

    assert result.classification == "live_failure"
    persisted = _read_state(feature_dir)
    statuses = {r["ac_id"]: r["status"] for r in persisted["build"]["runtime_verification"]["results"]}
    assert statuses["AC-3"] == "no-test"


def test_should_be_exempt_when_no_liveness_block_present(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    _write_state(feature_dir, {"spec_phase": {"completed_at": "2026-01-01"}})

    calls: list[Any] = []
    monkeypatch.setattr(
        rtc, "invoke_dispatcher", lambda *a, **k: calls.append(1) or {"results": []}
    )

    result = rtc.totalize(feature_dir)

    # Forward-only: legacy feature with no liveness block is never gated.
    assert calls == []
    assert result.classification == "ungated"


def test_should_classify_all_verified_when_liveness_empty(
    tmp_path: Path, monkeypatch: Any
) -> None:
    feature_dir = tmp_path / "F-test"
    state = {
        "spec_phase": {
            "contract_completeness": {"schema_version": 1, "liveness": []}
        }
    }
    _write_state(feature_dir, state)

    calls: list[Any] = []
    monkeypatch.setattr(
        rtc, "invoke_dispatcher", lambda *a, **k: calls.append(1) or {"results": []}
    )

    result = rtc.totalize(feature_dir)

    # Present-but-empty liveness totalizes trivially -> clean.
    assert calls == []
    assert result.classification == "all_verified"
