#!/usr/bin/env python3
"""
SDLC Workflow Tracker — persistent phase state and Definition of Done enforcement.

Usage:
    tracker.py init                          Initialize state.json from templates
    tracker.py current                       Print current phase
    tracker.py status                        Print current phase + DoD checklist
    tracker.py check <item_index>            Mark a DoD item as complete (0-indexed)
    tracker.py uncheck <item_index>          Mark a DoD item as incomplete
    tracker.py transition <phase> [reason]   Transition to a new phase (gates on DoD)
    tracker.py history                       Print phase transition log

Exit codes: 0 = success, 1 = validation failure, 2 = error
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(SCRIPT_DIR, "state.json")
DOD_TEMPLATE_FILE = os.path.join(SCRIPT_DIR, "dod-templates.json")

PHASE_ORDER = [
    "Bootstrap",
    "Spec",
    "Design",
    "Decompose",
    "Build",
    "Ship",
    "Evaluate",
]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_iso():
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def atomic_write(path, data):
    """Write JSON data atomically: write to temp file, then rename."""
    dir_name = os.path.dirname(path)
    fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_state():
    """Load state.json, or exit with error if not found."""
    if not os.path.exists(STATE_FILE):
        print("Error: state.json not found. Run 'tracker.py init' first.")
        sys.exit(2)
    with open(STATE_FILE) as f:
        return json.load(f)


def save_state(state):
    """Persist state to state.json atomically."""
    atomic_write(STATE_FILE, state)


def load_dod_templates():
    """Load DoD templates, or exit with error if not found."""
    if not os.path.exists(DOD_TEMPLATE_FILE):
        print("Error: dod-templates.json not found.")
        sys.exit(2)
    with open(DOD_TEMPLATE_FILE) as f:
        return json.load(f)


def format_check(done):
    """Return a checkbox character."""
    return "[x]" if done else "[ ]"


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_init():
    """Initialize state.json from DoD templates."""
    if os.path.exists(STATE_FILE):
        print("Error: state.json already exists. Delete it first to reinitialize.")
        sys.exit(1)

    templates = load_dod_templates()
    timestamp = now_iso()

    phases = {}
    for phase in PHASE_ORDER:
        items = templates.get(phase, [])
        dod = [{"item": item, "done": False} for item in items]
        entered_at = timestamp if phase == "Bootstrap" else None
        phases[phase] = {
            "dod": dod,
            "entered_at": entered_at,
            "completed_at": None,
        }

    state = {
        "current_phase": "Bootstrap",
        "phases": phases,
        "transitions": [],
        "created_at": timestamp,
    }

    save_state(state)
    print("Initialized .sdlc/state.json")
    print("Current phase: Bootstrap")


def cmd_current():
    """Print the current phase."""
    state = load_state()
    print(state["current_phase"])


def cmd_status():
    """Print current phase and its DoD checklist."""
    state = load_state()
    phase = state["current_phase"]
    phase_data = state["phases"][phase]
    dod = phase_data["dod"]

    total = len(dod)
    done_count = sum(1 for d in dod if d["done"])

    print(f"Phase: {phase}")
    print(f"Entered: {phase_data['entered_at']}")
    print(f"DoD progress: {done_count}/{total}")
    print()
    print("Definition of Done:")
    for i, item in enumerate(dod):
        check = format_check(item["done"])
        print(f"  {i}. {check} {item['item']}")

    if done_count == total:
        print()
        print("All DoD items complete. Ready to transition.")
    else:
        remaining = total - done_count
        print()
        print(f"{remaining} item(s) remaining before transition is allowed.")


def cmd_check(index_str):
    """Mark a DoD item as complete."""
    state = load_state()
    phase = state["current_phase"]
    dod = state["phases"][phase]["dod"]

    try:
        index = int(index_str)
    except ValueError:
        print(f"Error: '{index_str}' is not a valid index.")
        sys.exit(2)

    if index < 0 or index >= len(dod):
        print(f"Error: index {index} out of range (0-{len(dod) - 1}).")
        sys.exit(2)

    if dod[index]["done"]:
        print(f"Item {index} is already checked.")
        return

    dod[index]["done"] = True
    save_state(state)
    print(f"Checked: {dod[index]['item']}")

    done_count = sum(1 for d in dod if d["done"])
    print(f"DoD progress: {done_count}/{len(dod)}")


def cmd_uncheck(index_str):
    """Mark a DoD item as incomplete."""
    state = load_state()
    phase = state["current_phase"]
    dod = state["phases"][phase]["dod"]

    try:
        index = int(index_str)
    except ValueError:
        print(f"Error: '{index_str}' is not a valid index.")
        sys.exit(2)

    if index < 0 or index >= len(dod):
        print(f"Error: index {index} out of range (0-{len(dod) - 1}).")
        sys.exit(2)

    if not dod[index]["done"]:
        print(f"Item {index} is already unchecked.")
        return

    dod[index]["done"] = False
    save_state(state)
    print(f"Unchecked: {dod[index]['item']}")

    done_count = sum(1 for d in dod if d["done"])
    print(f"DoD progress: {done_count}/{len(dod)}")


def cmd_transition(target_phase, reason=None):
    """Transition to a new phase, gating on DoD completion."""
    state = load_state()
    current = state["current_phase"]

    # Validate target phase exists
    if target_phase not in PHASE_ORDER:
        print(f"Error: '{target_phase}' is not a valid phase.")
        print(f"Valid phases: {', '.join(PHASE_ORDER)}")
        sys.exit(2)

    # Cannot transition to current phase
    if target_phase == current:
        print(f"Error: already in phase '{current}'.")
        sys.exit(1)

    # Check DoD for current phase
    dod = state["phases"][current]["dod"]
    incomplete = [d for d in dod if not d["done"]]

    if incomplete:
        print(f"Cannot transition from {current} to {target_phase}.")
        print(f"{len(incomplete)} DoD item(s) still incomplete:")
        for d in incomplete:
            print(f"  [ ] {d['item']}")
        sys.exit(1)

    # Perform the transition
    timestamp = now_iso()

    # Mark current phase as completed
    state["phases"][current]["completed_at"] = timestamp

    # Mark target phase as entered
    state["phases"][target_phase]["entered_at"] = timestamp

    # Record transition
    transition_record = {
        "from": current,
        "to": target_phase,
        "at": timestamp,
    }
    if reason:
        transition_record["reason"] = reason

    state["transitions"].append(transition_record)
    state["current_phase"] = target_phase

    save_state(state)
    print(f"Transitioned: {current} -> {target_phase}")
    if reason:
        print(f"Reason: {reason}")
    print(f"Entered {target_phase} at {timestamp}")


def cmd_history():
    """Print the phase transition log."""
    state = load_state()
    transitions = state["transitions"]

    if not transitions:
        print("No transitions recorded yet.")
        print(f"Current phase: {state['current_phase']} (initial)")
        return

    print("Phase Transition History:")
    print()
    for i, t in enumerate(transitions, 1):
        print(f"  {i}. {t['from']} -> {t['to']}")
        print(f"     At: {t['at']}")
        if "reason" in t:
            print(f"     Reason: {t['reason']}")
        print()

    print(f"Current phase: {state['current_phase']}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def usage():
    print("Usage: tracker.py <command> [args]")
    print()
    print("Commands:")
    print("  init                          Initialize state.json")
    print("  current                       Print current phase")
    print("  status                        Print phase + DoD checklist")
    print("  check <index>                 Mark DoD item complete")
    print("  uncheck <index>               Mark DoD item incomplete")
    print("  transition <phase> [reason]   Transition to phase (gates on DoD)")
    print("  history                       Print transition log")
    sys.exit(2)


def main():
    if len(sys.argv) < 2:
        usage()

    command = sys.argv[1]

    if command == "init":
        cmd_init()
    elif command == "current":
        cmd_current()
    elif command == "status":
        cmd_status()
    elif command == "check":
        if len(sys.argv) < 3:
            print("Error: 'check' requires an item index.")
            sys.exit(2)
        cmd_check(sys.argv[2])
    elif command == "uncheck":
        if len(sys.argv) < 3:
            print("Error: 'uncheck' requires an item index.")
            sys.exit(2)
        cmd_uncheck(sys.argv[2])
    elif command == "transition":
        if len(sys.argv) < 3:
            print("Error: 'transition' requires a target phase.")
            sys.exit(2)
        reason = " ".join(sys.argv[3:]) if len(sys.argv) > 3 else None
        cmd_transition(sys.argv[2], reason)
    elif command == "history":
        cmd_history()
    else:
        print(f"Error: unknown command '{command}'")
        usage()


if __name__ == "__main__":
    main()
