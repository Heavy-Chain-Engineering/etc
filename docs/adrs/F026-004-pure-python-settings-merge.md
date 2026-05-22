# ADR-004: settings.json merge is pure Python, no shell-embedded heredoc

**Date:** 2026-05-22
**Status:** Accepted

**Context:** install.sh:368-401 currently merges hook wiring into the operator's settings.json via a Python heredoc invoked from bash:

```
python3 -c "
import json
with open('$(_to_native_path "$SETTINGS")') as f:
    settings = json.load(f)
..."
```

This pattern was the root cause of the Windows unicodeescape incident documented in `memory/feedback-windows-install-portability.md`: bash string-interpolates the cygpath-converted Windows path into a single-quoted Python string, and the embedded backslashes (`C:\Users\...`) trip the Python source-code unicodeescape decoder before json.load is even called.

Three candidates for the rewrite:

- (a) Pure Python (json stdlib) inside `etc_installer/settings_merge.py`. No string interpolation. Paths are `pathlib.Path` objects.
- (b) Shell out to jq for the merge. New hard dependency on jq.
- (c) Keep the heredoc pattern in the new bash bootstrap. Carries the antipattern forward.

**Decision:** Pure Python (option a). `etc_installer/settings_merge.py` reads the target settings.json via `pathlib.Path.read_text()`, parses with `json.loads`, mutates the `hooks` key, writes back via `json.dumps` with indent=2 and a trailing newline.

**Consequences:**
- *Easier*: The unicodeescape failure mode is structurally impossible — there is no bash-to-Python string interpolation anywhere. Path-translation for Windows-Git-Bash happens inside the Python module via `etc_installer/paths.py::to_native_path` (cygpath shell-out, see ADR-context — this ADR focuses on the merge, not the path translation).
- *Harder*: The merge logic must handle the case where the existing settings.json is invalid JSON (per spec Edge Case 5: print error, skip merge, continue with non-zero final exit).
- *Deferred*: A general JSON-merge utility (e.g., merging nested keys other than `hooks`). YAGNI — only the `hooks` section is replaced today.
- *Cannot defer*: The new settings_merge.py MUST preserve every existing top-level key in the operator's settings.json. Tests must assert this (existing test_install_sh_cli.py and test_windows_compatibility.py assertions cover the equivalent in bash; new tests/test_etc_installer.py covers the Python module).

**Related ADRs:** ADR-002 (typer + rich — settings_merge is called by an install_steps function; rich.Console emits the ✓/⚠/✗ status line for this step).
