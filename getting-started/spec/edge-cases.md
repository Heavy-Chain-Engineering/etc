# Edge Cases and Error Scenarios

## File Access Errors

### E1: state.json does not exist
- **Trigger:** `.sdlc/state.json` missing (project not initialized)
- **Expected behavior:** Dashboard shows "No SDLC state found. Run `tracker.py init` to initialize."
- **API response:** Return a default/empty state with a message field, not a 500 error

### E2: tasks.json does not exist
- **Trigger:** `.taskmaster/tasks/tasks.json` missing (TaskMaster not set up)
- **Expected behavior:** Dashboard shows task summary as "No tasks found" with all counts at 0
- **API response:** Return zeroed task summary, not a 500 error

### E3: state.json is malformed JSON
- **Trigger:** File exists but contains invalid JSON
- **Expected behavior:** Dashboard shows "Error reading SDLC state: invalid JSON"
- **API response:** Return 200 with error message in response body (not 500)

### E4: tasks.json is malformed JSON
- **Trigger:** File exists but contains invalid JSON
- **Expected behavior:** Dashboard shows "Error reading tasks: invalid JSON"
- **API response:** Return 200 with error message in response body (not 500)

### E5: Files change between reads
- **Trigger:** State file is being written to by tracker.py while dashboard reads it
- **Expected behavior:** Graceful handling — show stale data or error, never crash
- **Mitigation:** Read entire file content atomically, parse in memory

## Data Edge Cases

### E6: Zero DoD items for current phase
- **Trigger:** Phase has empty DoD list
- **Expected behavior:** Show "No definition of done items for this phase"
- **Progress bar:** Show 0% or N/A

### E7: Zero tasks
- **Trigger:** tasks.json exists but has empty task list
- **Expected behavior:** Show all task counts as 0

### E8: Unknown task status values
- **Trigger:** Task has a status not in the expected set
- **Expected behavior:** Count it under "other" or ignore gracefully, do not crash

### E9: Missing fields in state.json
- **Trigger:** state.json exists but is missing expected fields (e.g., no transitions array)
- **Expected behavior:** Use sensible defaults (empty list for transitions, "Unknown" for missing phase)

## Frontend Edge Cases

### E10: API unreachable during polling
- **Trigger:** Server goes down while dashboard is open
- **Expected behavior:** Show "Connection lost — retrying..." message, keep polling
- **Recovery:** Resume normal display when API becomes available again

### E11: Very long DoD item text
- **Trigger:** DoD item description is extremely long
- **Expected behavior:** Text wraps cleanly, does not break layout

### E12: Many tasks (100+)
- **Trigger:** Large task list from TaskMaster
- **Expected behavior:** Summary counts remain fast and correct; no performance degradation
