#!/bin/bash
# standards/code/profiles/python/runtime-verify.sh
#
# Gap A behavioral / runtime-verify reference profile (python / CLI).
#
# Stands etc's own CLI up against REAL artifacts (no mocks) and proves a set
# of declared-live acceptance-criteria (AC) outcomes at runtime. The "app"
# here is the CLI / package invoked end-to-end against a real project tree;
# the behavioral assertion for each AC lives in an AC-tagged e2e/smoke test.
#
# Contract (v1, additive-only — see ADR-001 + design.md API Contracts):
#   stdin : {"feature_path": <str>, "live_ac_ids": ["AC-3", ...]}
#   stdout: {"results": [{"ac_id": <str>,
#                         "status": "pass"|"fail"|"no-test",
#                         "evidence": <str>}]}
#   exit  : 0 = the profile ran (read per-AC `status` for verdicts);
#           non-zero = the profile itself could not stand up.
#
# AC->test binding: for each ac_id "AC-N" the profile selects the pytest test
# bound to it by the name convention  test_ac_N_*  via `pytest -k`.
#
# (The `@pytest.mark.ac("AC-N")` marker is the documented alternative binding,
# but pytest's `-m` expression language selects on marker *names*, not marker
# *arguments* — `-m 'ac("AC-N")'` is a syntax error — so argument-keyed marker
# selection would require a custom collection plugin and a registered marker in
# a shared pytest config, both outside this task's files_in_scope. Per the task
# note we therefore use the name-convention selection, which is self-contained.)
#
# status is:
#   pass    -> a bound test ran and the selection passed
#   fail    -> a bound test ran and the selection failed (evidence = summary)
#   no-test -> NO test matched this ac_id (a declared-live AC with no test;
#              a downstream gate failure — here we just report it)
#
# Inputs cross the boundary as JSON on stdin and are read with jq; AC ids and
# paths are never interpolated into a shell-command string (injection defense).
# Sibling of this dir's structural primitive verify-green.sh.

set -u

INPUT=$(cat)

FEATURE_PATH=$(printf '%s' "$INPUT" | jq -r '.feature_path // "."')
if [ -z "$FEATURE_PATH" ] || [ "$FEATURE_PATH" = "null" ]; then
  FEATURE_PATH="."
fi

cd "$FEATURE_PATH" || {
  echo "[python/runtime-verify] FAILED: feature_path not usable as a directory." >&2
  exit 2
}

# Choose a pytest runner. Prefer `uv run pytest` when a uv project is present;
# fall back to bare pytest so the profile is dogfoodable in a plain temp dir.
PYTEST_CMD=(python3 -m pytest)
if command -v uv >/dev/null 2>&1 && [ -f pyproject.toml ]; then
  PYTEST_CMD=(uv run pytest)
fi

# `python3 -m pytest` requires the pytest module to be importable. If it is
# not, the profile cannot stand up -> whole-profile error (exit 2).
if ! "${PYTEST_CMD[@]}" --version >/dev/null 2>&1; then
  echo "[python/runtime-verify] FAILED: pytest is not runnable in this environment." >&2
  exit 2
fi

# ac_n: extract the numeric suffix N from "AC-N" (digits only).
ac_n() {
  printf '%s' "$1" | sed -n 's/^AC-\([0-9][0-9]*\)$/\1/p'
}

# Build the JSON results array, one element per declared-live ac_id.
RESULTS_JSON="[]"

# Read live AC ids one per line (jq -r '.live_ac_ids[]'); empty/missing -> none.
while IFS= read -r AC_ID; do
  [ -z "$AC_ID" ] && continue

  N=$(ac_n "$AC_ID")
  if [ -z "$N" ]; then
    # Not an AC-<digits> id; treat as no-test (no binding possible).
    STATUS="no-test"
    EVIDENCE="ac_id '$AC_ID' is not of the form AC-<n>; no test binding"
    RESULTS_JSON=$(printf '%s' "$RESULTS_JSON" | jq \
      --arg ac "$AC_ID" --arg st "$STATUS" --arg ev "$EVIDENCE" \
      '. + [{"ac_id": $ac, "status": $st, "evidence": $ev}]')
    continue
  fi

  # Probe the AC->test binding by name convention. --collect-only never
  # executes a test, so this is a cheap, side-effect-free probe. A `::`
  # node id in the output means at least one test matched.
  #
  # The selector is the trailing-underscore form `test_ac_N_` (the documented
  # `test_ac_N_*` convention). The underscore is load-bearing: `pytest -k`
  # does bare substring matching, so a selector of `test_ac_1` would also
  # match `test_ac_12_*` (AC-1 stealing AC-12's tests). `test_ac_1_` cannot
  # match `test_ac_12_`, so the boundary is preserved.
  NAME_EXPR="test_ac_${N}_"

  COLLECT_OUT=$("${PYTEST_CMD[@]}" -q --collect-only \
    -k "$NAME_EXPR" -p no:cacheprovider 2>/dev/null)

  if ! printf '%s' "$COLLECT_OUT" | grep -q '::'; then
    # No test matched this declared-live AC.
    STATUS="no-test"
    EVIDENCE="no pytest test matched AC-$N (name convention test_ac_${N}_*)"
    RESULTS_JSON=$(printf '%s' "$RESULTS_JSON" | jq \
      --arg ac "$AC_ID" --arg st "$STATUS" --arg ev "$EVIDENCE" \
      '. + [{"ac_id": $ac, "status": $st, "evidence": $ev}]')
    continue
  fi

  # A binding exists: run it.
  RUN_OUT=$("${PYTEST_CMD[@]}" -q -k "$NAME_EXPR" \
    -p no:cacheprovider --no-header 2>&1)
  RUN_EXIT=$?

  # Evidence: the pytest summary line (last non-empty line), sanitized to a
  # single line and bounded length.
  EVIDENCE=$(printf '%s' "$RUN_OUT" | grep -E '(passed|failed|error|no tests ran)' \
    | tail -1 | tr -d '\r' | cut -c1-512)
  [ -z "$EVIDENCE" ] && EVIDENCE=$(printf '%s' "$RUN_OUT" | tail -1 | tr -d '\r' | cut -c1-512)

  if [ "$RUN_EXIT" -eq 0 ]; then
    STATUS="pass"
  else
    STATUS="fail"
  fi

  RESULTS_JSON=$(printf '%s' "$RESULTS_JSON" | jq \
    --arg ac "$AC_ID" --arg st "$STATUS" --arg ev "$EVIDENCE" \
    '. + [{"ac_id": $ac, "status": $st, "evidence": $ev}]')

done < <(printf '%s' "$INPUT" | jq -r '.live_ac_ids[]? // empty')

printf '%s' "$RESULTS_JSON" | jq -c '{"results": .}'
exit 0
