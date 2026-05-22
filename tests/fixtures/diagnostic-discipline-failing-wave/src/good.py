"""F021 fixture — clean type-annotated module.

Counterpart to bad.py. Demonstrates that the fixture is not a degenerate
all-broken project — verify-green's failure traces specifically to
bad.py's type error, not to the fixture being structurally broken.
"""

from __future__ import annotations


def add(a: int, b: int) -> int:
    """Add two integers; fully typed, no errors."""
    return a + b


def greet(name: str) -> str:
    """Return a greeting; demonstrates clean string-typed code."""
    return f"hello, {name}"
