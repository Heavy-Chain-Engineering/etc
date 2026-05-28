"""settings_merge — pure-Python hooks-section merge for settings.json.

Replaces the shell-embedded Python heredoc at install.sh:368-401 with a
pure Python module. Rationale lives in
`docs/adrs/Ftmp-5afddbce-004-pure-python-settings-merge.md`: the heredoc
pattern was the root cause of the Windows ``unicodeescape`` incident
(memory/feedback-windows-install-portability.md) because bash
string-interpolates cygpath-converted Windows paths into a single-quoted
Python source string, and embedded backslashes trip the Python
unicodeescape decoder before json.load fires.

Pure Python eliminates that failure mode structurally — no bash → Python
string interpolation anywhere.

Per design.md Module Structure, this module is the Infrastructure layer
and MUST NOT import from cli or install_steps.
"""

from __future__ import annotations

import json
from pathlib import Path

# Token the compiler writes in place of an absolute hooks directory.
# The installer substitutes it with the resolved target hooks dir at
# install time, since the compiler can't know --target-dir.
HOOKS_DIR_PLACEHOLDER = "{{ETC_HOOKS_DIR}}"


def substitute_hooks_dir(template_text: str, hooks_dir: Path) -> str:
    """Replace ``{{ETC_HOOKS_DIR}}`` with the resolved hooks directory.

    Operates on the raw template text rather than the parsed JSON so a
    single pass handles every hook command without walking the nested
    Claude Code hooks schema.
    """
    return template_text.replace(HOOKS_DIR_PLACEHOLDER, str(hooks_dir))


def merge_hooks(
    target_settings: Path, template_path: Path, hooks_dir: Path
) -> None:
    """Replace the ``hooks`` top-level key in ``target_settings`` with the
    template's ``hooks`` value, substituting ``{{ETC_HOOKS_DIR}}``.

    Reads ``target_settings`` and ``template_path`` as JSON, replaces the
    ``hooks`` key on the target dict with the template's ``hooks`` value,
    and writes the merged dict back to ``target_settings`` with
    ``json.dumps(merged, indent=2) + "\\n"``. Every other top-level key
    in the target is preserved byte-for-byte (the merge replaces only
    the ``hooks`` section, per install.sh:386 contract).

    Edge case 5 (spec.md): if the target file is not valid JSON,
    ``json.JSONDecodeError`` propagates to the caller. The target file
    is NOT overwritten. The caller (install_steps.py) catches the error
    and emits ``✗ settings.json at <path> is not valid JSON — skipping
    merge`` via rich.Console.

    Args:
        target_settings: Path to the operator's settings.json (read +
            write). Must contain valid JSON; otherwise JSONDecodeError
            is raised before any write happens.
        template_path: Path to the read-only template JSON containing the
            canonical ``hooks`` section (typically
            ``dist/settings-hooks.json``).
        hooks_dir: Resolved install hooks directory (typically
            ``target_dir / 'hooks'``). Substituted for
            ``{{ETC_HOOKS_DIR}}`` in every hook command path.

    Raises:
        json.JSONDecodeError: when ``target_settings`` contains invalid
            JSON. The target file is left untouched.
    """
    target_text = target_settings.read_text(encoding="utf-8")
    template_text = substitute_hooks_dir(
        template_path.read_text(encoding="utf-8"), hooks_dir
    )

    # Parse target FIRST so an invalid target raises before any write
    # touches the filesystem (Edge Case 5).
    merged = json.loads(target_text)
    template = json.loads(template_text)

    merged["hooks"] = template["hooks"]

    target_settings.write_text(
        json.dumps(merged, indent=2) + "\n",
        encoding="utf-8",
    )
