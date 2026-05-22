#!/usr/bin/env bash
# etc default status line — emitted by the etc Python installer
# (Ftmp-5afddbce task 004). Operators who answer "y" to BR-007's
# overwrite prompt get this script copied to $TARGET_DIR/scripts/
# and the matching `statusLine` key written into settings.json.
#
# The default behavior prints a single-line, minimal context strip:
# git branch + working-tree dirtiness marker + a short cwd basename.
# Operators are expected to fork this script (it is theirs after
# install) — etc owns only the default; the operator owns customization.

set -euo pipefail

branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo '-')"
dirty=""
if ! git diff --quiet 2>/dev/null || ! git diff --cached --quiet 2>/dev/null; then
  dirty="*"
fi
cwd_base="$(basename "$PWD")"

printf '[etc] %s %s%s' "$cwd_base" "$branch" "$dirty"
