"""sandbox_config — interactive sandbox-defaults installer.

Implements BR-008 / AC-008 of Ftmp-5afddbce: prompt the operator
(when running INTERACTIVE) to opt into etc's default sandbox
configuration, which sets ``permissions.defaultMode`` to a non-prompting
mode plus seed ``allow`` / ``ask`` / ``deny`` lists. On affirmative
answer, the installer merges the canonical defaults into the top-level
``permissions`` key of ``$TARGET_DIR/settings.json`` (preserving every
other top-level key).

Non-interactive runs (``--client`` flag set → ``OperatorMode.NON_INTERACTIVE``)
skip the prompt and the merge entirely. The sandbox-defaults install
is operator-opt-in by design — silently switching a fresh operator
into ``defaultMode: auto`` would violate BR-008's prompt contract and
the broader sandbox-bypass-discipline principle
(memory/feedback-sandbox-bypass-discipline.md).

The verbatim prompt string is defined at module level as
``BR_008_PROMPT_LITERAL`` and printed via Python's built-in ``print()``
for the same word-wrap reason documented in
``etc_installer.status_line``.

Per design.md Module Structure this module sits in the Infrastructure
layer and MUST NOT import from cli or install_steps.
"""

from __future__ import annotations

import json
from pathlib import Path

from rich.prompt import Prompt

from etc_installer.preflights import OperatorMode

# ── BR-008 verbatim prompt literal ────────────────────────────────────────
#
# spec.md BR-008 mandates this string byte-for-byte. The E501 line-too-long
# suppression is justified by F021 diagnostic-discipline (same rationale
# documented in etc_installer.status_line for BR_007_PROMPT_LITERAL).
BR_008_PROMPT_LITERAL = "Install the etc default sandbox config? This enables auto-mode without --dangerously-skip-permissions. [y/N]"  # noqa: E501


# Canonical permissions payload merged into settings.json on affirmative
# install. Shape mirrors Claude Code's published permissions schema
# (defaultMode + allow/ask/deny lists). The defaultMode is ``auto`` —
# matches the author's working settings.json:30 and aligns with BR-008's
# advertised "auto-mode without --dangerously-skip-permissions" outcome.
#
# allow: low-risk read-only / VCS / cloud-CLI prefixes the operator
#   should not be re-prompted for on each invocation.
# ask: file-system surfaces where the operator wants explicit consent
#   on each touch (sensitive dotfiles).
# deny: hard-blocked paths regardless of mode (secrets, system dirs).
#
# The lists are conservative defaults — operators can extend them
# post-install by editing settings.json directly. We do NOT merge into
# existing allow/ask/deny lists if they already exist; BR-008's contract
# is "merge sandbox defaults into permissions block" (top-level key
# replace), not "union with existing entries". The operator was warned
# by the prompt and consented.
_SANDBOX_DEFAULTS: dict[str, object] = {
    "defaultMode": "auto",
    "allow": [
        "Bash(git *)",
        "Bash(gh *)",
        "Bash(docker *)",
        "Bash(docker compose *)",
        "Bash(aws *)",
        "Bash(gcloud *)",
        "Bash(az *)",
        "Bash(terraform *)",
        "Bash(kubectl *)",
        "Bash(helm *)",
        "Bash(pulumi *)",
        "Bash(sam *)",
        "Bash(cdk *)",
        "Bash(serverless *)",
    ],
    "ask": [],
    "deny": [
        "Read(~/.ssh/**)",
        "Read(~/.gnupg/**)",
        "Read(~/.aws/credentials)",
        "Read(~/.netrc)",
        "Read(**/.env)",
        "Read(**/.env.*)",
    ],
}

_PERMISSIONS_KEY = "permissions"


def install_sandbox_config(target_dir: Path, mode: OperatorMode) -> None:
    """Install (or skip) the etc default sandbox-config defaults.

    INTERACTIVE: print the verbatim BR-008 prompt to stdout, then read
    operator input via ``rich.prompt.Prompt.ask``. On ``y`` / ``yes``
    (case-insensitive), merge the canonical sandbox defaults into the
    top-level ``permissions`` key of ``target_dir/settings.json``
    (preserving every other top-level key). On ``n``, empty input, or
    any other answer, skip.

    NON_INTERACTIVE: skip the prompt AND the merge entirely. The
    operator's settings.json is left untouched.

    Args:
        target_dir: Resolved install target — either ``$HOME/.claude``
            (``--scope global``) or ``$PWD/.claude`` (``--scope
            project``). The directory must contain an existing
            ``settings.json``; this function does NOT create it.
        mode: OperatorMode.INTERACTIVE → prompt + conditional merge;
            OperatorMode.NON_INTERACTIVE → skip entirely.
    """
    if mode is OperatorMode.NON_INTERACTIVE:
        return

    # Verbatim BR-008 echo via plain print() — see status_line.py for
    # the rationale (rich.Console word-wraps long lines).
    print(BR_008_PROMPT_LITERAL)
    answer = Prompt.ask("", default="n", show_default=False)

    if answer.strip().lower() not in {"y", "yes"}:
        return

    _merge_permissions(target_dir)


def _merge_permissions(target_dir: Path) -> None:
    """Merge the canonical sandbox defaults into settings.json.

    Reads ``target_dir/settings.json``, replaces the top-level
    ``permissions`` key with the canonical defaults, and writes back
    via ``json.dumps(merged, indent=2) + "\\n"``. Every other top-level
    key is preserved byte-for-byte.

    The replacement (not union) shape matches BR-008's "merge sandbox
    defaults into permissions block" contract and mirrors
    settings_merge.merge_hooks's replacement-of-hooks-key pattern.
    """
    settings_path = target_dir / "settings.json"
    body = json.loads(settings_path.read_text(encoding="utf-8"))
    body[_PERMISSIONS_KEY] = _SANDBOX_DEFAULTS
    settings_path.write_text(
        json.dumps(body, indent=2) + "\n",
        encoding="utf-8",
    )
