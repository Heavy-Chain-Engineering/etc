#!/bin/bash
# standards/code/profiles/python/baseline-verify.sh
#
# Architecture-baseline conformance reference profile (python / generic-tree).
#
# The python reference checker for the ENFORCE stage
# (F-2026-06-10-brownfield-architecture-baseline, ADR-004). v1 ships this
# profile only; other profiles warn-and-skip at the dispatcher (the proven
# runtime-verify.sh staged-rollout shape). Sibling of this dir's behavioral
# primitive runtime-verify.sh.
#
# Contract (v1, additive-only — ADR-004 + design.md API Contracts §2):
#   stdin : {"repo_root": <str>, "rules": [{"rule_id": <str>,
#                                           "statement": <str>}, ...]}
#           (the dispatcher's thinned jq projection; rules already filtered to
#            mechanizable + selected. JSON on stdin, never shell args.)
#   stdout: {"results": [{"rule_id": <str>,
#                         "status": "pass"|"fail"|"no-check",
#                         "evidence": <str>}]}
#   exit  : 0 = the profile RAN (read per-rule `status` for verdicts);
#           non-zero = the profile itself could not stand up.
#
# status semantics (closed enum):
#   pass     -> the rule compiled to a tree assertion and the tree satisfies it
#   fail     -> the rule compiled to a tree assertion and the tree VIOLATES it
#               (evidence names the rule and the offending path(s))
#   no-check -> the statement does not match a mechanizable pattern this v1
#               profile understands; evidence says why. NEVER a fake pass — an
#               un-evaluable rule is honestly reported, not silently greened.
#
# Mechanizable statement grammar (v1 — honest + minimal). Each pattern compiles
# to a grep/glob assertion over the tree. Matching is case-insensitive on the
# verb phrasing; the glob/needle tokens are taken verbatim.
#
#   (A) "files matching <GLOB> must not contain <NEEDLE>"
#       -> every file whose path matches <GLOB> is grepped for <NEEDLE> (fixed
#          string). A match anywhere is a violation.
#   (B) "directory <DIR> must not contain <GLOB> files"   (e.g. "*.spec")
#       -> a violation if any file under <DIR> matches <GLOB>.
#       (also accepts "<DIR> must not contain <GLOB> files")
#
# Anything else -> no-check.
#
# All path/needle tokens cross the boundary as JSON and reach grep/find as
# array arguments or -F fixed strings; they are never interpolated into a shell
# command string (injection defense, parity with runtime-verify.sh).

set -u

INPUT=$(cat)

REPO_ROOT=$(printf '%s' "$INPUT" | jq -r '.repo_root // "."')
if [ -z "$REPO_ROOT" ] || [ "$REPO_ROOT" = "null" ]; then
  REPO_ROOT="."
fi

cd "$REPO_ROOT" || {
  echo "[python/baseline-verify] FAILED: repo_root not usable as a directory." >&2
  exit 2
}

# jq must be available to read the per-rule contract; without it the profile
# cannot stand up (whole-profile error, exit 2 — distinct from a per-rule fail).
if ! command -v jq >/dev/null 2>&1; then
  echo "[python/baseline-verify] FAILED: jq is not runnable in this environment." >&2
  exit 2
fi

# emit_result ACCUMULATES one {rule_id,status,evidence} object into RESULTS_JSON.
RESULTS_JSON="[]"
emit_result() {
  local rid="$1" status="$2" evidence="$3"
  RESULTS_JSON=$(printf '%s' "$RESULTS_JSON" | jq \
    --arg rid "$rid" --arg st "$status" --arg ev "$evidence" \
    '. + [{"rule_id": $rid, "status": $st, "evidence": $ev}]')
}

