"""F021 fixture — deliberate mypy type error.

This module exists solely to make `mypy src/` exit non-zero under the
python profile's verify-green chain. DO NOT FIX. The fixture's whole
purpose is to drive AC-005's zero-tolerance assertion: verify-green.sh
returns non-zero, the conductor refuses to write the phase-N/done tag.

If you find this file outside the fixture tree, file a bug — it should
never be imported by production code.
"""

from __future__ import annotations


def returns_wrong_type(a: int) -> str:
    # Declared return type is str; we return int. mypy --strict will
    # report this as `error: Incompatible return value type (got "int",
    # expected "str")` — the gate fires on that exit code. No mypy
    # `# type: ignore` is added; the error MUST surface for the
    # integration test to assert. The pyright suppression below scopes
    # the dismissal to repo-wide IDE scans only (per F021 spec EC-005
    # option b); mypy does not honor `# pyright:` directives.
    return a  # pyright: ignore[reportReturnType]
