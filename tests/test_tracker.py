#!/usr/bin/env python3
"""Tests for the SDLC Workflow Tracker (.sdlc/tracker.py)."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

TRACKER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".sdlc", "tracker.py")


class TrackerTestHarness:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.errors = []

    def run(self, name, fn):
        try:
            fn()
            self.passed += 1
            print(f"  PASS: {name}")
        except AssertionError as e:
            self.failed += 1
            self.errors.append((name, str(e)))
            print(f"  FAIL: {name} -- {e}")
        except Exception as e:
            self.failed += 1
            self.errors.append((name, str(e)))
            print(f"  ERROR: {name} -- {e}")

    def summary(self):
        total = self.passed + self.failed
        print(f"\n{self.passed}/{total} passed, {self.failed} failed")
        if self.errors:
            print("\nFailures:")
            for name, err in self.errors:
                print(f"  - {name}: {err}")
        return 0 if self.failed == 0 else 1


def make_test_sdlc(tmp_dir):
    sdlc_dir = os.path.join(tmp_dir, ".sdlc")
    os.makedirs(sdlc_dir, exist_ok=True)
    real_templates = os.path.join(os.path.dirname(TRACKER), "dod-templates.json")
    shutil.copy2(real_templates, os.path.join(sdlc_dir, "dod-templates.json"))
    shutil.copy2(TRACKER, os.path.join(sdlc_dir, "tracker.py"))
    return os.path.join(sdlc_dir, "tracker.py")


def run_tracker(tracker_path, *args):
    result = subprocess.run(
        [sys.executable, tracker_path] + list(args),
        capture_output=True, text=True,
    )
    return result.returncode, result.stdout, result.stderr


def main():
    harness = TrackerTestHarness()

    def test_init_creates_state():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            code, out, _ = run_tracker(tp, "init")
            assert code == 0, f"Expected exit 0, got {code}: {out}"
            state_path = os.path.join(os.path.dirname(tp), "state.json")
            assert os.path.exists(state_path), "state.json not created"
            with open(state_path) as f:
                state = json.load(f)
            assert state["current_phase"] == "Bootstrap"
            assert len(state["phases"]) == 7

    def test_init_fails_if_exists():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            code, out, _ = run_tracker(tp, "init")
            assert code == 1, f"Expected exit 1 on double init, got {code}"

    def test_current_prints_bootstrap():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            code, out, _ = run_tracker(tp, "current")
            assert code == 0
            assert "Bootstrap" in out

    def test_status_shows_dod():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            code, out, _ = run_tracker(tp, "status")
            assert code == 0
            assert "Phase: Bootstrap" in out
            assert "[ ]" in out
            assert "0/3" in out

    def test_check_marks_item():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            code, out, _ = run_tracker(tp, "check", "0")
            assert code == 0
            assert "Checked:" in out
            assert "1/3" in out

    def test_uncheck_clears_item():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            run_tracker(tp, "check", "0")
            code, out, _ = run_tracker(tp, "uncheck", "0")
            assert code == 0
            assert "Unchecked:" in out
            assert "0/3" in out

    def test_transition_blocked_by_dod():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            code, out, _ = run_tracker(tp, "transition", "Spec")
            assert code == 1, f"Expected exit 1, got {code}"
            assert "Cannot transition" in out

    def test_transition_succeeds_when_dod_met():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            for i in range(3):
                run_tracker(tp, "check", str(i))
            code, out, _ = run_tracker(tp, "transition", "Spec", "Bootstrap complete")
            assert code == 0, f"Expected exit 0, got {code}: {out}"
            assert "Transitioned: Bootstrap -> Spec" in out

    def test_history_shows_transitions():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            for i in range(3):
                run_tracker(tp, "check", str(i))
            run_tracker(tp, "transition", "Spec", "done")
            code, out, _ = run_tracker(tp, "history")
            assert code == 0
            assert "Bootstrap -> Spec" in out

    def test_check_out_of_range():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            code, out, _ = run_tracker(tp, "check", "99")
            assert code == 2, f"Expected exit 2 for out-of-range, got {code}"

    def test_transition_invalid_phase():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            run_tracker(tp, "init")
            code, out, _ = run_tracker(tp, "transition", "Nonexistent")
            assert code == 2, f"Expected exit 2, got {code}"

    def test_current_without_init():
        with tempfile.TemporaryDirectory() as tmp:
            tp = make_test_sdlc(tmp)
            code, out, _ = run_tracker(tp, "current")
            assert code == 2, f"Expected exit 2 without init, got {code}"

    harness.run("init creates state.json", test_init_creates_state)
    harness.run("init fails if state.json exists", test_init_fails_if_exists)
    harness.run("current prints Bootstrap", test_current_prints_bootstrap)
    harness.run("status shows DoD items", test_status_shows_dod)
    harness.run("check marks item done", test_check_marks_item)
    harness.run("uncheck clears item", test_uncheck_clears_item)
    harness.run("transition blocked by incomplete DoD", test_transition_blocked_by_dod)
    harness.run("transition succeeds with DoD met", test_transition_succeeds_when_dod_met)
    harness.run("history shows transitions", test_history_shows_transitions)
    harness.run("check out of range errors", test_check_out_of_range)
    harness.run("transition to invalid phase errors", test_transition_invalid_phase)
    harness.run("current without init errors", test_current_without_init)

    sys.exit(harness.summary())


if __name__ == "__main__":
    main()