# files_matching_glob: list tree files whose path matches a shell GLOB, honoring
# `**`. find's -path is used (not the shell) so the glob is data, not code.
# A `**` in the glob is translated to find's `*` (find -path already crosses
# directory separators with `*`). Leading "./"-relative.
files_matching_glob() {
  local glob="$1"
  # Normalize the glob to a find -path pattern. find's '*' already spans '/'
  # (one '*' matches at any depth), so:
  #   - '**' collapses to a single '*'
  #   - the residual '*/*' (from '**/' plus a following segment) collapses to
  #     '*' as well, so 'src/**/*.py' -> 'src/*.py' matches at ANY depth,
  #     including a file directly under src/.
  # sed keeps the substitution unambiguous (bash ${//} replacement-quoting
  # differs across versions and previously emitted literal quote/backslash
  # characters into the pattern). Loop the '*/*' collapse to a fixpoint.
  local fpath
  fpath=$(printf '%s' "$glob" | sed -e 's#\*\*#*#g')
  while printf '%s' "$fpath" | grep -q '\*/\*'; do
    fpath=$(printf '%s' "$fpath" | sed -e 's#\*/\*#*#g')
  done
  # Ensure a leading ./ so -path matches find's emitted paths.
  case "$fpath" in
    ./*) : ;;
    /*)  fpath=".${fpath}" ;;
    *)   fpath="./${fpath}" ;;
  esac
  find . -type f -path "$fpath" 2>/dev/null
}

# check_files_must_not_contain GLOB NEEDLE -> echoes a single line
# "<matched_count>\t<first offending 'path: line'>". The count and hit travel
# on stdout (NOT a global): callers invoke this via command substitution, a
# subshell whose globals never reach the parent. The caller splits on the tab.
check_files_must_not_contain() {
  local glob="$1" needle="$2"
  local matched=0 hit=""
  while IFS= read -r f; do
    [ -z "$f" ] && continue
    matched=$((matched + 1))
    if [ -z "$hit" ] && grep -nF -- "$needle" "$f" >/dev/null 2>&1; then
      local line
      line=$(grep -nF -- "$needle" "$f" 2>/dev/null | head -1 | tr -d '\r' | cut -c1-180)
      hit="${f}: ${line}"
    fi
  done < <(files_matching_glob "$glob")
  printf '%s\t%s' "$matched" "$hit"
}

# dir_first_match DIR GLOB -> echoes the first file under DIR whose basename
# matches GLOB, or nothing. The caller checks `[ -d DIR ]` itself: a global set
# inside this function would be lost because callers invoke it via command
# substitution (a subshell), so directory existence is decided in the caller's
# own scope, never smuggled back through a global.
dir_first_match() {
  local base="$1" glob="$2"
  find "$base" -type f -name "$glob" 2>/dev/null | head -1
}

# ── Per-rule dispatch ───────────────────────────────────────────────────────
#
# Read rules one JSON object per line (jq -c). For each, lowercase the statement
# to classify the verb phrasing, then extract tokens with a regex against the
# ORIGINAL statement (tokens are case-preserved).

RULE_COUNT=$(printf '%s' "$INPUT" | jq '.rules | length' 2>/dev/null || echo 0)

while IFS= read -r RULE; do
  [ -z "$RULE" ] && continue

  RID=$(printf '%s' "$RULE" | jq -r '.rule_id // "<unknown>"')
  STMT=$(printf '%s' "$RULE" | jq -r '.statement // ""')
  STMT_LC=$(printf '%s' "$STMT" | tr '[:upper:]' '[:lower:]')

  # ── Pattern (A): files matching <GLOB> must not contain <NEEDLE> ──────────
  if printf '%s' "$STMT_LC" | grep -qE 'files matching .+ must not contain .+'; then
    GLOB=$(printf '%s' "$STMT" | sed -nE 's/.*[Ff]iles matching[[:space:]]+([^[:space:]]+)[[:space:]]+must not contain[[:space:]]+(.+)$/\1/p')
    NEEDLE=$(printf '%s' "$STMT" | sed -nE 's/.*[Ff]iles matching[[:space:]]+([^[:space:]]+)[[:space:]]+must not contain[[:space:]]+(.+)$/\2/p')
    # Trim a trailing period and surrounding quotes from the needle.
    NEEDLE="${NEEDLE%.}"
    NEEDLE="${NEEDLE%\"}"; NEEDLE="${NEEDLE#\"}"
    NEEDLE="${NEEDLE%\'}"; NEEDLE="${NEEDLE#\'}"

    if [ -z "$GLOB" ] || [ -z "$NEEDLE" ]; then
      emit_result "$RID" "no-check" \
        "statement matched the 'files matching X must not contain Y' shape but X or Y did not parse: '${STMT}'"
      continue
    fi

    OUT=$(check_files_must_not_contain "$GLOB" "$NEEDLE")
    MATCHED="${OUT%%$'\t'*}"
    HIT="${OUT#*$'\t'}"
    if [ -n "$HIT" ]; then
      emit_result "$RID" "fail" \
        "rule ${RID} violated: file matching '${GLOB}' contains '${NEEDLE}' -> ${HIT}"
    else
      emit_result "$RID" "pass" \
        "rule ${RID} satisfied: ${MATCHED} file(s) matched '${GLOB}'; none contain '${NEEDLE}'"
    fi
    continue
  fi

  # ── Pattern (B): [directory] <DIR> must not contain <GLOB> files ──────────
  if printf '%s' "$STMT_LC" | grep -qE 'must not contain [^[:space:]]+ files'; then
    DIR=$(printf '%s' "$STMT" | sed -nE 's/^([Dd]irectory[[:space:]]+)?([^[:space:]]+)[[:space:]]+must not contain[[:space:]]+([^[:space:]]+)[[:space:]]+files.*$/\2/p')
    FGLOB=$(printf '%s' "$STMT" | sed -nE 's/^([Dd]irectory[[:space:]]+)?([^[:space:]]+)[[:space:]]+must not contain[[:space:]]+([^[:space:]]+)[[:space:]]+files.*$/\3/p')

    if [ -z "$DIR" ] || [ -z "$FGLOB" ]; then
      emit_result "$RID" "no-check" \
        "statement matched the 'DIR must not contain GLOB files' shape but DIR or GLOB did not parse: '${STMT}'"
      continue
    fi

    DIR_BASE="${DIR%/}"
    [ -z "$DIR_BASE" ] && DIR_BASE="."
    if [ ! -d "$DIR_BASE" ]; then
      emit_result "$RID" "pass" \
        "rule ${RID} satisfied vacuously: directory '${DIR}' does not exist; no '${FGLOB}' files possible"
      continue
    fi
    HIT=$(dir_first_match "$DIR_BASE" "$FGLOB")
    if [ -n "$HIT" ]; then
      emit_result "$RID" "fail" \
        "rule ${RID} violated: directory '${DIR}' contains a '${FGLOB}' file -> ${HIT}"
    else
      emit_result "$RID" "pass" \
        "rule ${RID} satisfied: directory '${DIR}' contains no '${FGLOB}' files"
    fi
    continue
  fi

  # ── No mechanizable pattern matched -> honest no-check (never fake pass) ──
  emit_result "$RID" "no-check" \
    "v1 python profile cannot mechanically evaluate this statement (no grep/glob assertion compiled): '${STMT}'"

done < <(printf '%s' "$INPUT" | jq -c '.rules[]? // empty')

# RULE_COUNT is informational; the results array is authoritative.
printf '%s' "$RESULTS_JSON" | jq -c '{"results": .}'
exit 0
